"""Thin wrapper around optional edgartools imports."""

from datetime import date
from datetime import timedelta
from http.client import RemoteDisconnected
import importlib
from importlib import util
import os
import re
import time
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen
import xml.etree.ElementTree as ET


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


class Edgar13FParseError(RuntimeError):
    """Raised when a 13F information table cannot be parsed."""


class EdgarRateLimitError(RuntimeError):
    """Raised when SEC temporarily blocks an edgartools request."""


class EdgarToolsClient:
    """Lazy wrapper to keep edgartools optional until sync commands are used."""

    def __init__(self) -> None:
        self._edgar_module = None
        self._last_sec_request_at: float | None = None

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

    def search_all_13f_filings(
        self,
        filing_date_from: str,
        filing_date_to: str,
    ) -> list[object]:
        edgar = self._edgar()
        start_date = date.fromisoformat(filing_date_from)
        end_date = date.fromisoformat(filing_date_to)
        if end_date < start_date:
            raise ValueError("filing_date_to must not be earlier than filing_date_from")

        filings_by_accession: dict[str, object] = {}
        quarter_start = date(start_date.year, ((start_date.month - 1) // 3) * 3 + 1, 1)
        http_requests = importlib.import_module("edgar.httprequests")
        too_many_requests_error = getattr(http_requests, "TooManyRequestsError")
        while quarter_start <= end_date:
            quarter = ((quarter_start.month - 1) // 3) + 1
            try:
                filings = edgar.get_filings(
                    year=quarter_start.year,
                    quarter=quarter,
                    form=["13F-HR", "13F-HR/A"],
                    amendments=True,
                )
            except too_many_requests_error as exc:
                raise EdgarRateLimitError(
                    "SEC rate limit reached while loading the 13F filing index; wait before retrying."
                ) from exc
            if filings is not None:
                for filing in filings:
                    filing_date = self._filing_date(filing)
                    if filing_date is None or not start_date <= filing_date <= end_date:
                        continue
                    accession = self._accession_number(filing)
                    if accession:
                        filings_by_accession[accession] = filing
            quarter_start = self._next_quarter_start(quarter_start)

        return sorted(
            filings_by_accession.values(),
            key=lambda filing: (self._filing_date(filing) or date.min, self._accession_number(filing)),
        )

    def build_13f_payload(
        self,
        filing: object,
        user_agent: str | None = None,
    ) -> dict[str, object]:
        if user_agent:
            report_date, content = self._fetch_submission_information_table(filing, user_agent)
        else:
            report_date = self.period_of_report(filing)
            information_table = self._information_table_attachment(filing)
            content = getattr(information_table, "content", "")
        return self._build_13f_payload_from_content(filing, report_date, content)

    def _build_13f_payload_from_content(
        self,
        filing: object,
        report_date: str,
        content: object,
    ) -> dict[str, object]:
        if not report_date:
            raise Edgar13FParseError(
                f"13F filing {self._accession_number(filing)} has no period of report."
            )
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        content_text = str(content).lstrip()
        if not content_text:
            raise Edgar13FParseError(
                f"13F filing {self._accession_number(filing)} has an empty information table."
            )
        try:
            root = ET.fromstring(content_text)
        except ET.ParseError as exc:
            raise Edgar13FParseError(
                f"13F filing {self._accession_number(filing)} information table is not valid XML."
            ) from exc

        holdings_by_key: dict[str, dict[str, object]] = {}
        for info_table in root.findall(".//{*}infoTable"):
            cusip = self._xml_child_text(info_table, "cusip").upper()
            title_of_class = self._xml_child_text(info_table, "titleOfClass")
            put_call = self._xml_child_text(info_table, "putCall").upper()
            security_key = f"{cusip}|{put_call or 'COMMON'}|{title_of_class}".upper()
            holding = {
                "name_of_issuer": self._xml_child_text(info_table, "nameOfIssuer"),
                "title_of_class": title_of_class,
                "cusip": cusip,
                "put_call": put_call,
                "value_usd": self._parse_int(self._xml_child_text(info_table, "value")),
                "shares_or_principal": self._parse_int(
                    self._xml_nested_text(info_table, "shrsOrPrnAmt", "sshPrnamt")
                ),
                "amount_type": self._xml_nested_text(info_table, "shrsOrPrnAmt", "sshPrnamtType"),
                "investment_discretion": self._xml_child_text(info_table, "investmentDiscretion"),
            }
            existing = holdings_by_key.get(security_key)
            if existing is None:
                holdings_by_key[security_key] = holding
            else:
                existing["value_usd"] = int(existing["value_usd"]) + int(holding["value_usd"])
                existing["shares_or_principal"] = int(existing["shares_or_principal"]) + int(
                    holding["shares_or_principal"]
                )

        if not holdings_by_key:
            raise Edgar13FParseError(
                f"13F filing {self._accession_number(filing)} has no information-table holdings."
            )
        filing_date = self._filing_date(filing)
        return {
            "accession_number": self._accession_number(filing),
            "manager_cik": int(getattr(filing, "cik", 0) or 0),
            "manager_name": _normalize_text(getattr(filing, "company", "") or getattr(filing, "company_name", "")),
            "form": _normalize_text(getattr(filing, "form", "")),
            "filing_date": filing_date.isoformat() if filing_date else "",
            "report_date": report_date,
            "filing_url": _normalize_text(getattr(filing, "homepage_url", "")),
            "payload": {
                "report_date": report_date,
                "holdings": list(holdings_by_key.values()),
            },
        }

    def _fetch_submission_information_table(
        self,
        filing: object,
        user_agent: str,
    ) -> tuple[str, str]:
        submission_url = str(getattr(filing, "text_url", "") or "").strip()
        if not submission_url:
            cik = int(getattr(filing, "cik", 0) or 0)
            accession = self._accession_number(filing).replace("-", "")
            submission_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{self._accession_number(filing)}.txt"
        submission_text = self._download_sec_text(submission_url, user_agent, filing)

        period_match = re.search(
            r"CONFORMED PERIOD OF REPORT:\s*(\d{8})",
            submission_text,
            flags=re.IGNORECASE,
        )
        if period_match is None:
            raise Edgar13FParseError(
                f"13F submission {self._accession_number(filing)} has no conformed report period."
            )
        raw_period = period_match.group(1)
        report_date = f"{raw_period[:4]}-{raw_period[4:6]}-{raw_period[6:8]}"
        information_documents: list[tuple[str, str]] = []
        for document in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", submission_text, flags=re.IGNORECASE | re.DOTALL):
            document_type = re.search(r"<TYPE>\s*([^\r\n<]+)", document, flags=re.IGNORECASE)
            filename_match = re.search(r"<FILENAME>\s*([^\r\n<]+)", document, flags=re.IGNORECASE)
            document_text = re.search(r"<TEXT>(.*?)</TEXT>", document, flags=re.IGNORECASE | re.DOTALL)
            if document_type is None or document_text is None:
                continue
            filename = filename_match.group(1).strip() if filename_match is not None else ""
            if "INFORMATION TABLE" in document_type.group(1).upper() or "INFOTABLE" in filename.upper():
                information_documents.append((filename, document_text.group(1).strip()))

        for filename, document_content in information_documents:
            if filename.lower().endswith(".xml") or "<infotable" in document_content.lower():
                try:
                    ET.fromstring(document_content.lstrip())
                except ET.ParseError:
                    continue
                return report_date, document_content

        xml_filename = next(
            (filename for filename, _ in information_documents if filename.lower().endswith(".xml")),
            "",
        )
        if xml_filename:
            archive_url = submission_url.rsplit("/", maxsplit=1)[0]
            xml_url = f"{archive_url}/{xml_filename.rsplit('/', maxsplit=1)[-1]}"
            return report_date, self._download_sec_text(xml_url, user_agent, filing)
        raise Edgar13FParseError(
            f"13F submission {self._accession_number(filing)} has no information-table document."
        )

    def _download_sec_text(self, url: str, user_agent: str, filing: object) -> str:
        try:
            self._wait_for_sec_request()
            request = Request(url, headers={"User-Agent": user_agent})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code in {403, 429, 503}:
                raise EdgarRateLimitError(
                    f"SEC temporarily rejected a 13F submission request (HTTP {exc.code}); wait before retrying."
                ) from exc
            raise Edgar13FParseError(
                f"Unable to download 13F submission {self._accession_number(filing)} (HTTP {exc.code})."
            ) from exc
        except (RemoteDisconnected, URLError, TimeoutError, ConnectionResetError) as exc:
            raise Edgar13FParseError(
                f"Unable to download 13F submission {self._accession_number(filing)}."
            ) from exc

    def _wait_for_sec_request(self) -> None:
        raw_rate = os.environ.get("EDGAR_RATE_LIMIT_PER_SEC", "2")
        try:
            requests_per_second = max(float(raw_rate), 0.1)
        except ValueError:
            requests_per_second = 2.0
        minimum_interval = 1.0 / requests_per_second
        if self._last_sec_request_at is not None:
            elapsed = time.monotonic() - self._last_sec_request_at
            if elapsed < minimum_interval:
                time.sleep(minimum_interval - elapsed)
        self._last_sec_request_at = time.monotonic()

    @staticmethod
    def _next_quarter_start(value: date) -> date:
        if value.month == 10:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 3, 1)

    @staticmethod
    def _filing_date(filing: object) -> date | None:
        value = getattr(filing, "filing_date", None)
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        return date.fromisoformat(text) if text else None

    @staticmethod
    def _accession_number(filing: object) -> str:
        return str(getattr(filing, "accession_number", None) or getattr(filing, "accession_no", "") or "").strip()

    @classmethod
    def period_of_report(cls, filing: object) -> str:
        header = getattr(filing, "header", None)
        return cls._normalize_date(getattr(header, "period_of_report", ""))

    @staticmethod
    def _normalize_date(value: object) -> str:
        if isinstance(value, date):
            return value.isoformat()
        text = str(value or "").strip()
        return text[:10] if len(text) >= 10 and text[4] == "-" else text

    @staticmethod
    def _information_table_attachment(filing: object) -> object:
        attachments = getattr(filing, "attachments", None)
        if attachments is None:
            raise Edgar13FParseError("13F filing has no attachments.")
        for attachment in list(attachments):
            document_type = _normalize_text(getattr(attachment, "document_type", "")).upper()
            document_name = _normalize_text(getattr(attachment, "document", "")).lower()
            if document_type == "INFORMATION TABLE" or "infotable" in document_name or "information" in document_name:
                return attachment
        raise Edgar13FParseError("13F filing has no information-table attachment.")

    @staticmethod
    def _xml_child_text(element: ET.Element, child_name: str) -> str:
        for child in list(element):
            if child.tag.split("}")[-1] == child_name:
                return (child.text or "").strip()
        return ""

    @classmethod
    def _xml_nested_text(cls, element: ET.Element, parent_name: str, child_name: str) -> str:
        for child in list(element):
            if child.tag.split("}")[-1] == parent_name:
                return cls._xml_child_text(child, child_name)
        return ""

    @staticmethod
    def _parse_int(value: str) -> int:
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return 0
        return int(float(cleaned))

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
