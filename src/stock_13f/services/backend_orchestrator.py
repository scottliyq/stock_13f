"""Orchestrator for the unified backend sync entrypoint."""

from dataclasses import replace
from datetime import datetime, timezone
import logging

import httpx
import requests

from stock_13f.adapters.structured_13f_dataset import Structured13FDatasetAdapter
from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.sync_requests import Audit13DGCoverageRequest
from stock_13f.domain.sync_requests import BackfillTickersRequest
from stock_13f.domain.sync_requests import RebuildMartsRequest
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_requests import Sync8KRequest
from stock_13f.domain.sync_requests import SyncAllRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.eightk_sync_service import EightKSyncService
from stock_13f.services.marts_service import MartsService
from stock_13f.services.ticker_backfill_service import TickerBackfillService
from stock_13f.services.thirteendg_sync_service import ThirteenDGSyncService
from stock_13f.services.thirteenf_sync_service import ThirteenFSyncService


LOGGER = logging.getLogger("stock_13f.services.backend_orchestrator")
BACKEND_RECOVERABLE_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
    httpx.HTTPError,
    requests.RequestException,
)


class BackendOrchestrator:
    """Route backend subcommands to the correct sync services."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository | None = None,
        thirteenf_service: ThirteenFSyncService | None = None,
        eightk_service: EightKSyncService | None = None,
        thirteendg_service: ThirteenDGSyncService | None = None,
        marts_service: MartsService | None = None,
        ticker_backfill_service: TickerBackfillService | None = None,
    ) -> None:
        checkpoints = checkpoints or CheckpointRepository(
            settings.paths.checkpoints_path,
            supabase_client=build_supabase_client(settings),
        )
        self._settings = settings
        self._checkpoints = checkpoints
        self._thirteenf_service = thirteenf_service or ThirteenFSyncService(settings, checkpoints)
        self._eightk_service = eightk_service or EightKSyncService(settings, checkpoints)
        self._thirteendg_service = thirteendg_service or ThirteenDGSyncService(settings, checkpoints)
        self._marts_service = marts_service or MartsService(settings, checkpoints)
        self._ticker_backfill_service = ticker_backfill_service or TickerBackfillService(settings, checkpoints)

    def sync_13f(self, request: Sync13FRequest) -> SyncResult:
        return self._thirteenf_service.sync(request)

    def sync_8k(self, request: Sync8KRequest) -> SyncResult:
        return self._eightk_service.sync(request)

    def sync_13dg(self, request: Sync13DGRequest) -> SyncResult:
        return self._thirteendg_service.sync(request)

    def audit_13dg_coverage(self, request: Audit13DGCoverageRequest) -> SyncResult:
        return self._thirteendg_service.audit_coverage(
            Sync13DGRequest(
                dry_run=request.dry_run,
                log_level=request.log_level,
                job_id=request.job_id,
                mode="manager",
                days_back=request.days_back,
                date_from=request.date_from,
                manager_ciks=request.manager_ciks,
                manager_scope=request.manager_scope,
                max_filings=request.max_filings,
                form_scope=request.form_scope,
            )
        )

    def rebuild_marts(self, request: RebuildMartsRequest) -> SyncResult:
        return self._marts_service.rebuild(request)

    def backfill_tickers(self, request: BackfillTickersRequest) -> SyncResult:
        return self._ticker_backfill_service.backfill(request)

    def sync_all(self, request: SyncAllRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings: list[str] = []
        rows_written = 0
        checkpoints_updated = 0
        details: dict[str, object] = {"steps": []}
        step_requests = [
            ("sync-13f", request.sync_13f_request or Sync13FRequest(dry_run=request.dry_run, log_level=request.log_level)),
            ("sync-8k", request.sync_8k_request or Sync8KRequest(dry_run=request.dry_run, log_level=request.log_level)),
            ("sync-13dg", request.sync_13dg_request or Sync13DGRequest(dry_run=request.dry_run, log_level=request.log_level)),
        ]
        results: list[SyncResult] = []
        for job_name, step_request in step_requests:
            result = self._run_sync_all_step(job_name, step_request)
            results.append(result)
            warnings.extend(result.warnings)
            rows_written += result.rows_written
            checkpoints_updated += result.checkpoints_updated
            step_details: dict[str, object] = {"job_name": result.job_name, "status": result.status}
            if result.error_summary:
                step_details["error_summary"] = result.error_summary
            details["steps"].append(step_details)
            if result.status == "failed" and request.fail_fast:
                aggregate = SyncResult.failed(
                    job_name="sync-all",
                    started_at=started_at,
                    error_summary=f"{result.job_name} failed: {result.error_summary}",
                    warnings=warnings,
                    details=details,
                )
                self._checkpoints.record_result(aggregate, cursor={"steps": details["steps"]})
                return aggregate

        if request.with_marts:
            marts_request = request.rebuild_marts_request or RebuildMartsRequest(
                dry_run=request.dry_run,
                log_level=request.log_level,
            )
            marts_result = self._run_sync_all_step("rebuild-marts", marts_request)
            results.append(marts_result)
            warnings.extend(marts_result.warnings)
            rows_written += marts_result.rows_written
            checkpoints_updated += marts_result.checkpoints_updated
            marts_step_details: dict[str, object] = {
                "job_name": marts_result.job_name,
                "status": marts_result.status,
            }
            if marts_result.error_summary:
                marts_step_details["error_summary"] = marts_result.error_summary
            details["steps"].append(marts_step_details)
            if marts_result.status == "failed":
                aggregate = SyncResult.failed(
                    job_name="sync-all",
                    started_at=started_at,
                    error_summary=f"{marts_result.job_name} failed: {marts_result.error_summary}",
                    warnings=warnings,
                    details=details,
                )
                self._checkpoints.record_result(aggregate, cursor={"steps": details["steps"]})
                return aggregate

        failed_results = [result for result in results if result.status == "failed"]
        if failed_results:
            aggregate = SyncResult.failed(
                job_name="sync-all",
                started_at=started_at,
                error_summary="; ".join(
                    f"{result.job_name}: {result.error_summary}" for result in failed_results
                ),
                warnings=warnings,
                details=details,
            )
        else:
            aggregate = SyncResult.success(
                job_name="sync-all",
                started_at=started_at,
                rows_written=rows_written,
                checkpoints_updated=checkpoints_updated,
                warnings=warnings,
                details=details,
            )
        self._checkpoints.record_result(aggregate, cursor={"steps": details["steps"]})
        return aggregate

    def _run_sync_all_step(
        self,
        job_name: str,
        step_request: Sync13FRequest | Sync8KRequest | Sync13DGRequest | RebuildMartsRequest,
    ) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        try:
            if job_name == "sync-13f":
                return self.sync_13f(step_request)
            if job_name == "sync-8k":
                return self.sync_8k(step_request)
            if job_name == "sync-13dg":
                return self.sync_13dg(step_request)
            return self.rebuild_marts(step_request)
        except BACKEND_RECOVERABLE_ERRORS as exc:
            error_summary = f"{type(exc).__name__}: {exc}"
            LOGGER.exception(
                "sync_all_step_failed",
                extra={"job_name": job_name, "exception_type": type(exc).__name__},
            )
            return SyncResult.failed(
                job_name=job_name,
                started_at=started_at,
                error_summary=error_summary,
                warnings=[f"{job_name} raised a recoverable exception; later sync-all steps continued."],
                details={"exception_type": type(exc).__name__},
            )

    def show_status(self) -> list[dict[str, object]]:
        try:
            return self._checkpoints.list_remote_statuses()
        except SupabaseError:
            return []
