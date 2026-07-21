"""File-backed checkpoint repository for backend sync jobs."""

from filelock import FileLock
from pathlib import Path
import json
import tempfile
from json import JSONDecodeError

from stock_13f.core.supabase import SupabaseError
from stock_13f.core.supabase import SupabaseRestClient
from stock_13f.core.supabase import SupabaseTableMissingError
from stock_13f.domain.sync_results import SyncResult


class CheckpointRepository:
    """Persist sync checkpoints to a local JSON file."""

    _REMOTE_TABLE_NAME = "sync_checkpoints"

    def __init__(self, path: Path, supabase_client: SupabaseRestClient | None = None) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self._path) + ".lock")
        self._supabase_client = supabase_client

    def _load(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}
        raw_text = self._path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {}
        try:
            return json.loads(raw_text)
        except JSONDecodeError as exc:
            raise RuntimeError(f"Checkpoint file is corrupted: {self._path}") from exc

    def _save(self, payload: dict[str, dict[str, object]]) -> None:
        serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=self._path.stem,
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temp_path = Path(handle.name)
        temp_path.replace(self._path)

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
        try:
            self._supabase_client.upsert_rows(
                self._REMOTE_TABLE_NAME,
                [payload_row],
                on_conflict="job_name",
            )
        except (SupabaseError, SupabaseTableMissingError):
            return

    def record_result(self, result: SyncResult, cursor: dict[str, object] | None = None) -> None:
        payload_row = self._build_status_payload(result, cursor)
        with self._lock:
            payload = self._load()
            payload[result.job_name] = payload_row
            self._save(payload)
        self._record_remote_result(payload_row)

    def list_statuses(self) -> list[dict[str, object]]:
        with self._lock:
            payload = self._load()
            return [payload[key] for key in sorted(payload)]

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
        with self._lock:
            payload = self._load()
            return payload.get(job_name)
