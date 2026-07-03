#!/usr/bin/env python3
"""Export full-universe quarterly 13F rebalance leaderboards to CSV files."""

import argparse
import csv
import io
import logging
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from zipfile import ZipFile

from monitor_13f_ai import (
    DEFAULT_USER_AGENT,
    FORM_TYPES,
    MonitorError,
    business_profile,
    http_get_bytes,
    normalize_value,
    ticker_for_issuer,
)
from enrich_cusip_ticker_map_openfigi import enrich_cusip_ticker_map_with_openfigi


LOGGER = logging.getLogger("export_13f_quarterly_rebalance_csv")
DEFAULT_TOP_LIMIT = 100
REPO_ROOT = Path(__file__).resolve().parents[1]
CUSIP_TICKER_MAP_PATH = REPO_ROOT / "data" / "cusip_ticker_map.csv"
DATASET_REPORT_TYPES = {"13F HOLDINGS REPORT", "13F COMBINATION REPORT"}
QUARTER_END_MONTH_DAYS = {
    1: (3, 31),
    2: (6, 30),
    3: (9, 30),
    4: (12, 31),
}
MONTH_ABBREVIATIONS = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dec",
}
GENERIC_SECURITY_TITLES = {
    "ADR",
    "ADS",
    "CL A",
    "CL B",
    "CL C",
    "COM",
    "COM NEW",
    "COMMON STOCK",
    "NEW",
    "ORD",
    "ORD SHS",
    "ORDINARY SHARES",
    "SHS",
    "SPONSORED ADR",
}
ETF_ISSUER_FRAGMENTS = (
    "DIREXION",
    "DIMENSIONAL ETF",
    "FIRST TR",
    "INNOVATOR ETFS",
    "INVESCO ACTI",
    "INVESCO DB",
    "INVESCO EXCHANGE",
    "INVESCO QQQ",
    "ISHARES",
    "J P MORGAN EXCHANGE",
    "PROSHARES",
    "SCHWAB STRATEGIC TR",
    "SELECT SECTOR SPDR",
    "SPDR",
    "SPROTT ASSET MANAGEMENT",
    "VANECK ETF",
    "VANGUARD",
    "WISDOMTREE",
)
ETF_TITLE_FRAGMENTS = (
    "ETF",
    "EXCHANGE TRADED",
    "INDEX",
    "TR UNIT",
    "UNIT SER",
)
SECURITY_TYPES = ("stock", "etf")


@dataclass(frozen=True)
class QuarterlySecuritySummary:
    report_date: str
    security_key: str
    security_type: str
    issuer_name: str
    cusip: str
    ticker: str
    business_summary: str
    new_manager_count: int
    new_entry_total_value_usd: int
    reduced_manager_count: int
    reduced_total_value_usd: int
    holder_manager_count: int
    total_holding_value_usd: int


@dataclass
class SummaryAccumulator:
    report_date: str
    security_key: str
    security_type: str
    issuer_name: str
    cusip: str
    ticker: str
    business_summary: str
    new_manager_count: int = 0
    new_entry_total_value_usd: int = 0
    reduced_manager_count: int = 0
    reduced_total_value_usd: int = 0
    holder_manager_count: int = 0
    total_holding_value_usd: int = 0

    def to_summary(self) -> QuarterlySecuritySummary:
        return QuarterlySecuritySummary(
            report_date=self.report_date,
            security_key=self.security_key,
            security_type=self.security_type,
            issuer_name=self.issuer_name,
            cusip=self.cusip,
            ticker=self.ticker,
            business_summary=self.business_summary,
            new_manager_count=self.new_manager_count,
            new_entry_total_value_usd=self.new_entry_total_value_usd,
            reduced_manager_count=self.reduced_manager_count,
            reduced_total_value_usd=self.reduced_total_value_usd,
            holder_manager_count=self.holder_manager_count,
            total_holding_value_usd=self.total_holding_value_usd,
        )


