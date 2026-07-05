from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import stock_13f.ui.data_access as data_access
from stock_13f.ui.data_access import split_focus_terms
from stock_13f.ui.data_access import build_security_candidates
from stock_13f.ui.data_access import build_security_history_digest
from stock_13f.ui.data_access import build_manager_13dg_monitor_rows
from stock_13f.ui.data_access import build_13dg_reporting_person_changes
from stock_13f.ui.data_access import load_13dg_chain
from stock_13f.ui.data_access import load_manager_13f_crosscheck
from stock_13f.ui.data_access import load_latest_13dg_change_summary
from stock_13f.ui.data_access import load_recent_8k
from stock_13f.ui.data_access import load_recent_13dg_by_manager
from stock_13f.ui.data_access import load_recent_13dg_for_tickers
from stock_13f.ui.data_access import load_manager_rebalance_snapshot
from stock_13f.ui.data_access import summarize_13dg_row
from stock_13f.ui.data_access import summarize_8k_row


def test_split_focus_terms_handles_chinese_and_slash_delimiters() -> None:
    terms = split_focus_terms("AI 基建、半导体、数据中心、电力链 / Apple/NVDA/TSLA")
    assert terms == ["AI", "基建", "半导体", "数据中心", "电力链", "Apple", "NVDA", "TSLA"]


def test_summarize_8k_row_prefers_structured_payload() -> None:
    summary = summarize_8k_row(
        {
            "accession_number": "0001",
            "ticker": "SHOP",
            "form": "8-K",
            "filing_date": "2026-07-02",
            "company_name": "SHOPIFY INC.",
            "payload": {
                "period_of_report": "2026-07-02",
                "date_of_report": "July 02, 2026",
                "item_codes": ["Item 5.02", "Item 9.01"],
                "items": [
                    {"code": "Item 5.02", "text": "Director resignation update."},
                    {"code": "Item 9.01", "text": "Financial statements and exhibits."},
                ],
                "has_press_release": False,
                "has_earnings": True,
                "filing_url": "https://www.sec.gov/example",
                "exhibits": [
                    {
                        "sequence_number": "2",
                        "document": "ex99-1.htm",
                        "document_type": "EX-99.1",
                        "description": "Press release",
                        "purpose": "Press release",
                    }
                ],
            },
        }
    )

    assert summary["ticker"] == "SHOP"
    assert summary["period_of_report"] == "2026-07-02"
    assert summary["item_codes"] == ["Item 5.02", "Item 9.01"]
    assert summary["has_earnings"] is True
    assert summary["has_structured_content"] is True
    assert "Items: Item 5.02, Item 9.01" in str(summary["summary_text"])


def test_summarize_13dg_row_prefers_structured_payload() -> None:
    summary = summarize_13dg_row(
        {
            "ticker": "MS",
            "form": "SCHEDULE 13G",
            "filing_date": "2026-06-26",
            "company_name": "MORGAN STANLEY",
            "payload": {
                "filing_url": "https://www.sec.gov/example",
                "issuer_name": "Zepp Health Corp",
                "issuer_cik": "1961960",
                "issuer_cusip": "98945L204",
                "security_title": "Class A Ordinary Shares / American Depositary Receipts",
                "event_date": "09/30/2025",
                "amendment_number": "",
                "is_amendment": False,
                "is_passive_investor": True,
                "rule_designation": "Rule 13d-1(b)",
                "total_shares": 8472224,
                "total_percent": 7.5,
                "summary": "Morgan Stanley reported 8,472,224 shares, representing 7.5% of class.",
                "reporting_persons": [
                    {
                        "name": "Morgan Stanley",
                        "aggregate_amount": 8472224,
                        "percent_of_class": 7.5,
                        "type_of_reporting_person": "HC",
                        "sole_voting_power": 8472224,
                        "shared_voting_power": 0,
                    }
                ],
            },
        }
    )

    assert summary["company_name"] == "MORGAN STANLEY"
    assert summary["filing_url"] == "https://www.sec.gov/example"
    assert summary["issuer_name"] == "Zepp Health Corp"
    assert summary["issuer_cik"] == "1961960"
    assert summary["total_shares"] == 8472224
    assert summary["total_percent"] == 7.5
    assert summary["is_passive_investor"] is True
    assert summary["reporting_persons"][0]["name"] == "Morgan Stanley"
    assert summary["reporting_persons"][0]["sole_voting_power"] == 8472224
    assert "7.5% of class" in str(summary["summary_text"])


