from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.settings import BackendPaths
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import BackfillTickersRequest
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.ticker_backfill_service import TickerBackfillService


class FakeMartsRepository:
    def __init__(self) -> None:
        self.movers_rows = [
            {
                "row_key": "old-mover",
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_total_holding_value",
                "rank": 1,
                "issuer": "HONEYWELL INTL INC",
                "cusip": "438516106",
                "ticker": None,
                "business_summary": "industrial",
                "new_manager_count": 1,
                "new_entry_total_value_usd": 1,
                "reduced_manager_count": 0,
                "reduced_total_value_usd": 0,
                "holder_manager_count": 1,
                "total_holding_value_usd": 1,
            }
        ]
        self.detail_rows = [
            {
                "row_key": "old-detail",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1697748,
                "manager_name": "ARK Investment Management LLC",
                "rank": 155,
                "ticker": None,
                "issuer": "ChargePoint Holdings Inc - COM CL A",
                "cusip": "15961R105",
                "status": "increased",
                "previous_value_usd": 100,
                "current_value_usd": 120,
                "value_change_usd": 20,
            }
        ]
        self.security_rows = [
            {
                "row_key": "old-security",
                "report_date": "2026-03-31",
                "previous_report_date": "2025-12-31",
                "manager_cik": 1697748,
                "manager_name": "ARK Investment Management LLC",
                "ticker": None,
                "issuer": "Pure Storage Inc",
                "cusip": "74624M102",
                "status": "increased",
                "previous_value_usd": 100,
                "current_value_usd": 120,
                "value_change_usd": 20,
                "found_in_current": True,
                "found_in_previous": True,
            }
        ]
        self.replaced_movers: list[dict[str, object]] = []
        self.replaced_details: list[dict[str, object]] = []
        self.replaced_security: list[dict[str, object]] = []

    def fetch_quarterly_movers(self, limit=1000, offset=0, filters=None, order=None):
        del limit, offset, filters, order
        return list(self.movers_rows)

    def fetch_manager_rebalance_details(self, limit=1000, offset=0, filters=None, order=None):
        del limit, offset, filters, order
        return list(self.detail_rows)

    def fetch_manager_security_latest_rows(self, limit=1000, offset=0, filters=None, order=None):
        del limit, offset, filters, order
        return list(self.security_rows)

    def replace_quarterly_movers(self, report_dates, rows):
        del report_dates
        self.replaced_movers = rows
        return len(rows)

    def replace_manager_rebalance_details(self, report_dates, rows):
        del report_dates
        self.replaced_details = rows
        return len(rows)

    def replace_manager_security_latest_rows(self, report_dates, rows):
        del report_dates
        self.replaced_security = rows
        return len(rows)


def test_backfill_service_fills_rows_from_local_and_sec_cache(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cusip_ticker_map.csv").write_text(
        "cusip,ticker,issuer\n438516106,HON,HONEYWELL INTL INC\n",
        encoding="utf-8",
    )
    (data_dir / "sec_company_tickers.json").write_text(
        json.dumps(
            {
                "0": {"cik_str": 1777393, "ticker": "CHPT", "title": "ChargePoint Holdings, Inc."},
                "1": {"cik_str": 1474432, "ticker": "PSTG", "title": "Pure Storage, Inc."},
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "sec_company_tickers_exchange.json").write_text("{}", encoding="utf-8")
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
    repository = FakeMartsRepository()
    service = TickerBackfillService(
        settings=settings,
        checkpoints=CheckpointRepository(paths.checkpoints_path),
        repository=repository,
    )
    monkeypatch.setattr(service, "_refresh_sec_company_caches", lambda: [])
    monkeypatch.setattr(service, "_enrich_missing_cusips_with_openfigi", lambda *args, **kwargs: 0)

    result = service.backfill(BackfillTickersRequest())

    assert result.status == "success"
    assert repository.replaced_movers[0]["ticker"] == "HON"
    assert repository.replaced_details[0]["ticker"] == "CHPT"
    assert repository.replaced_security[0]["ticker"] == "PSTG"
    assert result.details["after_missing"]["mart_13f_quarterly_movers"]["missing_count"] == 0


def test_backfill_service_dedupes_conflicting_row_keys(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cusip_ticker_map.csv").write_text(
        "cusip,ticker,issuer\n88339J105,TTD,Trade Desk Inc\n",
        encoding="utf-8",
    )
    (data_dir / "sec_company_tickers.json").write_text("{}", encoding="utf-8")
    (data_dir / "sec_company_tickers_exchange.json").write_text("{}", encoding="utf-8")
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
    repository = FakeMartsRepository()
    repository.security_rows = [
        {
            "row_key": "old-security-a",
            "report_date": "2026-03-31",
            "previous_report_date": "2025-12-31",
            "manager_cik": 1697748,
            "manager_name": "ARK Investment Management LLC",
            "ticker": None,
            "issuer": "THE TRADE DESK INC - COM CL A",
            "cusip": "88339J105",
            "status": "increased",
            "previous_value_usd": 100,
            "current_value_usd": 120,
            "value_change_usd": 20,
            "found_in_current": True,
            "found_in_previous": True,
        },
        {
            "row_key": "old-security-b",
            "report_date": "2026-03-31",
            "previous_report_date": "2025-12-31",
            "manager_cik": 1697748,
            "manager_name": "ARK Investment Management LLC",
            "ticker": None,
            "issuer": "Trade Desk Inc",
            "cusip": "88339J105",
            "status": "increased",
            "previous_value_usd": 100,
            "current_value_usd": 120,
            "value_change_usd": 20,
            "found_in_current": True,
            "found_in_previous": True,
        },
    ]
    service = TickerBackfillService(
        settings=settings,
        checkpoints=CheckpointRepository(paths.checkpoints_path),
        repository=repository,
    )
    monkeypatch.setattr(service, "_refresh_sec_company_caches", lambda: [])
    monkeypatch.setattr(service, "_enrich_missing_cusips_with_openfigi", lambda *args, **kwargs: 0)

    result = service.backfill(BackfillTickersRequest())

    assert result.status == "success"
    assert len(repository.replaced_security) == 1
    assert repository.replaced_security[0]["ticker"] == "TTD"
    assert result.details["resolution_stats"]["mart_manager_security_latest"]["deduped"] == 1