@dataclass(frozen=True)
class FilingSelection:
    accession_number: str
    cik: str
    manager_name: str
    filing_date: str
    report_date: str
    amendment_number: int


@dataclass
class ManagerHolding:
    name_of_issuer: str
    title_of_class: str
    cusip: str
    put_call: str
    value_usd: int


@dataclass
class QuarterData:
    report_date: str
    manager_names_by_cik: dict[str, str]
    holdings_by_cik: dict[str, dict[str, ManagerHolding]]


def quarter_end_for_date(reference_date: date) -> date:
    quarter = ((reference_date.month - 1) // 3) + 1
    month, day = QUARTER_END_MONTH_DAYS[quarter]
    return date(reference_date.year, month, day)


def previous_quarter_end(report_date: date) -> date:
    if report_date.month == 3:
        return date(report_date.year - 1, 12, 31)
    if report_date.month == 6:
        return date(report_date.year, 3, 31)
    if report_date.month == 9:
        return date(report_date.year, 6, 30)
    return date(report_date.year, 9, 30)


def latest_available_report_date(reference_date: date) -> str:
    current_quarter_end = quarter_end_for_date(reference_date)
    while current_quarter_end + timedelta(days=45) > reference_date:
        current_quarter_end = previous_quarter_end(current_quarter_end)
    return current_quarter_end.isoformat()


def recent_report_dates(latest_report_date: str, quarter_count: int) -> list[str]:
    report_dates = [latest_report_date]
    current = date.fromisoformat(latest_report_date)
    while len(report_dates) < quarter_count:
        current = previous_quarter_end(current)
        report_dates.append(current.isoformat())
    return report_dates


def dataset_url_for_report_date(report_date: str) -> str:
    report_date_value = date.fromisoformat(report_date)
    if report_date_value.month == 3:
        start_date = date(report_date_value.year, 3, 1)
        end_date = date(report_date_value.year, 5, 31)
    elif report_date_value.month == 6:
        start_date = date(report_date_value.year, 6, 1)
        end_date = date(report_date_value.year, 8, 31)
    elif report_date_value.month == 9:
        start_date = date(report_date_value.year, 9, 1)
        end_date = date(report_date_value.year, 11, 30)
    elif report_date_value.month == 12:
        start_date = date(report_date_value.year, 12, 1)
        february_last_day = monthrange(report_date_value.year + 1, 2)[1]
        end_date = date(report_date_value.year + 1, 2, february_last_day)
    else:
        raise MonitorError(f"Unsupported 13F report date: {report_date}")
    return (
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
        f"{dataset_fragment(start_date)}-{dataset_fragment(end_date)}_form13f.zip"
    )


def dataset_fragment(value: date) -> str:
    return f"{value.day:02d}{MONTH_ABBREVIATIONS[value.month]}{value.year}"


def dataset_zip_path(cache_dir: Path, report_date: str) -> Path:
    return cache_dir / "zip" / f"{report_date}_form13f.zip"


def ensure_dataset_zip(report_date: str, cache_dir: Path, user_agent: str) -> Path:
    zip_path = dataset_zip_path(cache_dir, report_date)
    if zip_path.exists():
        return zip_path
    url = dataset_url_for_report_date(report_date)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("downloading_13f_dataset", extra={"report_date": report_date, "url": url})
    payload = http_get_bytes(url, user_agent)
    zip_path.write_bytes(payload)
    return zip_path


def security_display_name(name_of_issuer: str, title_of_class: str) -> str:
    normalized_title = title_of_class.strip()
    if not normalized_title:
        return name_of_issuer
    upper_title = normalized_title.upper()
    if upper_title in GENERIC_SECURITY_TITLES or upper_title.startswith("CLASS ") or upper_title.startswith("CL "):
        return name_of_issuer
    return f"{name_of_issuer} - {normalized_title}"


def normalize_cusip(cusip: str) -> str:
    return cusip.strip().upper()


@lru_cache(maxsize=1)
def load_cusip_ticker_map() -> dict[str, str]:
    if not CUSIP_TICKER_MAP_PATH.exists():
        return {}
    mapping: dict[str, str] = {}
    with CUSIP_TICKER_MAP_PATH.open("r", encoding="utf-8-sig", newline="") as input_file:
        for row in csv.DictReader(input_file):
            cusip = normalize_cusip(row.get("cusip", ""))
            ticker = row.get("ticker", "").strip().upper()
            if not cusip or not ticker:
                continue
            mapping[cusip] = ticker
    return mapping


def ticker_for_security(cusip: str, name_of_issuer: str) -> str:
    ticker = load_cusip_ticker_map().get(normalize_cusip(cusip))
    if ticker:
        return ticker
    return ticker_for_issuer(name_of_issuer)


def display_issuer_with_ticker(display_name: str, ticker: str) -> str:
    if not ticker:
        return display_name
    return f"{display_name} ({ticker})"


def security_identity(cusip: str, name_of_issuer: str, title_of_class: str) -> tuple[str, str]:
    ticker = ticker_for_security(cusip, name_of_issuer)
    display_name = security_display_name(name_of_issuer, title_of_class)
    if ticker:
        return display_issuer_with_ticker(display_name, ticker.upper()), ticker.upper()
    return display_name, ""


def classify_security_type(name_of_issuer: str, title_of_class: str) -> str:
    upper_issuer = name_of_issuer.upper()
    upper_title = title_of_class.upper()
    if any(fragment in upper_issuer for fragment in ETF_ISSUER_FRAGMENTS):
        return "etf"
    if any(fragment in upper_title for fragment in ETF_TITLE_FRAGMENTS):
        return "etf"
    return "stock"


def business_summary_for_security(
    security_type: str,
    name_of_issuer: str,
    title_of_class: str,
) -> str:
    business, _ = business_profile(name_of_issuer)
    if not business.startswith("暂未在内置规则中识别出详细业务描述"):
        return business
    if security_type == "etf":
        display_name = security_display_name(name_of_issuer, title_of_class)
        return f"ETF/基金产品，主要提供对 {display_name} 所代表资产、行业或指数的组合敞口。"
    return "公开股票/权益证券，主营业务需结合公司最新披露进一步核实。"


def holding_security_key(cusip: str, put_call: str, title_of_class: str) -> str:
    normalized_put_call = put_call or "COMMON"
    return f"{cusip}|{normalized_put_call}|{title_of_class}".upper()


def read_zip_tsv_rows(zip_path: Path, member_name: str) -> Iterator[dict[str, str]]:
    with ZipFile(zip_path) as archive:
        resolved_member_name = resolve_zip_member_name(archive, member_name)
        with archive.open(resolved_member_name) as raw_file:
            text_file = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text_file, delimiter="\t")
            yield from reader


