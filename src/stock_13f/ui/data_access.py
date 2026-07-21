"""Cached data access helpers for the Streamlit research UI."""

from dataclasses import asdict
from pathlib import Path
import re

import streamlit as st

from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.manager_registry import list_default_managers
from stock_13f.repositories.security_identifiers import SecurityIdentifierRepository


REPORTS_PAGE_SIZE = 1000
RANKING_TYPE_LABELS = {
    "top_new_manager_count": "Top new managers",
    "top_total_holding_value": "Top holding value",
    "top_reduced_manager_count": "Top reduced managers",
}


@st.cache_resource(show_spinner=False)
def get_settings() -> Settings:
    return Settings.load()


@st.cache_resource(show_spinner=False)
def get_supabase_client():
    return build_supabase_client(get_settings(), allow_publishable_fallback=True)


@st.cache_resource(show_spinner=False)
def get_security_identifier_repository() -> SecurityIdentifierRepository:
    settings = get_settings()
    return SecurityIdentifierRepository(
        settings.paths.data_dir / "cusip_ticker_map.csv",
        (
            settings.paths.data_dir / "sec_company_tickers.json",
            settings.paths.data_dir / "sec_company_tickers_exchange.json",
        ),
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_checkpoint_statuses() -> list[dict[str, object]]:
    client = get_supabase_client()
    if client is None:
        return []
    try:
        return client.fetch_rows(
            "sync_checkpoints",
            limit=20,
            offset=0,
            order="finished_at.desc",
        )
    except SupabaseError:
        return []


def _fetch_all_rows(
    table_name: str,
    filters: dict[str, str] | None = None,
    order: str | None = None,
    max_pages: int = 25,
) -> list[dict[str, object]]:
    client = get_supabase_client()
    if client is None:
        return []
    rows: list[dict[str, object]] = []
    offset = 0
    try:
        for _ in range(max_pages):
            page = client.fetch_rows(
                table_name,
                limit=REPORTS_PAGE_SIZE,
                offset=offset,
                filters=filters,
                order=order,
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < REPORTS_PAGE_SIZE:
                break
            offset += REPORTS_PAGE_SIZE
    except SupabaseError:
        return []
    return rows


def split_focus_terms(focus_areas: str) -> list[str]:
    raw_terms = re.split(r"[、，,/·]| and | AND |\s+", focus_areas)
    terms: list[str] = []
    for term in raw_terms:
        cleaned = term.strip()
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms


def _focus_score(row: dict[str, object], focus_terms: list[str]) -> int:
    if not focus_terms:
        return 0
    haystack = " ".join(
        [
            str(row.get("ticker", "") or "").lower(),
            str(row.get("issuer", "") or "").lower(),
            str(row.get("business_summary", "") or "").lower(),
        ]
    )
    score = 0
    for term in focus_terms:
        if term.lower() in haystack:
            score += 1
    return score


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _security_row_key(row: dict[str, object]) -> str:
    cusip = str(row.get("cusip", "") or "").strip().upper()
    ticker = str(row.get("ticker", "") or "").strip().upper()
    issuer = str(row.get("issuer", "") or "").strip().upper()
    return cusip or f"{ticker}|{issuer}"


def _search_matches(row: dict[str, object], normalized_search: str) -> bool:
    if not normalized_search:
        return True
    return (
        normalized_search in str(row.get("ticker", "") or "").lower()
        or normalized_search in str(row.get("issuer", "") or "").lower()
        or normalized_search in str(row.get("business_summary", "") or "").lower()
    )


def _normalize_ticker_query(value: str) -> str:
    return re.sub(r"[^A-Z.-]", "", value.strip().upper())


def _is_exact_ticker_query(value: str) -> bool:
    normalized = _normalize_ticker_query(value)
    return bool(normalized) and normalized == value.strip().upper() and len(normalized) <= 10


def _resolve_security_ticker(
    ticker: object = "",
    cusip: object = "",
    issuer_name: object = "",
    payload: dict[str, object] | None = None,
) -> str:
    payload = payload if isinstance(payload, dict) else {}
    raw_ticker = _normalize_whitespace(ticker or payload.get("ticker", "")).upper()
    raw_cusip = _normalize_whitespace(cusip or payload.get("issuer_cusip", "") or payload.get("cusip", "")).upper()
    raw_issuer_name = _normalize_whitespace(
        issuer_name or payload.get("issuer_name", "") or payload.get("company_name", "") or payload.get("issuer", "")
    )
    repository = get_security_identifier_repository()
    try:
        return repository.resolve_ticker(raw_cusip, raw_ticker, raw_issuer_name)
    except TypeError:
        return repository.resolve_ticker(raw_cusip, raw_ticker)


def _with_resolved_ticker(
    row: dict[str, object],
    *,
    cusip_field: str = "cusip",
    ticker_field: str = "ticker",
    issuer_field: str = "issuer",
) -> dict[str, object]:
    payload = _coerce_payload(row)
    normalized_row = dict(row)
    normalized_row[ticker_field] = _resolve_security_ticker(
        ticker=row.get(ticker_field, ""),
        cusip=row.get(cusip_field, ""),
        issuer_name=row.get(issuer_field, "") or row.get("company_name", ""),
        payload=payload,
    )
    return normalized_row


def build_security_candidates(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}
    for row in rows:
        key = _security_row_key(row)
        if not key:
            continue
        ranking_type = str(row.get("ranking_type", "") or "").strip()
        existing = candidates.get(key)
        if existing is None:
            candidate = dict(row)
            candidate["ranking_ranks"] = {}
            candidates[key] = candidate
        else:
            candidate = existing
            current_is_value_row = str(candidate.get("ranking_type", "")) == "top_total_holding_value"
            incoming_is_value_row = ranking_type == "top_total_holding_value"
            incoming_total_value = _safe_int(row.get("total_holding_value_usd", 0))
            current_total_value = _safe_int(candidate.get("total_holding_value_usd", 0))
            if incoming_is_value_row and not current_is_value_row:
                merged_ranks = dict(candidate.get("ranking_ranks", {}))
                candidate = dict(row)
                candidate["ranking_ranks"] = merged_ranks
                candidates[key] = candidate
            elif incoming_total_value > current_total_value and not current_is_value_row:
                merged_ranks = dict(candidate.get("ranking_ranks", {}))
                candidate = dict(row)
                candidate["ranking_ranks"] = merged_ranks
                candidates[key] = candidate
        ranking_ranks = candidate.setdefault("ranking_ranks", {})
        if ranking_type:
            ranking_ranks[ranking_type] = _safe_int(row.get("rank", 10_000), 10_000)
        candidate["new_manager_count"] = max(
            _safe_int(candidate.get("new_manager_count", 0)),
            _safe_int(row.get("new_manager_count", 0)),
        )
        candidate["reduced_manager_count"] = max(
            _safe_int(candidate.get("reduced_manager_count", 0)),
            _safe_int(row.get("reduced_manager_count", 0)),
        )
        candidate["holder_manager_count"] = max(
            _safe_int(candidate.get("holder_manager_count", 0)),
            _safe_int(row.get("holder_manager_count", 0)),
        )
        candidate["total_holding_value_usd"] = max(
            _safe_int(candidate.get("total_holding_value_usd", 0)),
            _safe_int(row.get("total_holding_value_usd", 0)),
        )
        candidate["new_entry_total_value_usd"] = max(
            _safe_int(candidate.get("new_entry_total_value_usd", 0)),
            _safe_int(row.get("new_entry_total_value_usd", 0)),
        )
        candidate["reduced_total_value_usd"] = max(
            _safe_int(candidate.get("reduced_total_value_usd", 0)),
            _safe_int(row.get("reduced_total_value_usd", 0)),
        )
    normalized_candidates: list[dict[str, object]] = []
    for candidate in candidates.values():
        ranking_ranks = dict(candidate.get("ranking_ranks", {}))
        candidate["ranking_ranks"] = ranking_ranks
        candidate["signal_count"] = len(ranking_ranks)
        candidate["best_rank"] = min(ranking_ranks.values(), default=10_000)
        summary_parts = []
        for ranking_type in (
            "top_total_holding_value",
            "top_new_manager_count",
            "top_reduced_manager_count",
        ):
            rank = ranking_ranks.get(ranking_type)
            if rank is not None:
                summary_parts.append(f"{RANKING_TYPE_LABELS[ranking_type]} #{rank}")
        candidate["ranking_summary"] = " · ".join(summary_parts)
        normalized_candidates.append(candidate)
    return normalized_candidates


def build_security_history_digest(history_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    per_period: dict[str, dict[str, object]] = {}
    for row in history_rows:
        report_date = str(row.get("report_date", "") or "").strip()
        if not report_date:
            continue
        ranking_type = str(row.get("ranking_type", "") or "").strip()
        rank = _safe_int(row.get("rank", 10_000), 10_000)
        existing = per_period.get(report_date)
        if existing is None:
            base = dict(row)
            base["ranking_ranks"] = {}
            per_period[report_date] = base
            existing = base
        ranking_ranks = existing.setdefault("ranking_ranks", {})
        if ranking_type:
            ranking_ranks[ranking_type] = rank
        existing["holder_manager_count"] = max(
            _safe_int(existing.get("holder_manager_count", 0)),
            _safe_int(row.get("holder_manager_count", 0)),
        )
        existing["total_holding_value_usd"] = max(
            _safe_int(existing.get("total_holding_value_usd", 0)),
            _safe_int(row.get("total_holding_value_usd", 0)),
        )
        existing["new_manager_count"] = max(
            _safe_int(existing.get("new_manager_count", 0)),
            _safe_int(row.get("new_manager_count", 0)),
        )
        existing["reduced_manager_count"] = max(
            _safe_int(existing.get("reduced_manager_count", 0)),
            _safe_int(row.get("reduced_manager_count", 0)),
        )
        current_is_value_row = str(existing.get("ranking_type", "")) == "top_total_holding_value"
        if ranking_type == "top_total_holding_value" and not current_is_value_row:
            merged_ranks = dict(ranking_ranks)
            replacement = dict(row)
            replacement["ranking_ranks"] = merged_ranks
            per_period[report_date] = replacement
    digest_rows = sorted(per_period.values(), key=lambda row: str(row.get("report_date", "")), reverse=True)
    for row in digest_rows:
        ranking_ranks = dict(row.get("ranking_ranks", {}))
        row["signal_count"] = len(ranking_ranks)
        row["best_rank"] = min(ranking_ranks.values(), default=10_000)
        summary_parts = []
        for ranking_type in (
            "top_total_holding_value",
            "top_new_manager_count",
            "top_reduced_manager_count",
        ):
            rank = ranking_ranks.get(ranking_type)
            if rank is not None:
                summary_parts.append(f"{RANKING_TYPE_LABELS[ranking_type]} #{rank}")
        row["ranking_summary"] = " · ".join(summary_parts)
    return digest_rows


@st.cache_data(ttl=300, show_spinner=False)
def load_report_periods() -> list[str]:
    client = get_supabase_client()
    if client is None:
        return []
    try:
        latest_runs = client.fetch_rows("raw_13f_sync_runs", limit=1, order="synced_at.desc")
    except SupabaseError:
        latest_runs = []
    if latest_runs:
        payload = latest_runs[0].get("payload", {})
        if isinstance(payload, dict):
            report_dates = payload.get("report_dates", [])
            if isinstance(report_dates, list):
                values = [str(item) for item in report_dates if str(item).strip()]
                if values:
                    return values
    mover_rows = _fetch_all_rows("mart_13f_quarterly_movers", order="report_date.desc")
    periods = sorted({str(row.get("report_date", "")) for row in mover_rows if row.get("report_date")}, reverse=True)
    return periods


@st.cache_data(ttl=300, show_spinner=False)
def load_movers(
    report_period: str,
    security_type: str,
    ranking_type: str,
    top_n: int,
    search_text: str,
) -> list[dict[str, object]]:
    if not report_period:
        return []
    rows = _fetch_all_rows(
        "mart_13f_quarterly_movers",
        filters={
            "report_date": f"eq.{report_period}",
            "security_type": f"eq.{security_type}",
            "ranking_type": f"eq.{ranking_type}",
        },
        order="rank.asc",
    )
    rows = [_with_resolved_ticker(row) for row in rows]
    normalized_search = search_text.strip().lower()
    if normalized_search:
        rows = [
            row
            for row in rows
            if normalized_search in str(row.get("ticker", "") or "").lower()
            or normalized_search in str(row.get("issuer", "") or "").lower()
            or normalized_search in str(row.get("business_summary", "") or "").lower()
        ]
    rows.sort(key=lambda item: int(item.get("rank", 10_000)))
    return rows[: min(top_n, 100)]


@st.cache_data(ttl=300, show_spinner=False)
def load_period_security_rows(report_period: str, security_type: str) -> list[dict[str, object]]:
    if not report_period:
        return []
    rows = _fetch_all_rows(
        "mart_13f_quarterly_movers",
        filters={
            "report_date": f"eq.{report_period}",
            "security_type": f"eq.{security_type}",
        },
        order="ranking_type.asc,rank.asc",
    )
    return [_with_resolved_ticker(row) for row in rows]


@st.cache_data(ttl=300, show_spinner=False)
def load_security_history(cusip: str, security_type: str) -> list[dict[str, object]]:
    if not cusip:
        return []
    rows = _fetch_all_rows(
        "mart_13f_quarterly_movers",
        filters={
            "security_type": f"eq.{security_type}",
            "cusip": f"eq.{cusip.strip().upper()}",
        },
        order="report_date.desc,rank.asc",
    )
    return [_with_resolved_ticker(row) for row in rows]


@st.cache_data(ttl=300, show_spinner=False)
def load_security_period_rows(report_period: str, cusip: str, security_type: str) -> list[dict[str, object]]:
    if not report_period or not cusip:
        return []
    rows = load_period_security_rows(report_period, security_type)
    return [row for row in rows if str(row.get("cusip", "")).strip().upper() == cusip.strip().upper()]


@st.cache_data(ttl=300, show_spinner=False)
def load_security_candidates(
    report_period: str,
    security_type: str,
    search_text: str,
    min_holders: int,
    sort_metric: str,
    limit: int,
) -> list[dict[str, object]]:
    rows = load_period_security_rows(report_period, security_type)
    normalized_search = search_text.strip().lower()
    candidates = [
        row
        for row in build_security_candidates(rows)
        if _search_matches(row, normalized_search) and _safe_int(row.get("holder_manager_count", 0)) >= min_holders
    ]
    candidates.sort(
        key=lambda row: (
            -_safe_int(row.get(sort_metric, 0)),
            _safe_int(row.get("best_rank", 10_000), 10_000),
            str(row.get("ticker", "") or ""),
        )
    )
    return candidates[:limit]


@st.cache_data(ttl=300, show_spinner=False)
def load_recent_8k(search_text: str = "", limit: int = 100) -> list[dict[str, object]]:
    normalized_search = search_text.strip().lower()
    ticker_query = _normalize_ticker_query(search_text) if _is_exact_ticker_query(search_text) else ""
    if ticker_query:
        rows = _fetch_all_rows(
            "raw_8k_filings",
            filters={"ticker": f"eq.{ticker_query}"},
            order="filing_date.desc",
            max_pages=1,
        )
        return rows[:limit]
    rows = _fetch_all_rows("raw_8k_filings", order="filing_date.desc", max_pages=5)
    if normalized_search:
        rows = [
            row
            for row in rows
            if normalized_search in str(row.get("ticker", "") or "").lower()
            or normalized_search in str(row.get("company_name", "") or "").lower()
            or normalized_search in str(row.get("form", "") or "").lower()
        ]
    return rows[:limit]


def _coerce_payload(row: dict[str, object]) -> dict[str, object]:
    payload = row.get("payload", {})
    if isinstance(payload, dict):
        return payload
    return {}


def _normalize_whitespace(value: object) -> str:
    return " ".join(str(value or "").split())


def _13dg_form_family(form: str) -> str:
    normalized = _normalize_whitespace(form).upper()
    if "13D" in normalized:
        return "13D"
    if "13G" in normalized:
        return "13G"
    return normalized


def _13dg_reporting_person_key(person: dict[str, object]) -> str:
    cik = _normalize_whitespace(person.get("cik", ""))
    name = _normalize_whitespace(person.get("name", ""))
    return cik or name.upper()


def _resolve_13dg_ticker(row: dict[str, object], payload: dict[str, object]) -> str:
    return _resolve_security_ticker(
        ticker=row.get("ticker", ""),
        cusip=row.get("issuer_cusip", ""),
        payload=payload,
    )


def summarize_8k_row(row: dict[str, object]) -> dict[str, object]:
    payload = _coerce_payload(row)
    item_entries = payload.get("items", [])
    normalized_items: list[dict[str, str]] = []
    if isinstance(item_entries, list):
        for entry in item_entries:
            if isinstance(entry, dict):
                code = _normalize_whitespace(entry.get("code", ""))
                text = _normalize_whitespace(entry.get("text", ""))
                if code:
                    normalized_items.append({"code": code, "text": text})
    item_codes = [item["code"] for item in normalized_items]
    if not item_codes:
        raw_item_codes = payload.get("item_codes", [])
        if isinstance(raw_item_codes, list):
            item_codes = [_normalize_whitespace(item) for item in raw_item_codes if _normalize_whitespace(item)]
    exhibit_entries = payload.get("exhibits", [])
    normalized_exhibits: list[dict[str, str]] = []
    if isinstance(exhibit_entries, list):
        for entry in exhibit_entries:
            if isinstance(entry, dict):
                normalized_exhibits.append(
                    {
                        "sequence_number": _normalize_whitespace(entry.get("sequence_number", "")),
                        "document": _normalize_whitespace(entry.get("document", "")),
                        "document_type": _normalize_whitespace(entry.get("document_type", "")),
                        "description": _normalize_whitespace(entry.get("description", "")),
                        "purpose": _normalize_whitespace(entry.get("purpose", "")),
                    }
                )
    summary_parts: list[str] = []
    if item_codes:
        summary_parts.append("Items: " + ", ".join(item_codes))
    if payload.get("has_earnings"):
        summary_parts.append("Includes earnings-related disclosure")
    if payload.get("has_press_release"):
        summary_parts.append("Includes press release")
    if normalized_exhibits:
        summary_parts.append(f"{len(normalized_exhibits)} attachment(s)")
    return {
        "accession_number": _normalize_whitespace(row.get("accession_number") or payload.get("accession_number", "")),
        "ticker": _normalize_whitespace(row.get("ticker") or payload.get("ticker", "")),
        "form": _normalize_whitespace(row.get("form") or payload.get("form", "")),
        "filing_date": _normalize_whitespace(row.get("filing_date") or payload.get("filing_date", "")),
        "company_name": _normalize_whitespace(row.get("company_name") or payload.get("company_name", "")),
        "period_of_report": _normalize_whitespace(payload.get("period_of_report", "")),
        "date_of_report": _normalize_whitespace(payload.get("date_of_report", "")),
        "filing_url": _normalize_whitespace(payload.get("filing_url", "")),
        "text_url": _normalize_whitespace(payload.get("text_url", "")),
        "item_codes": item_codes,
        "items": normalized_items,
        "exhibits": normalized_exhibits,
        "has_press_release": bool(payload.get("has_press_release", False)),
        "has_earnings": bool(payload.get("has_earnings", False)),
        "summary_text": " · ".join(summary_parts) if summary_parts else "Structured 8-K detail is not available yet for this row.",
        "has_structured_content": bool(normalized_items or normalized_exhibits or item_codes),
    }


@st.cache_data(ttl=300, show_spinner=False)
def load_recent_13dg(search_text: str = "", limit: int = 100) -> list[dict[str, object]]:
    normalized_search = search_text.strip().lower()
    ticker_query = _normalize_ticker_query(search_text) if _is_exact_ticker_query(search_text) else ""
    if ticker_query:
        rows = _fetch_all_rows(
            "raw_13dg_filings",
            filters={"ticker": f"eq.{ticker_query}"},
            order="filing_date.desc",
            max_pages=2,
        )
        rows = [_with_resolved_ticker(row, cusip_field="issuer_cusip") for row in rows]
        if not rows:
            fallback_rows = _fetch_all_rows("raw_13dg_filings", order="filing_date.desc", max_pages=5)
            rows = [
                row
                for row in (_with_resolved_ticker(item, cusip_field="issuer_cusip") for item in fallback_rows)
                if str(row.get("ticker", "")).strip().upper() == ticker_query
            ]
        return rows[:limit]
    rows = _fetch_all_rows("raw_13dg_filings", order="filing_date.desc", max_pages=5)
    rows = [_with_resolved_ticker(row, cusip_field="issuer_cusip") for row in rows]
    if normalized_search:
        rows = [
            row
            for row in rows
            if normalized_search in str(row.get("ticker", "") or "").lower()
            or normalized_search in str(row.get("company_name", "") or "").lower()
            or normalized_search in str(row.get("form", "") or "").lower()
        ]
    return rows[:limit]


def _normalize_entity_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


@st.cache_data(ttl=300, show_spinner=False)
def load_recent_13dg_for_tickers(
    tickers: list[str] | set[str] | tuple[str, ...],
    limit: int = 100,
) -> list[dict[str, object]]:
    normalized_tickers = sorted({str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()})
    if not normalized_tickers:
        return []
    rows: list[dict[str, object]] = []
    seen_accessions: set[str] = set()
    for ticker in normalized_tickers:
        ticker_rows = _fetch_all_rows(
            "raw_13dg_filings",
            filters={"ticker": f"eq.{ticker}"},
            order="filing_date.desc",
            max_pages=1,
        )
        ticker_rows = [_with_resolved_ticker(row, cusip_field="issuer_cusip") for row in ticker_rows]
        for row in ticker_rows:
            accession_number = _normalize_whitespace(row.get("accession_number", ""))
            if accession_number and accession_number in seen_accessions:
                continue
            if accession_number:
                seen_accessions.add(accession_number)
            rows.append(row)
    rows.sort(
        key=lambda row: (
            _normalize_whitespace(row.get("filing_date", "")),
            _normalize_whitespace(row.get("accession_number", "")),
        ),
        reverse=True,
    )
    return rows[:limit]


def _13dg_row_matches_manager(
    detail: dict[str, object],
    manager_name: str,
    manager_cik: int | str = "",
) -> bool:
    normalized_manager_name = _normalize_entity_name(manager_name)
    normalized_manager_cik = re.sub(r"\D+", "", str(manager_cik or ""))
    reporting_persons = detail.get("reporting_persons", [])
    if not isinstance(reporting_persons, list):
        return False
    for person in reporting_persons:
        if not isinstance(person, dict):
            continue
        person_cik = re.sub(r"\D+", "", str(person.get("cik", "") or ""))
        if normalized_manager_cik and person_cik and person_cik == normalized_manager_cik:
            return True
        person_name = _normalize_entity_name(str(person.get("name", "") or ""))
        if not normalized_manager_name or not person_name:
            continue
        if person_name == normalized_manager_name:
            return True
        if person_name in normalized_manager_name or normalized_manager_name in person_name:
            return True
    return False


@st.cache_data(ttl=300, show_spinner=False)
def load_recent_13dg_by_manager(
    manager_name: str,
    manager_cik: int | str = "",
    tickers: list[str] | set[str] | tuple[str, ...] | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    if not str(manager_name).strip() and not str(manager_cik).strip():
        return []
    if tickers:
        source_rows = load_recent_13dg_for_tickers(tickers, limit=max(limit * 5, limit))
    else:
        source_rows = load_recent_13dg(limit=max(limit * 5, 100))
    matched_rows: list[dict[str, object]] = []
    for row in source_rows:
        detail = summarize_13dg_row(row)
        if _13dg_row_matches_manager(detail, manager_name, manager_cik):
            matched_rows.append(detail)
    matched_rows.sort(
        key=lambda row: (
            _normalize_whitespace(row.get("filing_date", "")),
            _normalize_whitespace(row.get("accession_number", "")),
        ),
        reverse=True,
    )
    return matched_rows[:limit]


def summarize_13dg_row(row: dict[str, object]) -> dict[str, object]:
    payload = _coerce_payload(row)
    resolved_ticker = _resolve_13dg_ticker(row, payload)
    reporting_persons = payload.get("reporting_persons", [])
    normalized_persons: list[dict[str, object]] = []
    if isinstance(reporting_persons, list):
        for person in reporting_persons:
            if not isinstance(person, dict):
                continue
            normalized_persons.append(
                {
                    "cik": _normalize_whitespace(person.get("cik", "")),
                    "name": _normalize_whitespace(person.get("name", "")),
                    "aggregate_amount": person.get("aggregate_amount"),
                    "percent_of_class": person.get("percent_of_class"),
                    "type_of_reporting_person": _normalize_whitespace(person.get("type_of_reporting_person", "")),
                    "citizenship": _normalize_whitespace(person.get("citizenship", "")),
                    "sole_voting_power": person.get("sole_voting_power"),
                    "shared_voting_power": person.get("shared_voting_power"),
                    "sole_dispositive_power": person.get("sole_dispositive_power"),
                    "shared_dispositive_power": person.get("shared_dispositive_power"),
                    "comment": _normalize_whitespace(person.get("comment", "")),
                }
            )
    return {
        "accession_number": _normalize_whitespace(row.get("accession_number") or payload.get("accession_number", "")),
        "ticker": resolved_ticker,
        "company_name": _normalize_whitespace(row.get("company_name") or payload.get("company_name", "")),
        "form": _normalize_whitespace(row.get("form") or payload.get("form", "")),
        "form_family": _13dg_form_family(_normalize_whitespace(row.get("form") or payload.get("form", ""))),
        "filing_date": _normalize_whitespace(row.get("filing_date") or payload.get("filing_date", "")),
        "filing_url": _normalize_whitespace(payload.get("filing_url", "")),
        "text_url": _normalize_whitespace(payload.get("text_url", "")),
        "issuer_name": _normalize_whitespace(payload.get("issuer_name", "")),
        "issuer_cik": _normalize_whitespace(payload.get("issuer_cik", "")),
        "issuer_cusip": _normalize_whitespace(payload.get("issuer_cusip", "")),
        "security_title": _normalize_whitespace(payload.get("security_title", "")),
        "event_date": _normalize_whitespace(payload.get("event_date", "")),
        "amendment_number": _normalize_whitespace(payload.get("amendment_number", "")),
        "is_amendment": bool(payload.get("is_amendment", False)),
        "is_passive_investor": bool(payload.get("is_passive_investor", False)),
        "rule_designation": _normalize_whitespace(payload.get("rule_designation", "")),
        "purpose_text": _normalize_whitespace(payload.get("purpose_text", "")),
        "total_shares": payload.get("total_shares"),
        "total_percent": payload.get("total_percent"),
        "reporting_persons": normalized_persons,
        "summary_text": _normalize_whitespace(payload.get("summary", "")) or "Beneficial ownership event synced from Schedule 13D/G feed.",
    }


def build_manager_13dg_monitor_rows(
    manager_13dg_rows: list[dict[str, object]],
    rebalance_rows: list[dict[str, object]],
    report_period: str,
    manager_cik: int | str,
    allow_local_fallback: bool = False,
) -> list[dict[str, object]]:
    rebalance_by_ticker = {
        str(row.get("ticker", "")).strip().upper(): row
        for row in rebalance_rows
        if str(row.get("ticker", "")).strip()
    }
    crosscheck_by_key = load_manager_13f_crosscheck(
        report_period,
        manager_cik,
        [
            {
                "ticker": str(row.get("ticker", "") or ""),
                "cusip": str(row.get("issuer_cusip", "") or ""),
            }
            for row in manager_13dg_rows
        ],
        allow_local_fallback=allow_local_fallback,
    )
    enriched_rows: list[dict[str, object]] = []
    normalized_manager_cik = re.sub(r"\D+", "", str(manager_cik or ""))
    for row in manager_13dg_rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        cusip = str(row.get("issuer_cusip", "") or "").strip().upper()
        rebalance_row = rebalance_by_ticker.get(ticker, {})
        crosscheck_row = crosscheck_by_key.get(f"{ticker}|{cusip}", {})
        if crosscheck_row and not rebalance_row:
            rebalance_row = crosscheck_row
        rebalance_status = str(rebalance_row.get("status", "") or "")
        if not rebalance_status:
            rebalance_status = "Not reported"
        filing_change = _build_manager_13dg_filing_change(row, normalized_manager_cik)
        enriched_rows.append(
            {
                **row,
                "ticker": ticker,
                "reported_shares": _safe_int(row.get("total_shares"), 0),
                "reported_percent": row.get("total_percent"),
                "filing_change_status": str(filing_change.get("status", "")),
                "filing_change_current_shares": filing_change.get("current_shares"),
                "filing_change_previous_shares": filing_change.get("previous_shares"),
                "filing_change_delta_shares": filing_change.get("delta_shares"),
                "filing_change_current_percent": filing_change.get("current_percent"),
                "filing_change_previous_percent": filing_change.get("previous_percent"),
                "filing_change_delta_percent": filing_change.get("delta_percent"),
                "rebalance_status": rebalance_status,
                "rebalance_value_change_usd": (
                    _safe_int(rebalance_row.get("value_change_usd"), 0) if rebalance_row else None
                ),
                "rebalance_current_value_usd": (
                    _safe_int(rebalance_row.get("current_value_usd"), 0) if rebalance_row else None
                ),
                "rebalance_previous_value_usd": (
                    _safe_int(rebalance_row.get("previous_value_usd"), 0) if rebalance_row else None
                ),
            }
        )
    return enriched_rows


def _manager_reporting_persons_for_detail(
    detail: dict[str, object],
    manager_cik: str,
) -> list[dict[str, object]]:
    reporting_persons = detail.get("reporting_persons", [])
    if not isinstance(reporting_persons, list):
        return []
    if not manager_cik:
        return [person for person in reporting_persons if isinstance(person, dict)]
    matched_persons: list[dict[str, object]] = []
    for person in reporting_persons:
        if not isinstance(person, dict):
            continue
        person_cik = re.sub(r"\D+", "", str(person.get("cik", "") or ""))
        if person_cik and person_cik == manager_cik:
            matched_persons.append(person)
    return matched_persons


def _aggregate_manager_reporting_persons(persons: list[dict[str, object]]) -> dict[str, object]:
    current_shares = sum(_safe_int(person.get("aggregate_amount"), 0) for person in persons)
    percents = [float(value) for value in (person.get("percent_of_class") for person in persons) if value is not None]
    current_percent = max(percents) if percents else None
    return {
        "shares": current_shares,
        "percent": current_percent,
    }


def _build_manager_13dg_filing_change(
    row: dict[str, object],
    normalized_manager_cik: str,
) -> dict[str, object]:
    current_detail = dict(row)
    chain_rows = load_13dg_chain(
        str(current_detail.get("ticker", "") or ""),
        str(current_detail.get("form_family", "") or current_detail.get("form", "") or ""),
        str(current_detail.get("issuer_cusip", "") or ""),
        str(current_detail.get("issuer_name", "") or current_detail.get("company_name", "") or ""),
        limit=20,
    )
    previous_detail = next(
        (
            detail
            for detail in chain_rows
            if str(detail.get("accession_number", "") or "") != str(current_detail.get("accession_number", "") or "")
        ),
        None,
    )
    current_persons = _manager_reporting_persons_for_detail(current_detail, normalized_manager_cik)
    previous_persons = _manager_reporting_persons_for_detail(previous_detail or {}, normalized_manager_cik)
    current_aggregate = _aggregate_manager_reporting_persons(current_persons)
    previous_aggregate = _aggregate_manager_reporting_persons(previous_persons)
    current_shares = _safe_int(current_aggregate.get("shares"), 0)
    previous_shares = _safe_int(previous_aggregate.get("shares"), 0)
    current_percent = current_aggregate.get("percent")
    previous_percent = previous_aggregate.get("percent")
    if previous_detail is None or not previous_persons:
        status = "new"
    elif current_shares > previous_shares:
        status = "increased"
    elif current_shares < previous_shares:
        status = "decreased"
    else:
        status = "unchanged"
    return {
        "status": status,
        "current_shares": current_shares,
        "previous_shares": previous_shares,
        "delta_shares": current_shares - previous_shares,
        "current_percent": current_percent,
        "previous_percent": previous_percent,
        "delta_percent": (
            current_percent - previous_percent
            if current_percent is not None and previous_percent is not None
            else None
        ),
    }


@st.cache_data(ttl=300, show_spinner=False)
def load_manager_13f_crosscheck(
    report_period: str,
    manager_cik: int | str,
    security_refs: list[dict[str, str]],
    allow_local_fallback: bool = False,
) -> dict[str, dict[str, object]]:
    normalized_report_period = str(report_period or "").strip()
    normalized_manager_cik = str(manager_cik or "").strip()
    if not normalized_report_period or not normalized_manager_cik:
        return {}
    rows_by_key: dict[str, dict[str, object]] = {}
    mart_rows = _fetch_all_rows(
        "mart_manager_security_latest",
        filters={
            "report_date": f"eq.{normalized_report_period}",
            "manager_cik": f"eq.{normalized_manager_cik}",
        },
        order="ticker.asc",
        max_pages=10,
    )
    if mart_rows:
        mart_by_key = {
            f"{str(row.get('ticker', '') or '').strip().upper()}|{str(row.get('cusip', '') or '').strip().upper()}": row
            for row in mart_rows
        }
        for ref in security_refs:
            ticker = str(ref.get("ticker", "") or "").strip().upper()
            cusip = str(ref.get("cusip", "") or "").strip().upper()
            if not ticker and not cusip:
                continue
            key = f"{ticker}|{cusip}"
            row = mart_by_key.get(key)
            if row is None and cusip:
                row = next(
                    (
                        candidate
                        for candidate_key, candidate in mart_by_key.items()
                        if candidate_key.endswith(f"|{cusip}")
                    ),
                    None,
                )
            if row is None and ticker:
                row = next(
                    (
                        candidate
                        for candidate_key, candidate in mart_by_key.items()
                        if candidate_key.startswith(f"{ticker}|")
                    ),
                    None,
                )
            if row is None:
                continue
            rows_by_key[key] = {
                "ticker": str(row.get("ticker", "") or "").strip().upper(),
                "cusip": str(row.get("cusip", "") or "").strip().upper(),
                "issuer": str(row.get("issuer", "") or "").strip(),
                "status": str(row.get("status", "") or ""),
                "previous_value_usd": _safe_int(row.get("previous_value_usd"), 0),
                "current_value_usd": _safe_int(row.get("current_value_usd"), 0),
                "value_change_usd": _safe_int(row.get("value_change_usd"), 0),
                "found_in_current": bool(row.get("found_in_current", False)),
                "found_in_previous": bool(row.get("found_in_previous", False)),
            }
    return rows_by_key


@st.cache_data(ttl=300, show_spinner=False)
def load_13dg_chain(
    ticker: str,
    form_family: str,
    issuer_cusip: str,
    issuer_name: str,
    limit: int = 20,
) -> list[dict[str, object]]:
    normalized_ticker = _normalize_whitespace(ticker).upper()
    if not normalized_ticker:
        return []
    rows = _fetch_all_rows(
        "raw_13dg_filings",
        filters={"ticker": f"eq.{normalized_ticker}"},
        order="filing_date.desc",
        max_pages=10,
    )
    if not rows and (issuer_cusip or issuer_name):
        rows = _fetch_all_rows("raw_13dg_filings", order="filing_date.desc", max_pages=10)
    rows = [_with_resolved_ticker(row, cusip_field="issuer_cusip") for row in rows]
    detail_rows = [summarize_13dg_row(row) for row in rows]
    normalized_family = _13dg_form_family(form_family)
    normalized_issuer_cusip = _normalize_whitespace(issuer_cusip).upper()
    normalized_issuer_name = _normalize_whitespace(issuer_name).upper()
    filtered_rows = []
    for detail in detail_rows:
        if _13dg_form_family(str(detail.get("form_family", ""))) != normalized_family:
            continue
        detail_cusip = _normalize_whitespace(detail.get("issuer_cusip", "")).upper()
        detail_issuer_name = _normalize_whitespace(detail.get("issuer_name", "")).upper()
        if normalized_issuer_cusip and detail_cusip and detail_cusip != normalized_issuer_cusip:
            continue
        if normalized_issuer_name and detail_issuer_name and detail_issuer_name != normalized_issuer_name:
            continue
        filtered_rows.append(detail)
    return filtered_rows[:limit]


def build_13dg_reporting_person_changes(
    current_detail: dict[str, object],
    previous_detail: dict[str, object] | None,
) -> list[dict[str, object]]:
    current_persons = current_detail.get("reporting_persons", [])
    previous_persons = previous_detail.get("reporting_persons", []) if previous_detail else []
    current_map = {
        _13dg_reporting_person_key(person): person
        for person in current_persons
        if isinstance(person, dict) and _13dg_reporting_person_key(person)
    }
    previous_map = {
        _13dg_reporting_person_key(person): person
        for person in previous_persons
        if isinstance(person, dict) and _13dg_reporting_person_key(person)
    }
    rows: list[dict[str, object]] = []
    for person_key in sorted(current_map.keys() | previous_map.keys()):
        current_person = current_map.get(person_key, {})
        previous_person = previous_map.get(person_key, {})
        current_shares = _safe_int(current_person.get("aggregate_amount"), 0)
        previous_shares = _safe_int(previous_person.get("aggregate_amount"), 0)
        current_percent_raw = current_person.get("percent_of_class")
        previous_percent_raw = previous_person.get("percent_of_class")
        current_percent = float(current_percent_raw) if current_percent_raw is not None else None
        previous_percent = float(previous_percent_raw) if previous_percent_raw is not None else None
        if not previous_person:
            status = "new"
        elif not current_person:
            status = "exited"
        elif current_shares > previous_shares:
            status = "increased"
        elif current_shares < previous_shares:
            status = "decreased"
        else:
            status = "unchanged"
        rows.append(
            {
                "name": current_person.get("name") or previous_person.get("name") or "-",
                "cik": current_person.get("cik") or previous_person.get("cik") or "",
                "type_of_reporting_person": current_person.get("type_of_reporting_person")
                or previous_person.get("type_of_reporting_person")
                or "",
                "status": status,
                "current_shares": current_shares,
                "previous_shares": previous_shares,
                "delta_shares": current_shares - previous_shares,
                "current_percent": current_percent,
                "previous_percent": previous_percent,
                "delta_percent": (
                    current_percent - previous_percent
                    if current_percent is not None and previous_percent is not None
                    else None
                ),
            }
        )
    status_priority = {"new": 0, "increased": 1, "decreased": 2, "exited": 3, "unchanged": 4}
    rows.sort(key=lambda row: (status_priority.get(str(row.get("status", "")), 99), -abs(_safe_int(row.get("delta_shares"), 0))))
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def load_latest_13dg_change_summary(ticker: str) -> dict[str, object]:
    normalized_ticker = _normalize_whitespace(ticker).upper()
    if not normalized_ticker:
        return {}
    rows = load_recent_13dg(search_text=normalized_ticker, limit=20)
    matching_rows = [
        row
        for row in rows
        if _normalize_whitespace(row.get("ticker", "")).upper() == normalized_ticker
    ]
    if not matching_rows:
        return {}
    latest_detail = summarize_13dg_row(matching_rows[0])
    chain_rows = load_13dg_chain(
        normalized_ticker,
        str(latest_detail.get("form_family", "")),
        str(latest_detail.get("issuer_cusip", "")),
        str(latest_detail.get("issuer_name", "")),
        limit=20,
    )
    previous_detail = chain_rows[1] if len(chain_rows) > 1 else None
    changes = build_13dg_reporting_person_changes(latest_detail, previous_detail)
    status_counts = {
        "new": sum(1 for row in changes if str(row.get("status", "")) == "new"),
        "increased": sum(1 for row in changes if str(row.get("status", "")) == "increased"),
        "decreased": sum(1 for row in changes if str(row.get("status", "")) == "decreased"),
        "exited": sum(1 for row in changes if str(row.get("status", "")) == "exited"),
        "unchanged": sum(1 for row in changes if str(row.get("status", "")) == "unchanged"),
    }
    summary_parts: list[str] = []
    if latest_detail.get("rule_designation"):
        summary_parts.append(str(latest_detail.get("rule_designation")))
    if latest_detail.get("total_percent") is not None:
        summary_parts.append(f"{float(latest_detail['total_percent']):g}% of class")
    if previous_detail is not None:
        if status_counts["new"]:
            summary_parts.append(f"{status_counts['new']} new reporting person(s)")
        if status_counts["increased"]:
            summary_parts.append(f"{status_counts['increased']} increased")
        if status_counts["decreased"]:
            summary_parts.append(f"{status_counts['decreased']} decreased")
        if status_counts["exited"]:
            summary_parts.append(f"{status_counts['exited']} exited")
    return {
        "latest_detail": latest_detail,
        "previous_detail": previous_detail,
        "changes": changes,
        "chain_rows": chain_rows,
        "status_counts": status_counts,
        "summary_text": " · ".join(summary_parts) if summary_parts else str(latest_detail.get("summary_text", "")),
    }


@st.cache_data(ttl=300, show_spinner=False)
def load_manager_profiles() -> list[dict[str, object]]:
    client = get_supabase_client()
    if client is None:
        return [asdict(manager) for manager in list_default_managers()]
    try:
        rows = _fetch_all_rows("mart_manager_profile", order="display_order.asc")
    except SupabaseError:
        rows = []
    if rows:
        return rows
    return [asdict(manager) for manager in list_default_managers()]


@st.cache_data(ttl=300, show_spinner=False)
def load_manager_snapshot() -> dict[str, object]:
    client = get_supabase_client()
    if client is None:
        return {}
    try:
        rows = client.fetch_rows("mart_manager_research_snapshot", limit=1, order="snapshot_key.asc")
    except SupabaseError:
        return {}
    return rows[0] if rows else {}


@st.cache_data(ttl=300, show_spinner=False)
def load_manager_rebalance_snapshot(
    report_period: str,
    manager_cik: int | str,
    top_n: int | None = 12,
) -> dict[str, object]:
    if not report_period or not str(manager_cik).strip():
        return {}
    client = get_supabase_client()
    if client is None:
        return {}
    normalized_manager_cik = str(manager_cik).strip()
    summary_filters = {
        "report_date": f"eq.{report_period}",
        "manager_cik": f"eq.{normalized_manager_cik}",
    }
    try:
        summary_rows = client.fetch_rows(
            "mart_manager_rebalance_summary",
            limit=1,
            filters=summary_filters,
            order="manager_cik.asc",
        )
        detail_rows = _fetch_all_rows(
            "mart_manager_rebalance_detail",
            filters=summary_filters,
            order="rank.asc",
            max_pages=10,
        )
    except SupabaseError:
        return {}
    if not summary_rows:
        return {}
    summary = summary_rows[0]
    normalized_rows = [_with_resolved_ticker(row) for row in detail_rows]
    if top_n is not None and top_n > 0:
        normalized_rows = normalized_rows[:top_n]
    return {
        "manager_cik": normalized_manager_cik,
        "manager_name": str(summary.get("manager_name", "") or ""),
        "report_date": str(summary.get("report_date", "") or report_period),
        "previous_report_date": str(summary.get("previous_report_date", "") or ""),
        "current_holding_count": int(summary.get("current_holding_count", 0) or 0),
        "previous_holding_count": int(summary.get("previous_holding_count", 0) or 0),
        "status_counts": {
            "new": int(summary.get("new_count", 0) or 0),
            "increased": int(summary.get("increased_count", 0) or 0),
            "decreased": int(summary.get("decreased_count", 0) or 0),
            "exited": int(summary.get("exited_count", 0) or 0),
            "unchanged": int(summary.get("unchanged_count", 0) or 0),
        },
        "rows": normalized_rows,
        "warning": "",
    }


@st.cache_data(ttl=300, show_spinner=False)
def load_focus_related_movers(
    report_period: str,
    focus_areas: str,
    security_type: str,
    top_n: int = 12,
) -> list[dict[str, object]]:
    focus_terms = split_focus_terms(focus_areas)
    rows = load_period_security_rows(report_period, security_type)
    scored_rows: dict[str, dict[str, object]] = {}
    for row in rows:
        score = _focus_score(row, focus_terms)
        if score <= 0:
            continue
        row_key = str(row.get("cusip", "")).strip().upper() or str(row.get("issuer", "")).strip()
        previous = scored_rows.get(row_key)
        candidate = dict(row)
        candidate["focus_score"] = score
        if previous is None:
            scored_rows[row_key] = candidate
            continue
        previous_score = int(previous.get("focus_score", 0))
        if score > previous_score:
            scored_rows[row_key] = candidate
            continue
        if score == previous_score and int(candidate.get("rank", 10_000)) < int(previous.get("rank", 10_000)):
            scored_rows[row_key] = candidate
    sorted_rows = sorted(
        scored_rows.values(),
        key=lambda row: (
            -int(row.get("focus_score", 0)),
            int(row.get("rank", 10_000)),
            -int(row.get("total_holding_value_usd", 0)),
        ),
    )
    return sorted_rows[:top_n]


@st.cache_data(ttl=300, show_spinner=False)
def prewarm_core_ui_cache(report_period: str) -> dict[str, int]:
    stock_rows = load_period_security_rows(report_period, "stock")
    etf_rows = load_period_security_rows(report_period, "etf")
    recent_8k = load_recent_8k(limit=100)
    recent_13dg = load_recent_13dg(limit=200)
    profiles = load_manager_profiles()
    snapshot = load_manager_snapshot()
    return {
        "stock_rows": len(stock_rows),
        "etf_rows": len(etf_rows),
        "recent_8k": len(recent_8k),
        "recent_13dg": len(recent_13dg),
        "profiles": len(profiles),
        "snapshot_keys": len(snapshot),
    }


@st.cache_data(ttl=300, show_spinner=False)
def prewarm_manager_ui_cache(
    report_period: str,
    manager_refs: tuple[tuple[str, str], ...],
) -> dict[str, int]:
    rebalance_rows = 0
    manager_event_rows = 0
    for manager_name, manager_cik in manager_refs:
        rebalance_snapshot = load_manager_rebalance_snapshot(report_period, manager_cik, top_n=None)
        rebalance_rows += len(rebalance_snapshot.get("rows", []))
        manager_event_rows += len(load_recent_13dg_by_manager(manager_name, manager_cik, limit=100))
    return {
        "managers": len(manager_refs),
        "rebalance_rows": rebalance_rows,
        "manager_event_rows": manager_event_rows,
    }


def list_markdown_reports() -> list[Path]:
    reports_dir = get_settings().paths.reports_dir
    return sorted(reports_dir.rglob("*.md"), reverse=True)
