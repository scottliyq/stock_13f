from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.table_name: str | None = None
        self.on_conflict: str | None = None

    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict[str, object]],
        on_conflict: str,
    ) -> int:
        self.table_name = table_name
        self.rows = rows
        self.on_conflict = on_conflict
        return len(rows)

    def fetch_rows(
        self,
        table_name: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        del table_name, limit, offset, order
        if filters is None:
            return list(self.rows)
        job_name_filter = filters.get("job_name", "")
        if job_name_filter.startswith("eq."):
            job_name = job_name_filter.removeprefix("eq.")
            return [row for row in self.rows if row.get("job_name") == job_name]
        return list(self.rows)


def test_checkpoint_repository_records_latest_status(tmp_path: Path) -> None:
    supabase_client = FakeSupabaseClient()
    repository = CheckpointRepository(
        tmp_path / "checkpoints.json",
        supabase_client=supabase_client,
    )
    result = SyncResult.success(
        job_name="sync-13f",
        started_at=datetime.now(timezone.utc),
        rows_written=2,
        checkpoints_updated=1,
    )

    repository.record_result(result, cursor={"latest_report_date": "2026-03-31"})

    status = repository.latest_status("sync-13f")
    assert status is not None
    assert status["job_name"] == "sync-13f"
    assert status["rows_written"] == 2
    assert status["cursor"]["latest_report_date"] == "2026-03-31"


def test_checkpoint_repository_returns_empty_without_supabase_client(tmp_path: Path) -> None:
    repository = CheckpointRepository(tmp_path / "checkpoints.json")

    assert repository.list_statuses() == []
    assert repository.latest_status("sync-13f") is None


def test_checkpoint_repository_dual_writes_remote_status(tmp_path: Path) -> None:
    supabase_client = FakeSupabaseClient()
    repository = CheckpointRepository(
        tmp_path / "checkpoints.json",
        supabase_client=supabase_client,
    )
    result = SyncResult.success(
        job_name="sync-13dg",
        started_at=datetime.now(timezone.utc),
        rows_written=4,
        checkpoints_updated=1,
    )

    repository.record_result(result, cursor={"mode": "manager"})

    assert supabase_client.table_name == "sync_checkpoints"
    assert supabase_client.on_conflict == "job_name"
    assert supabase_client.rows[0]["job_name"] == "sync-13dg"
    assert supabase_client.rows[0]["cursor"] == {"mode": "manager"}