def resolve_zip_member_name(archive: ZipFile, member_name: str) -> str:
    if member_name in archive.namelist():
        return member_name
    matches = [name for name in archive.namelist() if name.endswith(f"/{member_name}")]
    if len(matches) == 1:
        return matches[0]
    raise MonitorError(f"Unable to locate {member_name} in {archive.filename}")


def parse_sec_date(value: str) -> str:
    return datetime.strptime(value, "%d-%b-%Y").date().isoformat()


def load_coverpage_rows(zip_path: Path, report_date: str) -> dict[str, dict[str, str]]:
    coverpage_rows: dict[str, dict[str, str]] = {}
    for row in read_zip_tsv_rows(zip_path, "COVERPAGE.tsv"):
        if parse_sec_date(row["REPORTCALENDARORQUARTER"]) != report_date:
            continue
        if row["REPORTTYPE"] not in DATASET_REPORT_TYPES:
            continue
        coverpage_rows[row["ACCESSION_NUMBER"]] = row
    return coverpage_rows


def select_latest_filings(zip_path: Path, report_date: str) -> dict[str, FilingSelection]:
    coverpage_rows = load_coverpage_rows(zip_path, report_date)
    latest_by_cik: dict[str, FilingSelection] = {}
    for row in read_zip_tsv_rows(zip_path, "SUBMISSION.tsv"):
        if row["SUBMISSIONTYPE"] not in FORM_TYPES:
            continue
        if parse_sec_date(row["PERIODOFREPORT"]) != report_date:
            continue
        coverpage_row = coverpage_rows.get(row["ACCESSION_NUMBER"])
        if coverpage_row is None:
            continue
        amendment_number = int(coverpage_row["AMENDMENTNO"] or "0")
        selection = FilingSelection(
            accession_number=row["ACCESSION_NUMBER"],
            cik=row["CIK"],
            manager_name=coverpage_row["FILINGMANAGER_NAME"],
            filing_date=parse_sec_date(row["FILING_DATE"]),
            report_date=report_date,
            amendment_number=amendment_number,
        )
        existing = latest_by_cik.get(selection.cik)
        if existing is None or (
            selection.filing_date,
            selection.amendment_number,
            selection.accession_number,
        ) > (
            existing.filing_date,
            existing.amendment_number,
            existing.accession_number,
        ):
            latest_by_cik[selection.cik] = selection
    return latest_by_cik


def load_quarter_data(zip_path: Path, report_date: str) -> QuarterData:
    selected_by_cik = select_latest_filings(zip_path, report_date)
    selected_accessions = {
        selection.accession_number: selection for selection in selected_by_cik.values()
    }
    holdings_by_cik: dict[str, dict[str, ManagerHolding]] = {}
    for row in read_zip_tsv_rows(zip_path, "INFOTABLE.tsv"):
        selection = selected_accessions.get(row["ACCESSION_NUMBER"])
        if selection is None:
            continue
        value_usd = normalize_value(int(row["VALUE"] or "0"), report_date)
        security_key = holding_security_key(
            cusip=row["CUSIP"],
            put_call=row["PUTCALL"],
            title_of_class=row["TITLEOFCLASS"],
        )
        manager_holdings = holdings_by_cik.setdefault(selection.cik, {})
        existing = manager_holdings.get(security_key)
        if existing is None:
            manager_holdings[security_key] = ManagerHolding(
                name_of_issuer=row["NAMEOFISSUER"],
                title_of_class=row["TITLEOFCLASS"],
                cusip=row["CUSIP"],
                put_call=row["PUTCALL"],
                value_usd=value_usd,
            )
            continue
        existing.value_usd += value_usd
    manager_names_by_cik = {
        cik: selection.manager_name for cik, selection in selected_by_cik.items()
    }
    LOGGER.info(
        "quarter_data_loaded",
        extra={
            "report_date": report_date,
            "zip_path": str(zip_path),
            "manager_count": len(manager_names_by_cik),
            "zip_name": Path(urlparse(str(zip_path)).path).name,
        },
    )
    return QuarterData(
        report_date=report_date,
        manager_names_by_cik=manager_names_by_cik,
        holdings_by_cik=holdings_by_cik,
    )


def get_or_create_accumulator(
    accumulators: dict[str, SummaryAccumulator],
    report_date: str,
    security_key: str,
    security_type: str,
    issuer_name: str,
    cusip: str,
    ticker: str,
    business_summary: str,
) -> SummaryAccumulator:
    accumulator = accumulators.get(security_key)
    if accumulator is not None:
        return accumulator
    accumulator = SummaryAccumulator(
        report_date=report_date,
        security_key=security_key,
        security_type=security_type,
        issuer_name=issuer_name,
        cusip=cusip,
        ticker=ticker,
        business_summary=business_summary,
    )
    accumulators[security_key] = accumulator
    return accumulator


def summarize_quarter(
    current_data: QuarterData,
    previous_data: QuarterData,
) -> list[QuarterlySecuritySummary]:
    accumulators: dict[str, SummaryAccumulator] = {}
    all_ciks = set(current_data.holdings_by_cik) | set(previous_data.holdings_by_cik)
    for cik in all_ciks:
        current_holdings = current_data.holdings_by_cik.get(cik, {})
        previous_holdings = previous_data.holdings_by_cik.get(cik, {})
        all_security_keys = set(current_holdings) | set(previous_holdings)
        for security_key in all_security_keys:
            current_holding = current_holdings.get(security_key)
            previous_holding = previous_holdings.get(security_key)
            holding = current_holding or previous_holding
            if holding is None:
                continue
            issuer_name, ticker = security_identity(
                holding.cusip,
                holding.name_of_issuer,
                holding.title_of_class,
            )
            security_type = classify_security_type(
                holding.name_of_issuer,
                holding.title_of_class,
            )
            business_summary = business_summary_for_security(
                security_type,
                holding.name_of_issuer,
                holding.title_of_class,
            )
            accumulator = get_or_create_accumulator(
                accumulators=accumulators,
                report_date=current_data.report_date,
                security_key=security_key,
                security_type=security_type,
                issuer_name=issuer_name,
                cusip=holding.cusip,
                ticker=ticker,
                business_summary=business_summary,
            )
            if current_holding is not None:
                accumulator.holder_manager_count += 1
                accumulator.total_holding_value_usd += current_holding.value_usd
            if current_holding is not None and previous_holding is None:
                accumulator.new_manager_count += 1
                accumulator.new_entry_total_value_usd += current_holding.value_usd
            if previous_holding is not None:
                current_value_usd = current_holding.value_usd if current_holding is not None else 0
                reduced_value_usd = previous_holding.value_usd - current_value_usd
                if reduced_value_usd > 0:
                    accumulator.reduced_manager_count += 1
                    accumulator.reduced_total_value_usd += reduced_value_usd
    LOGGER.info(
        "quarter_summarized",
        extra={
            "report_date": current_data.report_date,
            "manager_count": len(current_data.holdings_by_cik),
            "security_count": len(accumulators),
        },
    )
    return [accumulator.to_summary() for accumulator in accumulators.values()]


def build_csv_rows(
    report_date: str,
    summaries: list[QuarterlySecuritySummary],
    security_type: str,
    top_limit: int,
) -> list[dict[str, str | int]]:
    filtered_summaries = [
        summary for summary in summaries if summary.security_type == security_type
    ]
    top_new_entries = sorted(
        [summary for summary in filtered_summaries if summary.new_manager_count > 0],
        key=lambda item: (
            -item.new_manager_count,
            -item.new_entry_total_value_usd,
            -item.total_holding_value_usd,
            item.security_key,
        ),
    )[:top_limit]
    top_total_values = sorted(
        filtered_summaries,
        key=lambda item: (
            -item.total_holding_value_usd,
            -item.holder_manager_count,
            -item.new_manager_count,
            item.security_key,
        ),
    )[:top_limit]
    top_reductions = sorted(
        [summary for summary in filtered_summaries if summary.reduced_manager_count > 0],
        key=lambda item: (
            -item.reduced_manager_count,
            -item.reduced_total_value_usd,
            -item.total_holding_value_usd,
            item.security_key,
        ),
    )[:top_limit]

    rows: list[dict[str, str | int]] = []
    for ranking_type, leaderboard in (
        ("top_new_manager_count", top_new_entries),
        ("top_total_holding_value", top_total_values),
        ("top_reduced_manager_count", top_reductions),
    ):
        for rank, summary in enumerate(leaderboard, start=1):
            rows.append(
                {
                    "report_date": report_date,
                    "security_type": security_type,
                    "ranking_type": ranking_type,
                    "rank": rank,
                    "issuer": summary.issuer_name,
                    "cusip": summary.cusip,
                    "ticker": summary.ticker,
                    "business_summary": summary.business_summary,
                    "new_manager_count": summary.new_manager_count,
                    "new_entry_total_value_usd": summary.new_entry_total_value_usd,
                    "reduced_manager_count": summary.reduced_manager_count,
                    "reduced_total_value_usd": summary.reduced_total_value_usd,
                    "holder_manager_count": summary.holder_manager_count,
                    "total_holding_value_usd": summary.total_holding_value_usd,
                }
            )
    return rows


def quarter_csv_path(
    output_dir: Path,
    report_date: str,
    security_type: str,
    top_limit: int,
) -> Path:
    return output_dir / f"{report_date}_13f_quarterly_rebalance_{security_type}_top{top_limit}.csv"


def write_quarter_csv(
    output_dir: Path,
    report_date: str,
    security_type: str,
    top_limit: int,
    rows: list[dict[str, str | int]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = quarter_csv_path(
        output_dir=output_dir,
        report_date=report_date,
        security_type=security_type,
        top_limit=top_limit,
    )
    fieldnames = [
        "report_date",
        "security_type",
        "ranking_type",
        "rank",
        "issuer",
        "cusip",
        "ticker",
        "business_summary",
        "new_manager_count",
        "new_entry_total_value_usd",
        "reduced_manager_count",
        "reduced_total_value_usd",
        "holder_manager_count",
        "total_holding_value_usd",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    LOGGER.info("quarter_csv_written", extra={"path": str(output_path), "rows": len(rows)})
    return output_path


def remove_legacy_quarter_csv(output_dir: Path, report_date: str) -> None:
    legacy_path = output_dir / f"{report_date}_13f_quarterly_rebalance_top20.csv"
    if not legacy_path.exists():
        return
    legacy_path.unlink()
    LOGGER.info("legacy_quarter_csv_removed", extra={"path": str(legacy_path)})


def remove_stale_ranked_csvs(
    output_dir: Path,
    report_date: str,
    security_type: str,
    top_limit: int,
) -> None:
    keep_path = quarter_csv_path(
        output_dir=output_dir,
        report_date=report_date,
        security_type=security_type,
        top_limit=top_limit,
    )
    pattern = f"{report_date}_13f_quarterly_rebalance_{security_type}_top*.csv"
    for path in output_dir.glob(pattern):
        if path == keep_path:
            continue
        path.unlink()
        LOGGER.info("stale_ranked_csv_removed", extra={"path": str(path)})


def refresh_report_csvs(output_dir: Path) -> list[Path]:
    refreshed_paths: list[Path] = []
    report_paths = sorted(output_dir.glob("*_13f_quarterly_rebalance_*_top*.csv"))
    for path in report_paths:
        with path.open("r", encoding="utf-8-sig", newline="") as input_file:
            rows = list(csv.DictReader(input_file))
            fieldnames = list(rows[0].keys()) if rows else []
        if not rows:
            continue

        changed = False
        filtered_rows: list[dict[str, str]] = []
        for row in rows:
            core_fields = (
                "report_date",
                "security_type",
                "ranking_type",
                "rank",
                "issuer",
                "cusip",
                "ticker",
                "new_manager_count",
                "new_entry_total_value_usd",
                "reduced_manager_count",
                "reduced_total_value_usd",
                "holder_manager_count",
                "total_holding_value_usd",
            )
            if not any((row.get(field, "") or "").strip() for field in core_fields):
                changed = True
                continue

            issuer_without_ticker = re.sub(
                r" \([A-Z][A-Z0-9.\-]*\)$",
                "",
                row["issuer"],
            ).strip()
            resolved_ticker = ticker_for_security(row["cusip"], issuer_without_ticker)
            if resolved_ticker and row.get("ticker", "").strip() != resolved_ticker:
                row["ticker"] = resolved_ticker
                row["issuer"] = f"{issuer_without_ticker} ({resolved_ticker})"
                changed = True
            resolved_business_summary = business_summary_for_security(
                row["security_type"],
                issuer_without_ticker,
                "",
            )
            if row.get("business_summary", "") != resolved_business_summary:
                row["business_summary"] = resolved_business_summary
                changed = True
            filtered_rows.append(row)

        if changed:
            with path.open("w", encoding="utf-8-sig", newline="") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(filtered_rows)
        refreshed_paths.append(path)
    return refreshed_paths


def export_quarterly_rebalance_csvs(
    dataset_cache_dir: Path,
    output_dir: Path,
    user_agent: str,
    quarter_count: int,
    top_limit: int,
    latest_report_date: str | None,
    skip_download: bool,
) -> list[Path]:
    resolved_latest_report_date = latest_report_date or latest_available_report_date(date.today())
    target_report_dates_desc = recent_report_dates(resolved_latest_report_date, quarter_count)
    comparison_report_dates_asc = list(
        reversed(recent_report_dates(resolved_latest_report_date, quarter_count + 1))
    )

    if not skip_download:
        for report_date in comparison_report_dates_asc:
            ensure_dataset_zip(report_date=report_date, cache_dir=dataset_cache_dir, user_agent=user_agent)

    output_paths_by_report_and_type: dict[tuple[str, str], Path] = {}
    previous_quarter_data: QuarterData | None = None
    for report_date in comparison_report_dates_asc:
        zip_path = ensure_dataset_zip(report_date=report_date, cache_dir=dataset_cache_dir, user_agent=user_agent)
        current_quarter_data = load_quarter_data(zip_path=zip_path, report_date=report_date)
        if previous_quarter_data is not None and report_date in target_report_dates_desc:
            summaries = summarize_quarter(
                current_data=current_quarter_data,
                previous_data=previous_quarter_data,
            )
            for security_type in SECURITY_TYPES:
                rows = build_csv_rows(
                    report_date=report_date,
                    summaries=summaries,
                    security_type=security_type,
                    top_limit=top_limit,
                )
                output_paths_by_report_and_type[(report_date, security_type)] = write_quarter_csv(
                    output_dir=output_dir,
                    report_date=report_date,
                    security_type=security_type,
                    top_limit=top_limit,
                    rows=rows,
                )
                remove_stale_ranked_csvs(
                    output_dir=output_dir,
                    report_date=report_date,
                    security_type=security_type,
                    top_limit=top_limit,
                )
            remove_legacy_quarter_csv(output_dir=output_dir, report_date=report_date)
        previous_quarter_data = current_quarter_data
    return [
        output_paths_by_report_and_type[(report_date, security_type)]
        for report_date in target_report_dates_desc
        for security_type in SECURITY_TYPES
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export full-universe quarterly 13F rebalance leaderboards to CSV.")
    parser.add_argument("--dataset-cache-dir", type=Path, default=REPO_ROOT / "data" / "13f_universe")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "13_following" / "data",
    )
    parser.add_argument("--quarters", type=int, default=4)
    parser.add_argument("--top-limit", type=int, default=DEFAULT_TOP_LIMIT)
    parser.add_argument("--latest-report-date")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--enrich-openfigi", action="store_true")
    parser.add_argument("--openfigi-batch-size", type=int, default=10)
    parser.add_argument("--openfigi-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    output_paths = export_quarterly_rebalance_csvs(
        dataset_cache_dir=args.dataset_cache_dir,
        output_dir=args.output_dir,
        user_agent=args.user_agent,
        quarter_count=args.quarters,
        top_limit=args.top_limit,
        latest_report_date=args.latest_report_date,
        skip_download=args.skip_download,
    )
    if args.enrich_openfigi:
        enrich_cusip_ticker_map_with_openfigi(
            map_path=CUSIP_TICKER_MAP_PATH,
            reports_dir=args.output_dir,
            batch_size=args.openfigi_batch_size,
            sleep_seconds=args.openfigi_sleep_seconds,
        )
        output_paths = refresh_report_csvs(args.output_dir)
    for path in output_paths:
        LOGGER.info("exported_file", extra={"path": str(path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