def test_summarize_13dg_row_resolves_ticker_from_cusip_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRepository:
        def resolve_ticker(self, issuer_cusip: str, fallback_ticker: str = "") -> str:
            if issuer_cusip == "N97284108":
                return "NBIS"
            return fallback_ticker

    monkeypatch.setattr(data_access, "get_security_identifier_repository", lambda: FakeRepository())

    summary = summarize_13dg_row(
        {
            "ticker": "",
            "form": "SCHEDULE 13G",
            "filing_date": "2026-05-27",
            "company_name": "Nebius Group N.V.",
            "payload": {
                "issuer_name": "Nebius Group N.V.",
                "issuer_cusip": "N97284108",
                "total_shares": 12410060,
                "total_percent": 5.6,
                "reporting_persons": [
                    {
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 12410060,
                        "percent_of_class": 5.6,
                    }
                ],
            },
        }
    )

    assert summary["ticker"] == "NBIS"


def test_build_13dg_reporting_person_changes_detects_new_and_increased() -> None:
    current_detail = {
        "reporting_persons": [
            {
                "cik": "111",
                "name": "Alpha Capital",
                "aggregate_amount": 120,
                "percent_of_class": 6.0,
                "type_of_reporting_person": "IA",
            },
            {
                "cik": "222",
                "name": "Beta Fund",
                "aggregate_amount": 50,
                "percent_of_class": 2.5,
                "type_of_reporting_person": "OO",
            },
        ]
    }
    previous_detail = {
        "reporting_persons": [
            {
                "cik": "111",
                "name": "Alpha Capital",
                "aggregate_amount": 90,
                "percent_of_class": 4.5,
                "type_of_reporting_person": "IA",
            }
        ]
    }

    changes = build_13dg_reporting_person_changes(current_detail, previous_detail)

    assert [row["name"] for row in changes] == ["Beta Fund", "Alpha Capital"]
    assert [row["status"] for row in changes] == ["new", "increased"]
    assert changes[1]["delta_shares"] == 30
    assert changes[1]["delta_percent"] == 1.5


def test_load_13dg_chain_filters_same_family_and_same_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": "PLTR",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-07-01",
                "company_name": "PLTR Filer",
                "accession_number": "1",
                "payload": {"issuer_name": "Surf Air Mobility Inc.", "issuer_cusip": "868927203"},
            },
            {
                "ticker": "PLTR",
                "form": "SCHEDULE 13G/A",
                "filing_date": "2026-06-01",
                "company_name": "PLTR Filer",
                "accession_number": "2",
                "payload": {"issuer_name": "Surf Air Mobility Inc.", "issuer_cusip": "868927203"},
            },
            {
                "ticker": "PLTR",
                "form": "SCHEDULE 13D",
                "filing_date": "2026-05-01",
                "company_name": "PLTR Filer",
                "accession_number": "3",
                "payload": {"issuer_name": "Surf Air Mobility Inc.", "issuer_cusip": "868927203"},
            },
            {
                "ticker": "PLTR",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-04-01",
                "company_name": "PLTR Filer",
                "accession_number": "4",
                "payload": {"issuer_name": "Another Issuer", "issuer_cusip": "000000000"},
            },
        ],
    )

    chain = load_13dg_chain("PLTR", "13G", "868927203", "Surf Air Mobility Inc.", limit=10)

    assert [row["accession_number"] for row in chain] == ["1", "2"]


