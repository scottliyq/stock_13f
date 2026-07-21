from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.settings import Settings
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.sync_requests import BackfillTickersRequest
from stock_13f.domain.sync_requests import SyncAllRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.backend_orchestrator import BackendOrchestrator


@dataclass
class FakeService:
    job_name: str
    status: str = "success"

    def sync(self, request) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        if self.status == "failed":
            return SyncResult.failed(self.job_name, started_at, error_summary=f"{self.job_name} failed")
        return SyncResult.success(self.job_name, started_at, rows_written=1, checkpoints_updated=1)

    def rebuild(self, request) -> SyncResult:
        return self.sync(request)

    def backfill(self, request) -> SyncResult:
        return self.sync(request)


class FakeCheckpointRepository(CheckpointRepository):
    def __init__(
        self,
        path: Path,
        *,
        local_statuses: list[dict[str, object]] | None = None,
        remote_statuses: list[dict[str, object]] | None = None,
        remote_error: Exception | None = None,
    ) -> None:
        super().__init__(path)
        self._local_statuses = local_statuses or []
        self._remote_statuses = remote_statuses or []
        self._remote_error = remote_error

    def list_statuses(self) -> list[dict[str, object]]:
        return list(self._local_statuses)

    def list_remote_statuses(self, limit: int = 20) -> list[dict[str, object]]:
        del limit
        if self._remote_error is not None:
            raise self._remote_error
        return list(self._remote_statuses)


def test_sync_all_runs_services_in_order(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "Tester tester@example.com")
    settings = Settings.load()
    checkpoints = CheckpointRepository(tmp_path / "checkpoints.json")
    orchestrator = BackendOrchestrator(
        settings=settings,
        checkpoints=checkpoints,
        thirteenf_service=FakeService("sync-13f"),
        eightk_service=FakeService("sync-8k"),
        thirteendg_service=FakeService("sync-13dg"),
        marts_service=FakeService("rebuild-marts"),
    )

    result = orchestrator.sync_all(SyncAllRequest(with_marts=True))

    assert result.status == "success"
    assert result.rows_written == 4
    step_names = [step["job_name"] for step in result.details["steps"]]
    assert step_names == ["sync-13f", "sync-8k", "sync-13dg", "rebuild-marts"]


def test_sync_all_honors_fail_fast(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "Tester tester@example.com")
    settings = Settings.load()
    checkpoints = CheckpointRepository(tmp_path / "checkpoints.json")
    orchestrator = BackendOrchestrator(
        settings=settings,
        checkpoints=checkpoints,
        thirteenf_service=FakeService("sync-13f"),
        eightk_service=FakeService("sync-8k", status="failed"),
        thirteendg_service=FakeService("sync-13dg"),
        marts_service=FakeService("rebuild-marts"),
    )

    result = orchestrator.sync_all(SyncAllRequest(with_marts=True, fail_fast=True))

    assert result.status == "failed"
    step_names = [step["job_name"] for step in result.details["steps"]]
    assert step_names == ["sync-13f", "sync-8k"]


def test_backfill_tickers_routes_to_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "Tester tester@example.com")
    settings = Settings.load()
    checkpoints = CheckpointRepository(tmp_path / "checkpoints.json")
    fake_backfill_service = FakeService("backfill-tickers")
    orchestrator = BackendOrchestrator(
        settings=settings,
        checkpoints=checkpoints,
        thirteenf_service=FakeService("sync-13f"),
        eightk_service=FakeService("sync-8k"),
        thirteendg_service=FakeService("sync-13dg"),
        marts_service=FakeService("rebuild-marts"),
        ticker_backfill_service=fake_backfill_service,
    )

    result = orchestrator.backfill_tickers(BackfillTickersRequest())

    assert result.status == "success"
    assert result.job_name == "backfill-tickers"


def test_show_status_prefers_supabase_checkpoint_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "Tester tester@example.com")
    settings = Settings.load()
    checkpoints = FakeCheckpointRepository(
        tmp_path / "checkpoints.json",
        local_statuses=[{"job_name": "sync-13f", "finished_at": "2026-07-05T11:25:32+00:00"}],
        remote_statuses=[{"job_name": "sync-13dg", "finished_at": "2026-07-20T15:22:37+00:00"}],
    )
    orchestrator = BackendOrchestrator(
        settings=settings,
        checkpoints=checkpoints,
        thirteenf_service=FakeService("sync-13f"),
        eightk_service=FakeService("sync-8k"),
        thirteendg_service=FakeService("sync-13dg"),
        marts_service=FakeService("rebuild-marts"),
    )

    statuses = orchestrator.show_status()

    assert statuses == [{"job_name": "sync-13dg", "finished_at": "2026-07-20T15:22:37+00:00"}]


def test_show_status_falls_back_to_local_when_supabase_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "Tester tester@example.com")
    settings = Settings.load()
    checkpoints = FakeCheckpointRepository(
        tmp_path / "checkpoints.json",
        local_statuses=[{"job_name": "sync-13f", "finished_at": "2026-07-05T11:25:32+00:00"}],
        remote_error=SupabaseError("sync_checkpoints unavailable"),
    )
    orchestrator = BackendOrchestrator(
        settings=settings,
        checkpoints=checkpoints,
        thirteenf_service=FakeService("sync-13f"),
        eightk_service=FakeService("sync-8k"),
        thirteendg_service=FakeService("sync-13dg"),
        marts_service=FakeService("rebuild-marts"),
    )

    statuses = orchestrator.show_status()

    assert statuses == [{"job_name": "sync-13f", "finished_at": "2026-07-05T11:25:32+00:00"}]
