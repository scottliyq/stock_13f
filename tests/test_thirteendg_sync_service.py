from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.settings import BackendPaths
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.services.thirteendg_sync_service import THIRTEENDG_FORM_TYPES
from stock_13f.services.thirteendg_sync_service import THIRTEENDG_13D_FORM_TYPES
from stock_13f.services.thirteendg_sync_service import THIRTEENDG_13G_FORM_TYPES
from stock_13f.services.thirteendg_sync_service import ThirteenDGSyncService


@dataclass
class FakeFiling:
    accession_number: str
    form: str
    filing_date: str
    company: str

    def obj(self):
        return SimpleNamespace(
            issuer_info=SimpleNamespace(name="Nebius Group N.V.", cusip="N97284108"),
            security_info=SimpleNamespace(cusip="N97284108"),
        )


class FakeEdgarClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.owner_calls: list[dict[str, object]] = []
        self.fail_tickers: set[str] = set()
        self.fail_managers: set[str] = set()
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
                form="SCHEDULE 13G",
                filing_date="2026-06-04",
                company="Bright Horizons Family Solutions Inc.",
            )
        ]

    def search_owner_filings(
        self,
        manager_identifier: str,
        forms: tuple[str, ...],
        days_back: int,
        date_from: str | None,
        max_filings: int,
    ) -> list[FakeFiling]:
        self.owner_calls.append(
            {
                "manager_identifier": manager_identifier,
                "forms": forms,
                "days_back": days_back,
                "date_from": date_from,
                "max_filings": max_filings,
            }
        )
        if manager_identifier in self.fail_managers:
            raise httpx.ReadTimeout(f"timed out while loading owner filings for {manager_identifier}")
        return [
            FakeFiling(
                accession_number="0000000000-26-000099",
                form="SCHEDULE 13G",
                filing_date="2026-05-27",
                company="Situational Awareness LP",
            )
        ]

    def build_13dg_payload(self, filing: FakeFiling, ticker: str) -> dict[str, object]:
        self.payload_calls.append((filing.accession_number, ticker))
        if filing.accession_number in self.fail_accessions:
            raise httpx.ReadTimeout(f"timed out while parsing {filing.accession_number}")
        return {
            "ticker": ticker,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "company_name": filing.company,
            "accession_number": filing.accession_number,
            "reporting_persons": [{"name": "Example Manager"}],
            "total_shares": 123456,
            "total_percent": 5.2,
            "rule_designation": "Rule 13d-1(b)",
            "issuer_name": filing.company,
            "issuer_cusip": "10920A600",
            "security_title": "Common Stock",
            "purpose_text": "",
        }


class FakeRawRepository:
    def __init__(self, existing_payloads: dict[str, dict[str, object]] | None = None) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.reporting_person_rows: list[tuple[str, list[dict[str, object]]]] = []
        self.sync_source_rows: list[dict[str, object]] = []
        self.existing_payloads = existing_payloads or {}

    def load_record(self, accession_number: str) -> dict[str, object] | None:
        return self.existing_payloads.get(accession_number)

    def upsert_record(self, accession_number: str, payload: dict[str, object]) -> None:
        self.records.append((accession_number, payload))

    def replace_reporting_person_rows(self, accession_number: str, rows: list[dict[str, object]]) -> int:
        self.reporting_person_rows.append((accession_number, rows))
        return len(rows)

    def upsert_sync_source_row(self, row: dict[str, object]) -> int:
        self.sync_source_rows.append(row)
        return 1


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