def test_load_latest_13dg_change_summary_uses_previous_filing_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        data_access,
        "load_recent_13dg",
        lambda search_text="", limit=100: [
            {
                "ticker": "PLTR",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-07-01",
                "company_name": "PLTR Filer",
                "accession_number": "1",
                "payload": {
                    "issuer_name": "Surf Air Mobility Inc.",
                    "issuer_cusip": "868927203",
                    "rule_designation": "Rule 13d-1(c)",
                    "total_percent": 7.4,
                    "reporting_persons": [
                        {
                            "cik": "111",
                            "name": "Alpha Capital",
                            "aggregate_amount": 120,
                            "percent_of_class": 7.4,
                            "type_of_reporting_person": "IA",
                        }
                    ],
                },
            }
        ],
    )
    monkeypatch.setattr(
        data_access,
        "load_13dg_chain",
        lambda ticker, form_family, issuer_cusip, issuer_name, limit=20: [
            {
                "ticker": ticker,
                "form_family": form_family,
                "issuer_cusip": issuer_cusip,
                "issuer_name": issuer_name,
                "filing_date": "2026-07-01",
                "form": "SCHEDULE 13G",
                "rule_designation": "Rule 13d-1(c)",
                "total_percent": 7.4,
                "reporting_persons": [
                    {
                        "cik": "111",
                        "name": "Alpha Capital",
                        "aggregate_amount": 120,
                        "percent_of_class": 7.4,
                        "type_of_reporting_person": "IA",
                    }
                ],
            },
            {
                "ticker": ticker,
                "form_family": form_family,
                "issuer_cusip": issuer_cusip,
                "issuer_name": issuer_name,
                "filing_date": "2026-06-01",
                "form": "SCHEDULE 13G/A",
                "rule_designation": "Rule 13d-1(c)",
                "total_percent": 6.1,
                "reporting_persons": [
                    {
                        "cik": "111",
                        "name": "Alpha Capital",
                        "aggregate_amount": 100,
                        "percent_of_class": 6.1,
                        "type_of_reporting_person": "IA",
                    }
                ],
            },
        ],
    )

    summary = load_latest_13dg_change_summary("PLTR")

    assert summary["status_counts"]["increased"] == 1
    assert summary["changes"][0]["delta_shares"] == 20
    assert "7.4% of class" in str(summary["summary_text"])


def test_load_recent_13dg_for_tickers_collects_all_requested_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_all_rows(table_name: str, filters=None, order=None, max_pages=25):
        ticker = str((filters or {}).get("ticker", "")).replace("eq.", "")
        return [
            {
                "ticker": ticker,
                "form": "SCHEDULE 13G",
                "filing_date": "2026-06-01" if ticker == "NBIS" else "2026-05-01",
                "company_name": f"{ticker} issuer",
                "accession_number": f"{ticker}-1",
                "payload": {},
            }
        ]

    monkeypatch.setattr(data_access, "_fetch_all_rows", fake_fetch_all_rows)

    rows = load_recent_13dg_for_tickers(["CRWV", "NBIS"], limit=10)

    assert [row["ticker"] for row in rows] == ["NBIS", "CRWV"]


def test_load_period_security_rows_resolves_missing_ticker_from_cusip(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_period_security_rows.clear()

    class FakeRepository:
        def resolve_ticker(self, issuer_cusip: str, fallback_ticker: str = "") -> str:
            return "HON" if issuer_cusip == "438516106" else fallback_ticker

    monkeypatch.setattr(data_access, "get_security_identifier_repository", lambda: FakeRepository())
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_total_holding_value",
                "rank": 3,
                "issuer": "HONEYWELL INTL INC",
                "cusip": "438516106",
                "ticker": None,
            }
        ],
    )

    rows = data_access.load_period_security_rows("2026-03-31", "stock")

    assert rows[0]["ticker"] == "HON"


