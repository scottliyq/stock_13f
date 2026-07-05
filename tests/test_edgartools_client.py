from pathlib import Path
from types import SimpleNamespace
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.adapters.edgartools_client import EdgarToolsClient


def test_is_available_uses_importlib_util(monkeypatch) -> None:
    monkeypatch.setattr("stock_13f.adapters.edgartools_client.util.find_spec", lambda name: object())
    assert EdgarToolsClient().is_available() is True


def test_build_13dg_payload_extracts_structured_beneficial_ownership_fields() -> None:
    client = EdgarToolsClient()
    filing = SimpleNamespace(
        form="SCHEDULE 13G",
        filing_date="2026-06-26",
        company="MORGAN STANLEY",
        accession_number="0000895421-26-000198",
        homepage_url="https://www.sec.gov/example-filing",
        text_url="https://www.sec.gov/example-filing.txt",
        obj=lambda: SimpleNamespace(
            filing_date="2026-06-26",
            event_date="09/30/2025",
            amendment_number="3",
            total_shares=8472224,
            total_percent=7.5,
            rule_designation="Rule 13d-1(b)",
            issuer_info=SimpleNamespace(name="Zepp Health Corp", cusip="98945L204"),
            security_info=SimpleNamespace(title="Class A Ordinary Shares / American Depositary Receipts", cusip="98945L204"),
            reporting_persons=[
                SimpleNamespace(
                    name="Morgan Stanley",
                    cik="",
                    citizenship="DE",
                    aggregate_amount=8472224,
                    percent_of_class=7.5,
                    type_of_reporting_person="HC",
                    sole_voting_power=0,
                    shared_voting_power=8472128,
                    sole_dispositive_power=0,
                    shared_dispositive_power=8472224,
                    comment=None,
                )
            ],
            items=None,
        ),
    )

    payload = client.build_13dg_payload(filing, "MS")

    assert payload["ticker"] == "MS"
    assert payload["issuer_name"] == "Zepp Health Corp"
    assert payload["issuer_cusip"] == "98945L204"
    assert payload["rule_designation"] == "Rule 13d-1(b)"
    assert payload["total_shares"] == 8472224
    assert payload["total_percent"] == 7.5
    assert payload["reporting_persons"][0]["name"] == "Morgan Stanley"
    assert payload["reporting_persons"][0]["percent_of_class"] == 7.5
    assert "Morgan Stanley" in str(payload["summary"])
    assert "7.5%" in str(payload["summary"])
