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


def test_build_13f_payload_parses_and_aggregates_information_table() -> None:
    xml = """
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>APPLE INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>037833100</cusip>
        <value>100</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <putCall></putCall>
        <investmentDiscretion>SOLE</investmentDiscretion>
      </infoTable>
      <infoTable>
        <nameOfIssuer>APPLE INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>037833100</cusip>
        <value>50</value>
        <shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <putCall></putCall>
        <investmentDiscretion>SOLE</investmentDiscretion>
      </infoTable>
    </informationTable>
    """
    filing = SimpleNamespace(
        header=SimpleNamespace(period_of_report="2026-06-30"),
        form="13F-HR",
        filing_date="2026-07-23",
        company="CITRINE CAPITAL LLC",
        cik=2053242,
        accession_number="0001754960-26-000616",
        homepage_url="https://www.sec.gov/example-13f",
        attachments=[SimpleNamespace(document_type="INFORMATION TABLE", document="infotable.xml", content=xml)],
    )

    payload = EdgarToolsClient().build_13f_payload(filing)

    assert payload["report_date"] == "2026-06-30"
    assert payload["manager_cik"] == 2053242
    assert payload["payload"]["holdings"] == [
        {
            "name_of_issuer": "APPLE INC",
            "title_of_class": "COM",
            "cusip": "037833100",
            "put_call": "",
            "value_usd": 150,
            "shares_or_principal": 15,
            "amount_type": "SH",
            "investment_discretion": "SOLE",
        }
    ]


def test_build_13f_payload_from_submission_text_uses_conformed_period(monkeypatch) -> None:
    xml = """
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>594918104</cusip>
        <value>250</value>
        <shrsOrPrnAmt><sshPrnamt>25</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        <putCall></putCall>
        <investmentDiscretion>SOLE</investmentDiscretion>
      </infoTable>
    </informationTable>
    """
    submission = f"""
CONFORMED PERIOD OF REPORT: 20260630
<DOCUMENT>
<TYPE>INFORMATION TABLE
<TEXT>
{xml}
</TEXT>
</DOCUMENT>
"""

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self) -> bytes:
            return submission.encode("utf-8")

    monkeypatch.setattr("stock_13f.adapters.edgartools_client.urlopen", lambda request, timeout: FakeResponse())
    filing = SimpleNamespace(
        text_url="https://www.sec.gov/example-submission.txt",
        form="13F-HR",
        filing_date="2026-07-08",
        company="Example Capital",
        cik=1234567,
        accession_number="0001234567-26-000001",
        homepage_url="https://www.sec.gov/example-filing",
    )

    payload = EdgarToolsClient().build_13f_payload(filing, user_agent="test@example.com")

    assert payload["report_date"] == "2026-06-30"
    assert payload["payload"]["holdings"][0]["cusip"] == "594918104"