def test_load_recent_13dg_resolves_blank_ticker_from_cusip(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_recent_13dg.clear()

    class FakeRepository:
        def resolve_ticker(self, issuer_cusip: str, fallback_ticker: str = "") -> str:
            return "HHH" if issuer_cusip == "44267D107" else fallback_ticker

    monkeypatch.setattr(data_access, "get_security_identifier_repository", lambda: FakeRepository())
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": "",
                "filing_date": "2026-06-08",
                "company_name": "Howard Hughes Holdings Inc.",
                "form": "SCHEDULE 13D",
                "payload": {"issuer_cusip": "44267D107"},
            }
        ],
    )

    rows = data_access.load_recent_13dg(limit=10)

    assert rows[0]["ticker"] == "HHH"


def test_load_recent_8k_exact_ticker_uses_server_side_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    load_recent_8k.clear()
    captured_filters: list[dict[str, str] | None] = []

    def fake_fetch_all_rows(table_name: str, filters=None, order=None, max_pages=25):
        captured_filters.append(filters)
        return [{"ticker": "NVDA", "company_name": "NVIDIA CORP", "form": "8-K", "filing_date": "2026-07-01"}]

    monkeypatch.setattr(data_access, "_fetch_all_rows", fake_fetch_all_rows)

    rows = data_access.load_recent_8k(search_text="NVDA", limit=5)

    assert rows[0]["ticker"] == "NVDA"
    assert captured_filters == [{"ticker": "eq.NVDA"}]


def test_load_recent_13dg_exact_ticker_uses_server_side_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_recent_13dg.clear()
    captured_filters: list[dict[str, str] | None] = []

    def fake_fetch_all_rows(table_name: str, filters=None, order=None, max_pages=25):
        captured_filters.append(filters)
        return [{"ticker": "NBIS", "company_name": "Nebius Group N.V.", "form": "SCHEDULE 13G", "filing_date": "2026-05-27"}]

    monkeypatch.setattr(data_access, "_fetch_all_rows", fake_fetch_all_rows)

    rows = data_access.load_recent_13dg(search_text="NBIS", limit=5)

    assert rows[0]["ticker"] == "NBIS"
    assert captured_filters == [{"ticker": "eq.NBIS"}]


def test_load_recent_13dg_by_manager_matches_reporting_person_name(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_recent_13dg_by_manager.clear()
    data_access.load_recent_13dg.clear()
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": "NBIS",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-05-27",
                "company_name": "Nebius Group N.V.",
                "accession_number": "nbis-1",
                "payload": {
                    "reporting_persons": [
                        {
                            "name": "Situational Awareness LP",
                            "aggregate_amount": 12410060,
                            "percent_of_class": 5.6,
                        }
                    ]
                },
            },
            {
                "ticker": "CRWV",
                "form": "SCHEDULE 13G/A",
                "filing_date": "2026-05-15",
                "company_name": "CoreWeave, Inc.",
                "accession_number": "crwv-1",
                "payload": {
                    "reporting_persons": [
                        {
                            "name": "Other Fund LP",
                            "aggregate_amount": 100,
                            "percent_of_class": 1.0,
                        }
                    ]
                },
            },
        ],
    )

    rows = load_recent_13dg_by_manager("Situational Awareness LP", limit=10)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "NBIS"


