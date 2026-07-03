from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository


def test_checkpoint_repository_records_latest_status(tmp_path: Path) -> None:
    repository = CheckpointRepository(tmp_path / "checkpoints.json")
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


def test_checkpoint_repository_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "checkpoints.json"
    path.write_text("", encoding="utf-8")
    repository = CheckpointRepository(path)

    assert repository.list_statuses() == []
