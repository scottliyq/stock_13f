"""Supabase-backed checkpoint repository for backend sync jobs."""

from pathlib import Path

from stock_13f.core.supabase import SupabaseError
from stock_13f.core.supabase import SupabaseRestClient
from stock_13f.core.supabase import SupabaseTableMissingError
from stock_13f.domain.sync_results import SyncResult


class CheckpointRepository:
    """Persist sync checkpoints to Supabase."""

    _REMOTE_TABLE_NAME = "sync_checkpoints"

    def __init__(self, path: Path, supabase_client: SupabaseRestClient | None = None) -> None:
        del path
        self._supabase_client = supabase_client

    def _build_status_payload(self, result: SyncResult, cursor: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "job_name": result.job_name,
            "status": result.status,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "rows_written": result.rows_written,
            "checkpoints_updated": result.checkpoints_updated,
            "warnings": result.warnings,
            "error_summary": result.error_summary,
            "details": result.details,
            "cursor": cursor or {},
        }

    def _record_remote_result(self, payload_row: dict[str, object]) -> None:
        if self._supabase_client is None:
            return
        self._supabase_client.upsert_rows(
            self._REMOTE_TABLE_NAME,
            [payload_row],
            on_conflict="job_name",
        )

    def record_result(self, result: SyncResult, cursor: dict[str, object] | None = None) -> None:
        payload_row = self._build_status_payload(result, cursor)
        self._record_remote_result(payload_row)

    def list_statuses(self) -> list[dict[str, object]]:
        return self.list_remote_statuses()

    def list_remote_statuses(self, limit: int = 20) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        return self._supabase_client.fetch_rows(
            self._REMOTE_TABLE_NAME,
            limit=limit,
            offset=0,
            order="finished_at.desc",
        )

    def latest_status(self, job_name: str) -> dict[str, object] | None:
        if self._supabase_client is None:
            return None
        rows = self._supabase_client.fetch_rows(
            self._REMOTE_TABLE_NAME,
            limit=1,
            offset=0,
            filters={"job_name": f"eq.{job_name}"},
            order="finished_at.desc",
        )
        if not rows:
            return None
        return rows[0]