def test_build_manager_13dg_monitor_rows_attaches_current_period_13f_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        data_access,
        "load_13dg_chain",
        lambda ticker, form_family, issuer_cusip, issuer_name, limit=20: [
            {
                "accession_number": "newer",
                "ticker": ticker,
                "form_family": form_family,
                "issuer_cusip": issuer_cusip,
                "issuer_name": issuer_name,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 12410060,
                        "percent_of_class": 5.6,
                    }
                ],
            },
            {
                "accession_number": "older",
                "ticker": ticker,
                "form_family": form_family,
                "issuer_cusip": issuer_cusip,
                "issuer_name": issuer_name,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 10000000,
                        "percent_of_class": 4.9,
                    }
                ],
            },
        ],
    )
    monkeypatch.setattr(
        data_access,
        "load_manager_13f_crosscheck",
        lambda report_period, manager_cik, security_refs, allow_local_fallback=False: {
            "SHAZ|778920306": {
                "ticker": "SHAZ",
                "cusip": "778920306",
                "issuer": "SharonAI Holdings Inc.",
                "status": "unchanged",
                "previous_value_usd": 12000000,
                "current_value_usd": 12000000,
                "value_change_usd": 0,
                "found_in_current": True,
                "found_in_previous": True,
            }
        },
    )
    rows = build_manager_13dg_monitor_rows(
        [
            {
                "ticker": "NBIS",
                "company_name": "Nebius Group N.V.",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-05-27",
                "accession_number": "newer",
                "form_family": "13G",
                "issuer_cusip": "N97284108",
                "issuer_name": "Nebius Group N.V.",
                "total_shares": 12410060,
                "total_percent": 5.6,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 12410060,
                        "percent_of_class": 5.6,
                    }
                ],
            },
            {
                "ticker": "SHAZ",
                "company_name": "SharonAI Holdings Inc.",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-06-29",
                "accession_number": "shaz-newer",
                "form_family": "13G",
                "issuer_cusip": "778920306",
                "issuer_name": "SharonAI Holdings Inc.",
                "total_shares": 5404540,
                "total_percent": 19.9,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 5404540,
                        "percent_of_class": 19.9,
                    }
                ],
            },
        ],
        [
            {
                "ticker": "NBIS",
                "status": "increased",
                "value_change_usd": 25000000,
                "current_value_usd": 85000000,
            }
        ],
        "2026-03-31",
        "2045724",
    )

    assert rows[0]["reported_shares"] == 12410060
    assert rows[0]["rebalance_status"] == "increased"
    assert rows[0]["rebalance_value_change_usd"] == 25000000
    assert rows[0]["filing_change_status"] == "increased"
    assert rows[0]["filing_change_delta_shares"] == 2410060
    assert rows[1]["rebalance_status"] == "unchanged"
    assert rows[1]["rebalance_current_value_usd"] == 12000000
    assert rows[1]["rebalance_value_change_usd"] == 0


