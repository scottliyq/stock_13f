"""Orchestrator for the unified backend sync entrypoint."""

from dataclasses import replace
from datetime import datetime, timezone

from stock_13f.adapters.structured_13f_dataset import Structured13FDatasetAdapter
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import RebuildMartsRequest
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_requests import Sync8KRequest
from stock_13f.domain.sync_requests import SyncAllRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.eightk_sync_service import EightKSyncService
from stock_13f.services.marts_service import MartsService
from stock_13f.services.thirteendg_sync_service import ThirteenDGSyncService
from stock_13f.services.thirteenf_sync_service import ThirteenFSyncService


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
    ) -> None:
        checkpoints = checkpoints or CheckpointRepository(settings.paths.checkpoints_path)
        self._settings = settings
        self._checkpoints = checkpoints
        self._thirteenf_service = thirteenf_service or ThirteenFSyncService(settings, checkpoints)
        self._eightk_service = eightk_service or EightKSyncService(settings, checkpoints)
        self._thirteendg_service = thirteendg_service or ThirteenDGSyncService(settings, checkpoints)
        self._marts_service = marts_service or MartsService(settings, checkpoints)

    def sync_13f(self, request: Sync13FRequest) -> SyncResult:
        return self._thirteenf_service.sync(request)

    def sync_8k(self, request: Sync8KRequest) -> SyncResult:
        return self._eightk_service.sync(request)

    def sync_13dg(self, request: Sync13DGRequest) -> SyncResult:
        return self._thirteendg_service.sync(request)

    def rebuild_marts(self, request: RebuildMartsRequest) -> SyncResult:
        return self._marts_service.rebuild(request)

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
            if job_name == "sync-13f":
                result = self.sync_13f(step_request)
            elif job_name == "sync-8k":
                result = self.sync_8k(step_request)
            else:
                result = self.sync_13dg(step_request)
            results.append(result)
            warnings.extend(result.warnings)
            rows_written += result.rows_written
            checkpoints_updated += result.checkpoints_updated
            details["steps"].append({"job_name": result.job_name, "status": result.status})
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
            marts_result = self.rebuild_marts(marts_request)
            results.append(marts_result)
            warnings.extend(marts_result.warnings)
            rows_written += marts_result.rows_written
            checkpoints_updated += marts_result.checkpoints_updated
            details["steps"].append({"job_name": marts_result.job_name, "status": marts_result.status})
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

    def show_status(self) -> list[dict[str, object]]:
        return self._checkpoints.list_statuses()
