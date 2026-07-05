from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.repositories.security_identifiers import SecurityIdentifierRepository


def test_security_identifier_repository_resolves_by_normalized_issuer_name(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    map_path.write_text(
        "cusip,ticker,issuer\n70450Y103,PYPL,PAYPAL HOLDINGS INC\n00165C302,AMC,AMC ENTERTAINMENT HOLDINGS INC\n",
        encoding="utf-8",
    )
    repository = SecurityIdentifierRepository(map_path)

    assert repository.resolve_ticker("", "", "PAYPAL HLDGS INC") == "PYPL"
    assert repository.resolve_ticker("", "", "AMC ENTMT HLDGS INC") == "AMC"


def test_security_identifier_repository_uses_sec_company_tickers_cache(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    map_path.write_text("cusip,ticker,issuer\n", encoding="utf-8")
    company_tickers_path = tmp_path / "sec_company_tickers.json"
    company_tickers_path.write_text(
        '{"0":{"cik_str":1326801,"ticker":"META","title":"Meta Platforms, Inc."}}',
        encoding="utf-8",
    )
    repository = SecurityIdentifierRepository(map_path, company_tickers_path)

    assert repository.resolve_ticker("", "", "META PLATFORMS INC") == "META"


def test_security_identifier_repository_strips_share_class_suffixes(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    map_path.write_text("cusip,ticker,issuer\n", encoding="utf-8")
    company_tickers_path = tmp_path / "sec_company_tickers.json"
    company_tickers_path.write_text(
        '{"0":{"cik_str":1777393,"ticker":"CHPT","title":"ChargePoint Holdings, Inc."}}',
        encoding="utf-8",
    )
    repository = SecurityIdentifierRepository(map_path, company_tickers_path)

    assert repository.resolve_ticker("", "", "CHARGEPOINT HOLDINGS INC - COM CL A") == "CHPT"


def test_security_identifier_repository_supports_multiple_sec_caches(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    map_path.write_text("cusip,ticker,issuer\n", encoding="utf-8")
    primary_path = tmp_path / "sec_company_tickers.json"
    primary_path.write_text("{}", encoding="utf-8")
    exchange_path = tmp_path / "sec_company_tickers_exchange.json"
    exchange_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "name": "Discover Financial Services",
                        "ticker": "DFS",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repository = SecurityIdentifierRepository(map_path, (primary_path, exchange_path))

    assert repository.resolve_ticker("", "", "DISCOVER FINL SVCS") == "DFS"


def test_security_identifier_repository_uses_unique_prefix_match(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    map_path.write_text("cusip,ticker,issuer\n", encoding="utf-8")
    company_tickers_path = tmp_path / "sec_company_tickers.json"
    company_tickers_path.write_text(
        '{"0":{"ticker":"CRH","title":"CRH PUBLIC LTD CO"}}',
        encoding="utf-8",
    )
    repository = SecurityIdentifierRepository(map_path, company_tickers_path)

    assert repository.resolve_ticker("", "", "CRH PLC") == "CRH"
