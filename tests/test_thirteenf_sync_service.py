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
        manager_ciks: set[str] | None = None,
    ) -> QuarterlyMoverBuildResult:
        del dataset_cache_dir, user_agent, quarter_count, top_limit, latest_report_date, skip_download, manager_ciks
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
        self.summary_report_dates: list[str] = []
        self.summary_rows: list[dict[str, object]] = []
        self.detail_report_dates: list[str] = []
        self.detail_rows: list[dict[str, object]] = []
        self.security_latest_report_dates: list[str] = []
        self.security_latest_rows: list[dict[str, object]] = []

    def replace_quarterly_movers(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        self.report_dates = report_dates
        self.rows = rows
        return len(rows)

    def replace_manager_rebalance_summaries(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        self.summary_report_dates = report_dates
        self.summary_rows = rows
        return len(rows)

    def replace_manager_rebalance_details(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        self.detail_report_dates = report_dates
        self.detail_rows = rows
        return len(rows)

    def replace_manager_security_latest_rows(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        self.security_latest_report_dates = report_dates
        self.security_latest_rows = rows
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


def test_sync_13f_persists_manager_rebalance_rows(tmp_path: Path) -> None:
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
    adapter_result = QuarterlyMoverBuildResult(
        latest_report_date="2026-03-31",
        report_dates=["2026-03-31"],
        rows=[],
        manager_rebalance_summary_rows=[
            {
                "row_key": "2026-03-31|1336528",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1336528,
                "manager_name": "Pershing Square Capital Management, L.P.",
                "current_holding_count": 8,
                "previous_holding_count": 7,
                "new_count": 1,
                "increased_count": 2,
                "decreased_count": 1,
                "exited_count": 0,
                "unchanged_count": 4,
            }
        ],
        manager_rebalance_detail_rows=[
            {
                "row_key": "2026-03-31|1336528|1|NVDA|new",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1336528,
                "manager_name": "Pershing Square Capital Management, L.P.",
                "rank": 1,
                "ticker": "NVDA",
                "issuer": "NVIDIA Corp. (NVDA)",
                "cusip": "67066G104",
                "status": "new",
                "previous_value_usd": 0,
                "current_value_usd": 150000000,
                "value_change_usd": 150000000,
            }
        ],
        manager_security_latest_rows=[
            {
                "row_key": "2026-03-31|1336528|67066G104|NVDA",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1336528,
                "manager_name": "Pershing Square Capital Management, L.P.",
                "ticker": "NVDA",
                "issuer": "NVIDIA Corp. (NVDA)",
                "cusip": "67066G104",
                "status": "new",
                "previous_value_usd": 0,
                "current_value_usd": 150000000,
                "value_change_usd": 150000000,
                "found_in_current": True,
                "found_in_previous": False,
            }
        ],
    )
    service = ThirteenFSyncService(
        settings=settings,
        checkpoints=CheckpointRepository(paths.checkpoints_path),
        adapter=FakeAdapter(adapter_result),
        raw_repository=FakeRawRepository(),
    )
    fake_marts = FakeMartsRepository()
    service._marts_repository = fake_marts

    result = service.sync(Sync13FRequest(quarters=1, top_limit=100, skip_download=True))

    assert result.status == "success"
    assert fake_marts.summary_report_dates == ["2026-03-31"]
    assert fake_marts.detail_report_dates == ["2026-03-31"]
    assert fake_marts.security_latest_report_dates == ["2026-03-31"]
    assert fake_marts.summary_rows[0]["manager_cik"] == 1336528
    assert fake_marts.detail_rows[0]["ticker"] == "NVDA"
    assert fake_marts.security_latest_rows[0]["cusip"] == "67066G104"


def test_sync_13f_backfills_missing_ticker_from_cusip_map(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cusip_ticker_map.csv").write_text(
        "cusip,ticker,issuer\n438516106,HON,HONEYWELL INTL INC\n",
        encoding="utf-8",
    )
    paths = BackendPaths(
        repo_root=tmp_path,
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        data_dir=data_dir,
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
    adapter_result = QuarterlyMoverBuildResult(
        latest_report_date="2026-03-31",
        report_dates=["2026-03-31"],
        rows=[
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_total_holding_value",
                "rank": 1,
                "issuer": "HONEYWELL INTL INC",
                "cusip": "438516106",
                "ticker": "",
                "business_summary": "industrial",
                "new_manager_count": 1,
                "new_entry_total_value_usd": 10,
                "reduced_manager_count": 0,
                "reduced_total_value_usd": 0,
                "holder_manager_count": 1,
                "total_holding_value_usd": 10,
            }
        ],
        manager_rebalance_detail_rows=[
            {
                "row_key": "old",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1697748,
                "manager_name": "ARK Investment Management LLC",
                "rank": 155,
                "ticker": "",
                "issuer": "Honeywell International Inc",
                "cusip": "438516106",
                "status": "increased",
                "previous_value_usd": 100,
                "current_value_usd": 120,
                "value_change_usd": 20,
            }
        ],
        manager_security_latest_rows=[
            {
                "row_key": "old2",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1697748,
                "manager_name": "ARK Investment Management LLC",
                "ticker": "",
                "issuer": "Honeywell International Inc",
                "cusip": "438516106",
                "status": "increased",
                "previous_value_usd": 100,
                "current_value_usd": 120,
                "value_change_usd": 20,
                "found_in_current": True,
                "found_in_previous": True,
            }
        ],
    )
    service = ThirteenFSyncService(
        settings=settings,
        checkpoints=CheckpointRepository(paths.checkpoints_path),
        adapter=FakeAdapter(adapter_result),
        raw_repository=FakeRawRepository(),
    )
    fake_marts = FakeMartsRepository()
    service._marts_repository = fake_marts

    result = service.sync(Sync13FRequest(quarters=1, top_limit=100, skip_download=True))

    assert result.status == "success"
    assert fake_marts.rows[0]["ticker"] == "HON"
    assert fake_marts.rows[0]["row_key"].endswith("|HON")
    assert fake_marts.detail_rows[0]["ticker"] == "HON"
    assert "|HON|increased" in fake_marts.detail_rows[0]["row_key"]
    assert fake_marts.security_latest_rows[0]["ticker"] == "HON"
    assert fake_marts.security_latest_rows[0]["row_key"].endswith("|438516106|HON")
