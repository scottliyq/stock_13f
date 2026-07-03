"""Rebuild mart snapshots from Supabase-backed data."""

from datetime import datetime, timezone

from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.manager_registry import list_default_managers
from stock_13f.domain.sync_requests import RebuildMartsRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.repositories.marts import MartsRepository


class MartsService:
    """Build local inspection snapshots from Supabase-backed marts."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        repository: MartsRepository | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        self._repository = repository or MartsRepository(
            settings.paths.marts_dir,
            supabase_client=build_supabase_client(settings),
        )

    def rebuild(self, request: RebuildMartsRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_supabase()
        self._settings.ensure_directories()
        if request.export_legacy_csv:
            warnings.append("export_legacy_csv was ignored because quarterly movers are sourced from Supabase only.")

        if request.dry_run:
            result = SyncResult.success(
                job_name="rebuild-marts",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "source_table": "mart_13f_quarterly_movers",
                    "manager_count": len(list_default_managers()),
                },
            )
            self._checkpoints.record_result(result, cursor={"source_table": "mart_13f_quarterly_movers"})
            return result

        try:
            mover_rows = self._fetch_all_quarterly_movers()
            periods = sorted({str(row["report_date"]) for row in mover_rows if row.get("report_date")})
            security_types = sorted({str(row["security_type"]) for row in mover_rows if row.get("security_type")})
            ranking_types = sorted({str(row["ranking_type"]) for row in mover_rows if row.get("ranking_type")})
            sample_rows = [
                {
                    "report_date": str(row.get("report_date", "")),
                    "security_type": str(row.get("security_type", "")),
                    "ranking_type": str(row.get("ranking_type", "")),
                    "ticker": str(row.get("ticker", "") or ""),
                    "issuer": str(row.get("issuer", "") or ""),
                }
                for row in mover_rows[:10]
            ]

            snapshot_count = 0
            self._repository.write_snapshot(
                "mart_13f_quarterly_movers",
                {
                    "periods": periods,
                    "security_types": security_types,
                    "ranking_types": ranking_types,
                    "sample_rows": sample_rows,
                    "source_table": "mart_13f_quarterly_movers",
                    "mover_row_count": len(mover_rows),
                },
            )
            snapshot_count += 1

            manager_rows = [
                {
                    "manager_cik": manager.manager_cik,
                    "manager_name": manager.manager_name,
                    "focus_areas": manager.focus_areas,
                    "short_description": manager.short_description,
                    "display_order": manager.display_order,
                    "is_active": manager.is_active,
                }
                for manager in list_default_managers()
            ]
            self._repository.write_snapshot("mart_manager_profile", {"managers": manager_rows})
            snapshot_count += 1

            snapshot_row = {
                "snapshot_key": "default",
                "manager_count": len(manager_rows),
                "latest_report_period": periods[-1] if periods else None,
                "available_report_periods": periods,
            }
            self._repository.write_snapshot("mart_manager_research_snapshot", snapshot_row)
            snapshot_count += 1

            rows_written = snapshot_count
            rows_written += self._repository.upsert_manager_watchlist(manager_rows)
            rows_written += self._repository.upsert_manager_profiles(manager_rows)
            rows_written += self._repository.upsert_research_snapshot(snapshot_row)
            result = SyncResult.success(
                job_name="rebuild-marts",
                started_at=started_at,
                rows_written=rows_written,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "snapshot_count": snapshot_count,
                    "source_table": "mart_13f_quarterly_movers",
                    "mover_row_count": len(mover_rows),
                },
            )
            self._checkpoints.record_result(result, cursor={"source_table": "mart_13f_quarterly_movers"})
            return result
        except SupabaseError as exc:
            result = SyncResult.failed(
                job_name="rebuild-marts",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={"source_table": "mart_13f_quarterly_movers"},
            )
            self._checkpoints.record_result(result, cursor={"source_table": "mart_13f_quarterly_movers"})
            return result

    def _fetch_all_quarterly_movers(self) -> list[dict[str, object]]:
        page_size = 1000
        offset = 0
        rows: list[dict[str, object]] = []
        while True:
            page = self._repository.fetch_quarterly_movers(
                limit=page_size,
                offset=offset,
                order="report_date.desc,security_type.asc,ranking_type.asc,rank.asc",
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows
