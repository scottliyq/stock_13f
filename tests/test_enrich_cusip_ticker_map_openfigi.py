import csv
import sys
import urllib.error
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from enrich_cusip_ticker_map_openfigi import (  # noqa: E402
    collect_missing_cusips,
    enrich_cusip_ticker_map_with_openfigi,
    load_existing_map,
    merge_rows,
    MissingCusip,
    query_openfigi_batch_with_retry,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_existing_map_reads_rows_by_cusip(tmp_path: Path) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    write_csv(
        map_path,
        ["cusip", "ticker", "issuer"],
        [
            {"cusip": "037833100", "ticker": "AAPL", "issuer": "APPLE INC"},
            {"cusip": "594918104", "ticker": "MSFT", "issuer": "MICROSOFT CORP"},
        ],
    )

    rows_by_cusip = load_existing_map(map_path)

    assert rows_by_cusip["037833100"]["ticker"] == "AAPL"
    assert rows_by_cusip["594918104"]["issuer"] == "MICROSOFT CORP"


def test_collect_missing_cusips_skips_existing_and_filled_rows(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    write_csv(
        reports_dir / "2026-03-31_13f_quarterly_rebalance_stock_top100.csv",
        [
            "report_date",
            "security_type",
            "ranking_type",
            "rank",
            "issuer",
            "cusip",
            "ticker",
        ],
        [
            {
                "report_date": "2026-03-31",
                "security_type": "stock",
                "ranking_type": "top_new_manager_count",
                "rank": "1",
                "issuer": "APPLE INC (AAPL)",
                "cusip": "037833100",
                "ticker": "AAPL",
            },
            {
                "report_date": "2026-03-31",
                "security_type": "etf",
                "ranking_type": "top_total_holding_value",
                "rank": "1",
                "issuer": "INVESCO QQQ TR - UNIT SER 1",
                "cusip": "46090E103",
                "ticker": "",
            },
        ],
    )

    missing_items = collect_missing_cusips(
        reports_dir=reports_dir,
        existing_rows_by_cusip={"037833100": {"cusip": "037833100", "ticker": "AAPL", "issuer": "APPLE INC"}},
    )

    assert len(missing_items) == 1
    assert missing_items[0].cusip == "46090E103"
    assert missing_items[0].security_type == "etf"


def test_merge_rows_overwrites_or_adds_new_rows() -> None:
    merged = merge_rows(
        existing_rows_by_cusip={"037833100": {"cusip": "037833100", "ticker": "AAPL", "issuer": "APPLE INC"}},
        new_rows=[
            {"cusip": "46090E103", "ticker": "QQQ", "issuer": "INVESCO QQQ TRUST SERIES 1"},
            {"cusip": "037833100", "ticker": "AAPL", "issuer": "APPLE INC"},
        ],
    )

    assert merged["037833100"]["ticker"] == "AAPL"
    assert merged["46090E103"]["ticker"] == "QQQ"


def test_enrich_cusip_ticker_map_with_openfigi_writes_new_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    reports_dir = tmp_path / "reports"
    write_csv(
        reports_dir / "2026-03-31_13f_quarterly_rebalance_etf_top100.csv",
        [
            "report_date",
            "security_type",
            "ranking_type",
            "rank",
            "issuer",
            "cusip",
            "ticker",
        ],
        [
            {
                "report_date": "2026-03-31",
                "security_type": "etf",
                "ranking_type": "top_total_holding_value",
                "rank": "1",
                "issuer": "INVESCO QQQ TR - UNIT SER 1",
                "cusip": "46090E103",
                "ticker": "",
            }
        ],
    )

    def fake_query(batch):
        return [{"cusip": batch[0].cusip, "ticker": "QQQ", "issuer": "INVESCO QQQ TRUST SERIES 1"}]

    monkeypatch.setattr(
        "enrich_cusip_ticker_map_openfigi.query_openfigi_batch",
        fake_query,
    )

    new_rows = enrich_cusip_ticker_map_with_openfigi(
        map_path=map_path,
        reports_dir=reports_dir,
        batch_size=10,
        sleep_seconds=0.0,
    )

    rows_by_cusip = load_existing_map(map_path)
    assert new_rows == 1
    assert rows_by_cusip["46090E103"]["ticker"] == "QQQ"


def test_query_openfigi_batch_with_retry_retries_http_429(monkeypatch) -> None:
    call_count = {"value": 0}

    def fake_query(batch):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise urllib.error.HTTPError(
                url="https://api.openfigi.com/v3/mapping",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=None,
            )
        return [{"cusip": batch[0].cusip, "ticker": "QQQ", "issuer": "INVESCO QQQ TRUST SERIES 1"}]

    monkeypatch.setattr(
        "enrich_cusip_ticker_map_openfigi.query_openfigi_batch",
        fake_query,
    )
    monkeypatch.setattr("enrich_cusip_ticker_map_openfigi.time.sleep", lambda _: None)

    rows = query_openfigi_batch_with_retry(
        batch=[MissingCusip(cusip="46090E103", issuer="INVESCO QQQ TR - UNIT SER 1", security_type="etf")],
        sleep_seconds=0.0,
        max_retries=2,
    )

    assert call_count["value"] == 2
    assert rows[0]["ticker"] == "QQQ"


def test_enrich_cusip_ticker_map_with_openfigi_skips_rate_limited_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    map_path = tmp_path / "cusip_ticker_map.csv"
    reports_dir = tmp_path / "reports"
    write_csv(
        reports_dir / "2026-03-31_13f_quarterly_rebalance_etf_top100.csv",
        [
            "report_date",
            "security_type",
            "ranking_type",
            "rank",
            "issuer",
            "cusip",
            "ticker",
        ],
        [
            {
                "report_date": "2026-03-31",
                "security_type": "etf",
                "ranking_type": "top_total_holding_value",
                "rank": "1",
                "issuer": "INVESCO QQQ TR - UNIT SER 1",
                "cusip": "46090E103",
                "ticker": "",
            }
        ],
    )

    def always_rate_limited(_batch):
        raise urllib.error.HTTPError(
            url="https://api.openfigi.com/v3/mapping",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "0"},
            fp=None,
        )

    monkeypatch.setattr(
        "enrich_cusip_ticker_map_openfigi.query_openfigi_batch",
        always_rate_limited,
    )
    monkeypatch.setattr("enrich_cusip_ticker_map_openfigi.time.sleep", lambda _: None)

    new_rows = enrich_cusip_ticker_map_with_openfigi(
        map_path=map_path,
        reports_dir=reports_dir,
        batch_size=10,
        sleep_seconds=0.0,
    )

    assert new_rows == 0
    assert map_path.exists()
    assert load_existing_map(map_path) == {}
