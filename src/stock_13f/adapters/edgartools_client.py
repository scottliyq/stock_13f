"""Thin wrapper around optional edgartools imports."""

from datetime import date
from datetime import timedelta
import importlib
from importlib import util


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EdgarToolsUnavailable(RuntimeError):
    """Raised when edgartools is required but unavailable."""


class EdgarTickerLookupError(RuntimeError):
    """Raised when a ticker cannot be resolved by edgartools."""


class EdgarToolsClient:
    """Lazy wrapper to keep edgartools optional until sync commands are used."""

    def __init__(self) -> None:
        self._edgar_module = None

    def is_available(self) -> bool:
        return util.find_spec("edgar") is not None

    def require_available(self) -> None:
        if not self.is_available():
            raise EdgarToolsUnavailable(
                "edgartools is not installed in the active environment. Install project dependencies first."
            )

    def _edgar(self):
        self.require_available()
        if self._edgar_module is None:
            self._edgar_module = importlib.import_module("edgar")
        return self._edgar_module

    def build_filing_date_range(self, days_back: int, date_from: str | None) -> str:
        if date_from:
            return f"{date_from}:{date.today().isoformat()}"
        return f"{(date.today() - timedelta(days=days_back)).isoformat()}:{date.today().isoformat()}"

    def search_company_filings(
        self,
        ticker: str,
        forms: tuple[str, ...],
        days_back: int,
        date_from: str | None,
        max_filings: int,
    ) -> list[object]:
        edgar = self._edgar()
        core_module = importlib.import_module("edgar.entity.core")
        company_not_found = getattr(core_module, "CompanyNotFoundError")
        try:
            company = edgar.Company(ticker)
        except company_not_found as exc:
            raise EdgarTickerLookupError(f"Ticker could not be resolved by edgartools: {ticker}") from exc
        filings = company.get_filings(form=list(forms))
        filing_date_range = self.build_filing_date_range(days_back, date_from)
        if hasattr(filings, "filter"):
            filings = filings.filter(filing_date=filing_date_range)
        return list(filings[:max_filings])

    def search_owner_filings(
        self,
        manager_identifier: str,
        forms: tuple[str, ...],
        days_back: int,
        date_from: str | None,
        max_filings: int,
    ) -> list[object]:
        edgar = self._edgar()
        core_module = importlib.import_module("edgar.entity.core")
        company_not_found = getattr(core_module, "CompanyNotFoundError")
        try:
            filer = edgar.Company(manager_identifier)
        except company_not_found as exc:
            raise EdgarTickerLookupError(f"Manager identifier could not be resolved by edgartools: {manager_identifier}") from exc
        filings = filer.get_filings(form=list(forms))
        filing_date_range = self.build_filing_date_range(days_back, date_from)
        if hasattr(filings, "filter"):
            filings = filings.filter(filing_date=filing_date_range)
        return list(filings[:max_filings])

    def build_8k_payload(self, filing: object, ticker: str) -> dict[str, object]:
        report = filing.obj()
        item_codes = [str(item).strip() for item in getattr(report, "items", []) or [] if str(item).strip()]
        items: list[dict[str, str]] = []
        for item_code in item_codes:
            item_text = _normalize_text(report[item_code])
            if item_text:
                items.append({"code": item_code, "text": item_text})
        exhibits: list[dict[str, str]] = []
        attachments = getattr(filing, "attachments", None)
        if attachments is not None:
            for attachment in list(attachments):
                document_type = str(getattr(attachment, "document_type", "") or "").strip()
                exhibits.append(
                    {
                        "sequence_number": str(getattr(attachment, "sequence_number", "") or "").strip(),
                        "document": str(getattr(attachment, "document", "") or "").strip(),
                        "document_type": document_type,
                        "description": _normalize_text(getattr(attachment, "description", "")),
                        "purpose": _normalize_text(getattr(attachment, "purpose", "")),
                    }
                )
        return {
            "ticker": ticker,
            "form": str(getattr(filing, "form", "") or "").strip(),
            "filing_date": str(getattr(filing, "filing_date", "") or "").strip(),
            "company_name": str(getattr(filing, "company", "") or getattr(filing, "company_name", "") or "").strip(),
            "accession_number": str(
                getattr(filing, "accession_number", None) or getattr(filing, "accession_no", "") or ""
            ).strip(),
            "filing_url": str(
                getattr(filing, "homepage_url", None)
                or getattr(filing, "filing_url", None)
                or getattr(filing, "url", "")
                or ""
            ).strip(),
            "text_url": str(getattr(filing, "text_url", "") or "").strip(),
            "period_of_report": str(getattr(report, "period_of_report", "") or "").strip(),
            "date_of_report": str(getattr(report, "date_of_report", "") or "").strip(),
            "item_codes": item_codes,
            "items": items,
            "has_press_release": bool(getattr(report, "has_press_release", False)),
            "has_earnings": bool(getattr(report, "has_earnings", False)),
            "press_release_count": len(getattr(report, "press_releases", []) or []),
            "exhibits": exhibits,
        }

    def build_13dg_payload(self, filing: object, ticker: str = "") -> dict[str, object]:
        report = filing.obj()
        issuer_info = getattr(report, "issuer_info", None)
        security_info = getattr(report, "security_info", None)
        issuer_name = _normalize_text(getattr(issuer_info, "name", ""))
        reporting_persons: list[dict[str, object]] = []
        for person in getattr(report, "reporting_persons", []) or []:
            reporting_persons.append(
                {
                    "name": _normalize_text(getattr(person, "name", "")),
                    "cik": _normalize_text(getattr(person, "cik", "")),
                    "citizenship": _normalize_text(getattr(person, "citizenship", "")),
                    "aggregate_amount": _safe_int(getattr(person, "aggregate_amount", None)),
                    "percent_of_class": _safe_float(getattr(person, "percent_of_class", None)),
                    "type_of_reporting_person": _normalize_text(getattr(person, "type_of_reporting_person", "")),
                    "sole_voting_power": _safe_int(getattr(person, "sole_voting_power", None)),
                    "shared_voting_power": _safe_int(getattr(person, "shared_voting_power", None)),
                    "sole_dispositive_power": _safe_int(getattr(person, "sole_dispositive_power", None)),
                    "shared_dispositive_power": _safe_int(getattr(person, "shared_dispositive_power", None)),
                    "comment": _normalize_text(getattr(person, "comment", "")),
                }
            )
        items = getattr(report, "items", None)
        purpose_text = _normalize_text(getattr(items, "item4_purpose_of_transaction", "")) if items is not None else ""
        summary_parts = []
        primary_person = reporting_persons[0] if reporting_persons else {}
        if primary_person.get("name"):
            summary_parts.append(str(primary_person["name"]))
        primary_shares = primary_person.get("aggregate_amount")
        if primary_shares:
            summary_parts.append(f"reported {primary_shares:,} shares")
        total_percent = _safe_float(getattr(report, "total_percent", None))
        if total_percent is not None:
            summary_parts.append(f"representing {total_percent:g}% of class")
        rule_designation = _normalize_text(getattr(report, "rule_designation", ""))
        if rule_designation:
            summary_parts.append(rule_designation)
        return {
            "ticker": ticker,
            "form": str(getattr(filing, "form", "") or "").strip(),
            "filing_date": str(getattr(filing, "filing_date", "") or "").strip(),
            "company_name": issuer_name or str(getattr(filing, "company", "") or getattr(filing, "company_name", "") or "").strip(),
            "accession_number": str(
                getattr(filing, "accession_number", None) or getattr(filing, "accession_no", "") or ""
            ).strip(),
            "filing_url": str(
                getattr(filing, "homepage_url", None)
                or getattr(filing, "filing_url", None)
                or getattr(filing, "url", "")
                or ""
            ).strip(),
            "text_url": str(getattr(filing, "text_url", "") or "").strip(),
            "event_date": _normalize_text(getattr(report, "event_date", "") or getattr(report, "date_of_event", "")),
            "amendment_number": _normalize_text(getattr(report, "amendment_number", "")),
            "is_amendment": bool(getattr(report, "is_amendment", False)),
            "is_passive_investor": bool(getattr(report, "is_passive_investor", False)),
            "rule_designation": rule_designation,
            "issuer_name": issuer_name,
            "issuer_cik": _normalize_text(getattr(issuer_info, "cik", "")),
            "issuer_cusip": _normalize_text(getattr(issuer_info, "cusip", "") or getattr(security_info, "cusip", "")),
            "security_title": _normalize_text(getattr(security_info, "title", "")),
            "total_shares": _safe_int(getattr(report, "total_shares", None)),
            "total_percent": total_percent,
            "reporting_persons": reporting_persons,
            "purpose_text": purpose_text,
            "summary": " · ".join(summary_parts) if summary_parts else "Beneficial ownership filing parsed from Schedule 13D/G.",
        }
