from dataclasses import dataclass
from pathlib import Path
import sys

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.settings import BackendPaths
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import Sync8KRequest
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.eightk_sync_service import EightKSyncService


@dataclass
class FakeFiling:
    accession_number: str
    form: str
    filing_date: str
    company: str


class FakeEdgarClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_tickers: set[str] = set()
        self.fail_accessions: set[str] = set()
        self.payload_calls: list[tuple[str, str]] = []

    def search_company_filings(
        self,
        ticker: str,
        forms: tuple[str, ...],
        days_back: int,
        date_from: str | None,
        max_filings: int,
    ) -> list[FakeFiling]:
        self.calls.append(
            {
                "ticker": ticker,
                "forms": forms,
                "days_back": days_back,
                "date_from": date_from,
                "max_filings": max_filings,
            }
        )
        if ticker in self.fail_tickers:
            raise httpx.ReadTimeout(f"timed out while loading filings for {ticker}")
        return [
            FakeFiling(
                accession_number="0000000000-26-000001",
                form="8-K",
                filing_date="2026-07-02",
                company="Apple Inc.",
            )
        ]

    def build_8k_payload(self, filing: FakeFiling, ticker: str) -> dict[str, object]:
        self.payload_calls.append((filing.accession_number, ticker))
        if filing.accession_number in self.fail_accessions:
            raise httpx.ReadTimeout(f"timed out while parsing {filing.accession_number}")
        return {
            "ticker": ticker,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "company_name": filing.company,
            "accession_number": filing.accession_number,
            "item_codes": ["2.02"],
            "items": [{"code": "2.02", "text": "Results of operations."}],
            "exhibits": [],
            "has_press_release": False,
            "has_earnings": True,
        }


class FakeRawRepository:
    def __init__(self, existing_payloads: dict[str, dict[str, object]] | None = None) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.existing_payloads = existing_payloads or {}

    def load_record(self, accession_number: str) -> dict[str, object] | None:
        return self.existing_payloads.get(accession_number)

    def upsert_record(self, accession_number: str, payload: dict[str, object]) -> None:
        self.records.append((accession_number, payload))


def build_settings(tmp_path: Path) -> Settings:
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
    return Settings(
        paths=paths,
        edgar_identity="stock_13f test@example.com",
        edgar_access_mode="NORMAL",
        edgar_use_local_data=True,
        edgar_local_data_dir=paths.edgar_cache_dir,
        supabase_url="",
        supabase_secret_key="",
        supabase_publishable_key="",
    )


def test_sync_8k_continues_when_search_times_out_for_one_ticker(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    edgar_client.fail_tickers.add("PLTR")
    raw_repository = FakeRawRepository()
    service = EightKSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync8KRequest(tickers=("PLTR", "AAPL"), days_back=7, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert len(raw_repository.records) == 1
    assert any("PLTR" in warning and "skipped" in warning for warning in result.warnings)


def test_sync_8k_falls_back_when_single_filing_parse_times_out(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    edgar_client.fail_accessions.add("0000000000-26-000001")
    raw_repository = FakeRawRepository()
    service = EightKSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync8KRequest(tickers=("AAPL",), days_back=7, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert len(raw_repository.records) == 1
    accession_number, payload = raw_repository.records[0]
    assert accession_number == "0000000000-26-000001"
    assert payload["item_codes"] == []
    assert payload["items"] == []
    assert any("parse fallback" in warning for warning in result.warnings)


def test_sync_8k_skips_existing_accession_without_refetching_payload(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository(
        existing_payloads={
            "0000000000-26-000001": {
                "ticker": "AAPL",
                "form": "8-K",
                "filing_date": "2026-07-02",
                "company_name": "Apple Inc.",
                "accession_number": "0000000000-26-000001",
                "item_codes": ["2.02"],
                "items": [{"code": "2.02", "text": "Results of operations."}],
                "exhibits": [],
                "has_press_release": False,
                "has_earnings": True,
            }
        }
    )
    service = EightKSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync8KRequest(tickers=("AAPL",), days_back=7, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 0
    assert result.details["skipped_existing_accessions"] == 1
    assert edgar_client.payload_calls == []
    assert raw_repository.records == []