def test_sync_13dg_queries_both_sc_and_schedule_form_names(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("BFAM",), days_back=30, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert edgar_client.calls[0]["forms"] == THIRTEENDG_FORM_TYPES
    assert "SC 13G" in THIRTEENDG_FORM_TYPES
    assert "SCHEDULE 13G" in THIRTEENDG_FORM_TYPES
    assert raw_repository.records[0][0] == "0000000000-26-000001"
    assert raw_repository.records[0][1]["form"] == "SCHEDULE 13G"


def test_sync_13dg_continues_when_search_times_out_for_one_ticker(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    edgar_client.fail_tickers.add("PLD")
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("PLD", "TSLA"), days_back=30, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert len(raw_repository.records) == 1
    assert any("PLD" in warning and "skipped" in warning for warning in result.warnings)


def test_sync_13dg_falls_back_when_single_filing_parse_times_out(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    edgar_client.fail_accessions.add("0000000000-26-000001")
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("BFAM",), days_back=30, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert len(raw_repository.records) == 1
    accession_number, payload = raw_repository.records[0]
    assert accession_number == "0000000000-26-000001"
    assert payload["reporting_persons"] == []
    assert any("parse fallback" in warning for warning in result.warnings)


def test_sync_13dg_can_limit_queries_to_13d_forms(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("BFAM",), form_scope="13d"))

    assert result.status == "success"
    assert edgar_client.calls[0]["forms"] == THIRTEENDG_13D_FORM_TYPES


def test_sync_13dg_can_limit_queries_to_13g_forms(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("BFAM",), form_scope="13g"))

    assert result.status == "success"
    assert edgar_client.calls[0]["forms"] == THIRTEENDG_13G_FORM_TYPES


def test_sync_13dg_reuses_existing_accession_without_refetching_payload(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository(
        existing_payloads={
            "0000000000-26-000001": {
                "ticker": "BFAM",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-06-04",
                "company_name": "Bright Horizons Family Solutions Inc.",
                "accession_number": "0000000000-26-000001",
                "reporting_persons": [{"name": "Example Manager"}],
                "total_shares": 123456,
                "total_percent": 5.2,
                "rule_designation": "Rule 13d-1(b)",
                "issuer_name": "Bright Horizons Family Solutions Inc.",
                "issuer_cusip": "10920A600",
                "security_title": "Common Stock",
                "purpose_text": "",
            }
        }
    )
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(Sync13DGRequest(tickers=("BFAM",), days_back=30, max_filings=5))

    assert result.status == "success"
    assert result.rows_written == 1
    assert result.details["skipped_existing_accessions"] == 1
    assert edgar_client.payload_calls == []
    assert raw_repository.records[0][0] == "0000000000-26-000001"
    assert raw_repository.sync_source_rows[0]["source_key"] == "BFAM"


def test_sync_13dg_manager_mode_queries_watchlist_ciks(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.sync(
        Sync13DGRequest(
            mode="manager",
            manager_ciks=("2045724",),
            form_scope="13g",
            max_filings=10,
        )
    )

    assert result.status == "success"
    assert result.rows_written == 1
    assert edgar_client.owner_calls[0]["manager_identifier"] == "2045724"
    assert edgar_client.owner_calls[0]["forms"] == THIRTEENDG_13G_FORM_TYPES
    assert raw_repository.records[0][0] == "0000000000-26-000099"
    assert raw_repository.sync_source_rows[0]["sync_mode"] == "manager"


def test_audit_13dg_coverage_reports_missing_manager_filings(tmp_path: Path) -> None:
    edgar_client = FakeEdgarClient()
    raw_repository = FakeRawRepository()
    service = ThirteenDGSyncService(
        settings=build_settings(tmp_path),
        checkpoints=CheckpointRepository(tmp_path / "checkpoints.json"),
        raw_repository=raw_repository,
        edgar_client=edgar_client,
    )

    result = service.audit_coverage(
        Sync13DGRequest(
            mode="manager",
            manager_ciks=("2045724",),
            date_from="2025-01-01",
            max_filings=5,
        )
    )

    assert result.status == "success"
    assert result.details["gap_count"] == 1
    assert result.details["missing_rows"][0]["manager_cik"] == "2045724"
    assert result.details["missing_rows"][0]["accession_number"] == "0000000000-26-000099"
