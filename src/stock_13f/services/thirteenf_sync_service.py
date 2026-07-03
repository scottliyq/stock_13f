"""13F sync service implementation."""

from datetime import datetime, timezone
import logging

from stock_13f.adapters.structured_13f_dataset import Structured13FDatasetAdapter
from stock_13f.core.edgar import apply_edgar_environment
from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.repositories.marts import MartsRepository
from stock_13f.repositories.raw_13f import Raw13FRepository


LOGGER = logging.getLogger("stock_13f.services.sync_13f")


class ThirteenFSyncService:
    """Run the existing quarterly 13F export pipeline via a unified service API."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        adapter: Structured13FDatasetAdapter | None = None,
        raw_repository: Raw13FRepository | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        supabase_client = build_supabase_client(settings)
        self._adapter = adapter or Structured13FDatasetAdapter(settings.paths.repo_root)
        self._raw_repository = raw_repository or Raw13FRepository(
            settings.paths.backend_state_dir / "raw_13f_manifest.json",
            supabase_client=supabase_client,
        )
        self._marts_repository = MartsRepository(
            settings.paths.marts_dir,
            supabase_client=supabase_client,
        )

    def sync(self, request: Sync13FRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        apply_edgar_environment(self._settings)
        resolved_latest_report_date = request.latest_report_date or self._adapter.latest_available_report_date()
        if request.dry_run:
            report_dates = self._adapter.recent_report_dates(resolved_latest_report_date, request.quarters)
            result = SyncResult.success(
                job_name="sync-13f",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "mode": request.mode,
                    "report_dates": report_dates,
                    "top_limit": request.top_limit,
                },
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result

        try:
            build_result = self._adapter.build_quarterly_mover_rows(
                dataset_cache_dir=self._settings.paths.data_dir / "13f_universe",
                user_agent=self._settings.edgar_identity,
                quarter_count=request.quarters,
                top_limit=request.top_limit,
                latest_report_date=resolved_latest_report_date,
                skip_download=request.skip_download,
            )
            if request.enrich_openfigi:
                warnings.append("enrich_openfigi was skipped because sync-13f no longer writes local CSV artifacts.")
            mover_rows_by_key: dict[str, dict[str, object]] = {}
            for row in build_result.rows:
                report_date = str(row["report_date"])
                security_type = str(row["security_type"])
                ranking_type = str(row["ranking_type"])
                cusip = str(row["cusip"]).strip().upper()
                ticker = str(row.get("ticker", "") or "").strip().upper()
                issuer = str(row["issuer"]).strip()
                row_key = f"{report_date}|{security_type}|{ranking_type}|{cusip}|{ticker or issuer}"
                mover_rows_by_key[row_key] = {
                    "row_key": row_key,
                    "report_date": report_date,
                    "security_type": security_type,
                    "ranking_type": ranking_type,
                    "rank": int(row["rank"]),
                    "issuer": issuer,
                    "cusip": cusip,
                    "ticker": ticker or None,
                    "business_summary": str(row.get("business_summary", "") or "").strip(),
                    "new_manager_count": int(row["new_manager_count"]),
                    "new_entry_total_value_usd": int(row["new_entry_total_value_usd"]),
                    "reduced_manager_count": int(row["reduced_manager_count"]),
                    "reduced_total_value_usd": int(row["reduced_total_value_usd"]),
                    "holder_manager_count": int(row["holder_manager_count"]),
                    "total_holding_value_usd": int(row["total_holding_value_usd"]),
                }
            mover_rows = list(mover_rows_by_key.values())
            upserted_rows = self._marts_repository.replace_quarterly_movers(
                report_dates=build_result.report_dates,
                rows=mover_rows,
            )
            manifest = {
                "latest_report_date": build_result.latest_report_date,
                "quarters": request.quarters,
                "top_limit": request.top_limit,
                "report_dates": build_result.report_dates,
                "row_count": len(mover_rows),
                "output_paths": [],
            }
            self._raw_repository.write_manifest(manifest)
            LOGGER.info("sync_13f_completed", extra={"report_dates": build_result.report_dates, "row_count": len(mover_rows)})
            result = SyncResult.success(
                job_name="sync-13f",
                started_at=started_at,
                rows_written=upserted_rows,
                checkpoints_updated=1,
                warnings=warnings,
                details=manifest,
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result
        except SupabaseError as exc:
            result = SyncResult.failed(
                job_name="sync-13f",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result
