from dataclasses import dataclass
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.adapters.structured_13f_dataset import QuarterlyMoverBuildResult
from stock_13f.core.settings import BackendPaths
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.thirteenf_sync_service import ThirteenFSyncService


@dataclass
class FakeAdapter:
    result: QuarterlyMoverBuildResult

    def latest_available_report_date(self) -> str:
        return self.result.latest_report_date

    def recent_report_dates(self, latest_report_date: str, quarter_count: int) -> list[str]:
        del latest_report_date, quarter_count
        return self.result.report_dates

    def build_quarterly_mover_rows(
        self,
        dataset_cache_dir: Path,
        user_agent: str,
        quarter_count: int,
        top_limit: int,
        latest_report_date: str | None,
        skip_download: bool,
    ) -> QuarterlyMoverBuildResult:
        del dataset_cache_dir, user_agent, quarter_count, top_limit, latest_report_date, skip_download
        return self.result


class FakeRawRepository:
    def __init__(self) -> None:
        self.manifest: dict[str, object] | None = None

    def write_manifest(self, payload: dict[str, object]) -> None:
        self.manifest = payload


class FakeMartsRepository:
    def __init__(self) -> None:
        self.report_dates: list[str] = []
        self.rows: list[dict[str, object]] = []

    def replace_quarterly_movers(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        self.report_dates = report_dates
        self.rows = rows
        return len(rows)


def test_sync_13f_deduplicates_duplicate_row_keys(tmp_path: Path) -> None:
    paths = BackendPaths(
        repo_root=tmp_path,
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        backend_state_dir=tmp_path / "backend_state",
        checkpoints_path=tmp_path / "backend_state" / "checkpoints.json",
        edgar_cache_dir=tmp_path / "backend_state" / "edgar_cache",
        raw_8k_dir=tmp_path / "backend_state" / "raw_8k",
        raw_13dg_dir=tmp_path / "backend_state" / "raw_13dg",
        marts_dir=tmp_path / "backend_state" / "marts",
    )
    settings = Settings(
        paths=paths,
        edgar_identity="stock_13f test@example.com",
        edgar_access_mode="NORMAL",
        edgar_use_local_data=True,
        edgar_local_data_dir=paths.edgar_cache_dir,
        supabase_url="https://example.supabase.co/rest/v1",
        supabase_secret_key="secret",
        supabase_publishable_key="publishable",
    )
    duplicate_rows = [
        {
            "report_date": "2026-03-31",
            "security_type": "stock",
            "ranking_type": "top_new_manager_count",
            "rank": 1,
            "issuer": "Apple Inc",
            "cusip": "037833100",
            "ticker": "AAPL",
            "business_summary": "consumer",
            "new_manager_count": 1,
            "new_entry_total_value_usd": 1,
            "reduced_manager_count": 0,
            "reduced_total_value_usd": 0,
            "holder_manager_count": 1,
            "total_holding_value_usd": 1,
        },
        {
            "report_date": "2026-03-31",
            "security_type": "stock",
            "ranking_type": "top_new_manager_count",
            "rank": 1,
            "issuer": "Apple Inc",
            "cusip": "037833100",
            "ticker": "AAPL",
            "business_summary": "consumer",
            "new_manager_count": 1,
            "new_entry_total_value_usd": 1,
            "reduced_manager_count": 0,
            "reduced_total_value_usd": 0,
            "holder_manager_count": 1,
            "total_holding_value_usd": 1,
        },
    ]
    service = ThirteenFSyncService(
        settings=settings,
        checkpoints=CheckpointRepository(paths.checkpoints_path),
        adapter=FakeAdapter(
            QuarterlyMoverBuildResult(
                latest_report_date="2026-03-31",
                report_dates=["2026-03-31"],
                rows=duplicate_rows,
            )
        ),
        raw_repository=FakeRawRepository(),
    )
    fake_marts = FakeMartsRepository()
    service._marts_repository = fake_marts

    result = service.sync(Sync13FRequest(quarters=1, top_limit=100, skip_download=True))

    assert result.status == "success"
    assert result.rows_written == 1
    assert fake_marts.report_dates == ["2026-03-31"]
    assert len(fake_marts.rows) == 1
    assert fake_marts.rows[0]["row_key"] == "2026-03-31|stock|top_new_manager_count|037833100|AAPL"