def test_build_manager_13dg_monitor_rows_marks_new_filing_when_no_previous_manager_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_access,
        "load_13dg_chain",
        lambda ticker, form_family, issuer_cusip, issuer_name, limit=20: [
            {
                "accession_number": "current",
                "ticker": ticker,
                "form_family": form_family,
                "issuer_cusip": issuer_cusip,
                "issuer_name": issuer_name,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 5404540,
                        "percent_of_class": 19.9,
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(
        data_access,
        "load_manager_13f_crosscheck",
        lambda report_period, manager_cik, security_refs, allow_local_fallback=False: {},
    )

    rows = build_manager_13dg_monitor_rows(
        [
            {
                "ticker": "SHAZ",
                "company_name": "SharonAI Holdings Inc.",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-06-29",
                "accession_number": "current",
                "form_family": "13G",
                "issuer_cusip": "778920306",
                "issuer_name": "SharonAI Holdings Inc.",
                "total_shares": 5404540,
                "total_percent": 19.9,
                "reporting_persons": [
                    {
                        "cik": "2045724",
                        "name": "Situational Awareness LP",
                        "aggregate_amount": 5404540,
                        "percent_of_class": 19.9,
                    }
                ],
            }
        ],
        [],
        "2026-03-31",
        "2045724",
    )

    assert rows[0]["filing_change_status"] == "new"
    assert rows[0]["filing_change_delta_shares"] == 5404540


def test_build_manager_13dg_monitor_rows_marks_absent_latest_13f_as_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        data_access,
        "load_manager_13f_crosscheck",
        lambda report_period, manager_cik, security_refs, allow_local_fallback=False: {},
    )

    rows = build_manager_13dg_monitor_rows(
        [
            {
                "ticker": "NBIS",
                "company_name": "Nebius Group N.V.",
                "form": "SCHEDULE 13G",
                "filing_date": "2026-05-27",
                "issuer_cusip": "N97284108",
                "total_shares": 12410060,
                "total_percent": 5.6,
            }
        ],
        [],
        "2026-03-31",
        "2045724",
    )

    assert rows[0]["rebalance_status"] == "Not reported"
    assert rows[0]["rebalance_current_value_usd"] is None


def test_load_manager_13f_crosscheck_prefers_supabase_mart(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_manager_13f_crosscheck.clear()
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": "SHAZ",
                "cusip": "778920306",
                "issuer": "SharonAI Holdings Inc.",
                "status": "new",
                "previous_value_usd": 0,
                "current_value_usd": 18095535,
                "value_change_usd": 18095535,
                "found_in_current": True,
                "found_in_previous": False,
            }
        ]
        if table_name == "mart_manager_security_latest"
        else [],
    )

    rows = load_manager_13f_crosscheck(
        "2026-03-31",
        "2045724",
        [{"ticker": "SHAZ", "cusip": "778920306"}],
    )

    assert rows["SHAZ|778920306"]["current_value_usd"] == 18095535


def test_load_manager_rebalance_snapshot_resolves_missing_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_manager_rebalance_snapshot.clear()

    class FakeClient:
        def fetch_rows(self, table_name, limit=10, filters=None, order=None):
            if table_name == "mart_manager_rebalance_summary":
                return [
                    {
                        "manager_name": "Citrine Capital LLC",
                        "report_date": "2026-03-31",
                        "previous_report_date": "2025-12-31",
                        "new_count": 1,
                        "increased_count": 0,
                        "decreased_count": 0,
                        "exited_count": 0,
                        "unchanged_count": 0,
                    }
                ]
            return []

    class FakeRepository:
        def resolve_ticker(self, issuer_cusip: str, fallback_ticker: str = "") -> str:
            return "DFAE" if issuer_cusip == "25434V302" else fallback_ticker

    monkeypatch.setattr(data_access, "get_supabase_client", lambda: FakeClient())
    monkeypatch.setattr(data_access, "get_security_identifier_repository", lambda: FakeRepository())
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": None,
                "cusip": "25434V302",
                "issuer": "DIMENSIONAL ETF TRUST - EMGR CRE EQT MNG",
                "status": "new",
                "value_change_usd": 1000,
                "current_value_usd": 1000,
                "previous_value_usd": 0,
            }
        ]
        if table_name == "mart_manager_rebalance_detail"
        else [],
    )

    snapshot = data_access.load_manager_rebalance_snapshot("2026-03-31", "2053242", top_n=24)

    assert snapshot["rows"][0]["ticker"] == "DFAE"


