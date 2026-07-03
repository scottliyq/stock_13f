"""File-backed checkpoint repository for backend sync jobs."""

from filelock import FileLock
from pathlib import Path
import json
import tempfile
from json import JSONDecodeError

from stock_13f.domain.sync_results import SyncResult


class CheckpointRepository:
    """Persist sync checkpoints to a local JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self._path) + ".lock")

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

    def record_result(self, result: SyncResult, cursor: dict[str, object] | None = None) -> None:
        with self._lock:
            payload = self._load()
            payload[result.job_name] = {
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
            self._save(payload)

    def list_statuses(self) -> list[dict[str, object]]:
        with self._lock:
            payload = self._load()
            return [payload[key] for key in sorted(payload)]

    def latest_status(self, job_name: str) -> dict[str, object] | None:
        with self._lock:
            payload = self._load()
            return payload.get(job_name)