def test_load_manager_rebalance_snapshot_returns_all_rows_when_top_n_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_access.load_manager_rebalance_snapshot.clear()

    class FakeClient:
        def fetch_rows(self, table_name, limit=10, filters=None, order=None):
            if table_name == "mart_manager_rebalance_summary":
                return [
                    {
                        "manager_name": "Situational Awareness LP",
                        "report_date": "2026-03-31",
                        "previous_report_date": "2025-12-31",
                        "new_count": 2,
                        "increased_count": 1,
                        "decreased_count": 1,
                        "exited_count": 0,
                        "unchanged_count": 3,
                    }
                ]
            return []

    monkeypatch.setattr(data_access, "get_supabase_client", lambda: FakeClient())
    monkeypatch.setattr(
        data_access,
        "_fetch_all_rows",
        lambda table_name, filters=None, order=None, max_pages=25: [
            {
                "ticker": "NBIS",
                "cusip": "N97284108",
                "issuer": "Nebius Group N.V.",
                "status": "new",
                "value_change_usd": 1000,
                "current_value_usd": 1000,
                "previous_value_usd": 0,
            },
            {
                "ticker": "SHAZ",
                "cusip": "778920306",
                "issuer": "SharonAI Holdings Inc.",
                "status": "increased",
                "value_change_usd": 500,
                "current_value_usd": 800,
                "previous_value_usd": 300,
            },
        ]
        if table_name == "mart_manager_rebalance_detail"
        else [],
    )

    snapshot = data_access.load_manager_rebalance_snapshot("2026-03-31", "2045724", top_n=None)

    assert [row["ticker"] for row in snapshot["rows"]] == ["NBIS", "SHAZ"]


def test_load_manager_13f_crosscheck_skips_local_zip_when_fallback_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_manager_13f_crosscheck.clear()
    monkeypatch.setattr(data_access, "_fetch_all_rows", lambda table_name, filters=None, order=None, max_pages=25: [])

    rows = data_access.load_manager_13f_crosscheck(
        "2026-03-31",
        "2045724",
        [{"ticker": "NBIS", "cusip": "N97284108"}],
        allow_local_fallback=False,
    )

    assert rows == {}


def test_prewarm_manager_ui_cache_warms_rebalance_and_13dg(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.prewarm_manager_ui_cache.clear()
    calls: list[tuple[str, str, int | None]] = []

    monkeypatch.setattr(
        data_access,
        "load_manager_rebalance_snapshot",
        lambda report_period, manager_cik, top_n=12: calls.append(("rebalance", str(manager_cik), top_n)) or {"rows": [1, 2]},
    )
    monkeypatch.setattr(
        data_access,
        "load_recent_13dg_by_manager",
        lambda manager_name, manager_cik="", tickers=None, limit=20: calls.append(("13dg", str(manager_cik), limit)) or [1],
    )

    result = data_access.prewarm_manager_ui_cache(
        "2026-03-31",
        (("Situational Awareness LP", "2045724"), ("ARK Investment Management LLC", "1697748")),
    )

    assert result == {"managers": 2, "rebalance_rows": 4, "manager_event_rows": 2}
    assert calls == [
        ("rebalance", "2045724", None),
        ("13dg", "2045724", 100),
        ("rebalance", "1697748", None),
        ("13dg", "1697748", 100),
    ]


def test_load_security_history_filters_by_cusip(monkeypatch: pytest.MonkeyPatch) -> None:
    data_access.load_security_history.clear()
    captured_filters: list[dict[str, str] | None] = []

    def fake_fetch_all_rows(table_name: str, filters=None, order=None, max_pages=25):
        captured_filters.append(filters)
        return [{"cusip": "67066G104", "security_type": "stock"}]

    monkeypatch.setattr(data_access, "_fetch_all_rows", fake_fetch_all_rows)

    rows = data_access.load_security_history("67066G104", "stock")

    assert rows[0]["cusip"] == "67066G104"
    assert rows[0]["security_type"] == "stock"
    assert rows[0]["ticker"] == "NVDA"
    assert captured_filters == [{"security_type": "eq.stock", "cusip": "eq.67066G104"}]


def test_build_security_candidates_merges_three_ranking_rows_into_one_security() -> None:
    candidates = build_security_candidates(
        [
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_total_holding_value",
                "rank": 4,
                "issuer": "NVIDIA CORP",
                "cusip": "67066G104",
                "ticker": "NVDA",
                "business_summary": "gpu",
                "new_manager_count": 12,
                "new_entry_total_value_usd": 100,
                "reduced_manager_count": 8,
                "reduced_total_value_usd": 50,
                "holder_manager_count": 1200,
                "total_holding_value_usd": 1000,
            },
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_new_manager_count",
                "rank": 9,
                "issuer": "NVIDIA CORP",
                "cusip": "67066G104",
                "ticker": "NVDA",
                "business_summary": "gpu",
                "new_manager_count": 18,
                "new_entry_total_value_usd": 200,
                "reduced_manager_count": 5,
                "reduced_total_value_usd": 10,
                "holder_manager_count": 1198,
                "total_holding_value_usd": 900,
            },
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_reduced_manager_count",
                "rank": 14,
                "issuer": "NVIDIA CORP",
                "cusip": "67066G104",
                "ticker": "NVDA",
                "business_summary": "gpu",
                "new_manager_count": 10,
                "new_entry_total_value_usd": 60,
                "reduced_manager_count": 21,
                "reduced_total_value_usd": 70,
                "holder_manager_count": 1199,
                "total_holding_value_usd": 950,
            },
        ]
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["ticker"] == "NVDA"
    assert candidate["signal_count"] == 3
    assert candidate["best_rank"] == 4
    assert candidate["ranking_ranks"] == {
        "top_total_holding_value": 4,
        "top_new_manager_count": 9,
        "top_reduced_manager_count": 14,
    }
    assert candidate["new_manager_count"] == 18
    assert candidate["reduced_manager_count"] == 21


def test_build_security_history_digest_deduplicates_by_report_period() -> None:
    digest = build_security_history_digest(
        [
            {
                "report_date": "2026-03-31",
                "ranking_type": "top_total_holding_value",
                "rank": 4,
                "holder_manager_count": 1200,
                "total_holding_value_usd": 1000,
                "new_manager_count": 12,
                "reduced_manager_count": 8,
            },
            {
                "report_date": "2026-03-31",
                "ranking_type": "top_new_manager_count",
                "rank": 9,
                "holder_manager_count": 1198,
                "total_holding_value_usd": 900,
                "new_manager_count": 18,
                "reduced_manager_count": 5,
            },
            {
                "report_date": "2025-12-31",
                "ranking_type": "top_total_holding_value",
                "rank": 7,
                "holder_manager_count": 1100,
                "total_holding_value_usd": 800,
                "new_manager_count": 9,
                "reduced_manager_count": 6,
            },
        ]
    )

    assert [row["report_date"] for row in digest] == ["2026-03-31", "2025-12-31"]
    assert digest[0]["signal_count"] == 2
    assert digest[0]["best_rank"] == 4
    assert "Top holding value #4" in str(digest[0]["ranking_summary"])


def test_load_manager_rebalance_snapshot_prefers_supabase_mart(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def fetch_rows(
            self,
            table_name: str,
            limit: int = 10,
            offset: int = 0,
            filters: dict[str, str] | None = None,
            order: str | None = None,
        ) -> list[dict[str, object]]:
            del limit, offset, order
            if table_name == "mart_manager_rebalance_summary":
                assert filters == {
                    "report_date": "eq.2026-03-31",
                    "manager_cik": "eq.1336528",
                }
                return [
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
                ]
            if table_name == "mart_manager_rebalance_detail":
                assert filters == {
                    "report_date": "eq.2026-03-31",
                    "manager_cik": "eq.1336528",
                }
                return [
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
                ]
            raise AssertionError(table_name)

    load_manager_rebalance_snapshot.clear()
    monkeypatch.setattr(data_access, "get_supabase_client", lambda: FakeClient())

    snapshot = load_manager_rebalance_snapshot("2026-03-31", 1336528, top_n=5)

    assert snapshot["manager_name"] == "Pershing Square Capital Management, L.P."
    assert snapshot["previous_report_date"] == "2025-12-31"
    assert snapshot["status_counts"] == {
        "new": 1,
        "increased": 2,
        "decreased": 1,
        "exited": 0,
        "unchanged": 4,
    }
    assert snapshot["rows"][0]["ticker"] == "NVDA"
