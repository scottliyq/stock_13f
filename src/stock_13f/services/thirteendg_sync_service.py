"""13D/G sync service implementation."""

from datetime import datetime, timezone
import importlib
from importlib import util
import logging

import httpx

from stock_13f.adapters.edgartools_client import EdgarToolsClient
from stock_13f.adapters.edgartools_client import EdgarTickerLookupError
from stock_13f.adapters.edgartools_client import EdgarToolsUnavailable
from stock_13f.core.edgar import apply_edgar_environment
from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.repositories.raw_13dg import Raw13DGRepository
from stock_13f.repositories.security_universe import SecurityUniverseRepository
from stock_13f.repositories.security_identifiers import SecurityIdentifierRepository
from stock_13f.repositories.watchlist import WatchlistRepository


LOGGER = logging.getLogger("stock_13f.services.sync_13dg")

THIRTEENDG_FORM_TYPES: tuple[str, ...] = (
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
    "SCHEDULE 13D",
    "SCHEDULE 13D/A",
    "SCHEDULE 13G",
    "SCHEDULE 13G/A",
)

THIRTEENDG_13D_FORM_TYPES: tuple[str, ...] = (
    "SC 13D",
    "SC 13D/A",
    "SCHEDULE 13D",
    "SCHEDULE 13D/A",
)

THIRTEENDG_13G_FORM_TYPES: tuple[str, ...] = (
    "SC 13G",
    "SC 13G/A",
    "SCHEDULE 13G",
    "SCHEDULE 13G/A",
)


def _build_thirteendg_ticker_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [
        EdgarTickerLookupError,
        httpx.HTTPError,
        OSError,
        TimeoutError,
    ]
    if util.find_spec("edgar.httprequests") is not None:
        httprequests_module = importlib.import_module("edgar.httprequests")
        ssl_error = getattr(httprequests_module, "SSLVerificationError", None)
        if isinstance(ssl_error, type) and issubclass(ssl_error, Exception):
            errors.append(ssl_error)
    return tuple(errors)

THIRTEENDG_TICKER_ERRORS = _build_thirteendg_ticker_errors()

THIRTEENDG_PAYLOAD_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
    httpx.HTTPError,
)


class ThirteenDGSyncService:
    """Sync 13D/13G filings for an explicit ticker list using edgartools."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        raw_repository: Raw13DGRepository | None = None,
        edgar_client: EdgarToolsClient | None = None,
        watchlist_repository: WatchlistRepository | None = None,
        security_identifier_repository: SecurityIdentifierRepository | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        supabase_client = build_supabase_client(settings)
        self._supabase_client = supabase_client
        self._edgar_client = edgar_client or EdgarToolsClient()
        self._raw_repository = raw_repository or Raw13DGRepository(
            settings.paths.raw_13dg_dir,
            supabase_client=supabase_client,
        )
        self._security_universe = SecurityUniverseRepository(supabase_client)
        self._watchlist_repository = watchlist_repository or WatchlistRepository()
        self._security_identifiers = security_identifier_repository or SecurityIdentifierRepository(
            settings.paths.data_dir / "cusip_ticker_map.csv",
            (
                settings.paths.data_dir / "sec_company_tickers.json",
                settings.paths.data_dir / "sec_company_tickers_exchange.json",
            ),
        )

    def sync(self, request: Sync13DGRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        apply_edgar_environment(self._settings)
        forms = self._resolve_forms(request.form_scope)
        resolved_tickers = request.tickers or self._security_universe.resolve(request.universe_source)
        resolved_manager_ciks = self._resolve_manager_ciks(request)
        if request.dry_run:
            dry_run_details = {
                "mode": request.mode,
                "days_back": request.days_back,
                "universe_source": request.universe_source,
                "form_scope": request.form_scope,
            }
            if request.mode.strip().lower() == "manager":
                dry_run_details["manager_ciks"] = list(resolved_manager_ciks)
            else:
                dry_run_details["tickers"] = list(resolved_tickers)
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings + ["13D/G dry-run does not contact EDGAR."],
                details=dry_run_details,
            )
            self._checkpoints.record_result(result, cursor=self._build_cursor(request, resolved_tickers, resolved_manager_ciks))
            return result
        if request.mode.strip().lower() == "manager" and not resolved_manager_ciks:
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings + ["No manager CIKs were resolved; sync-13dg completed without contacting EDGAR."],
                details={"mode": "manager", "manager_ciks": []},
            )
            self._checkpoints.record_result(result, cursor={"mode": "manager", "manager_ciks": []})
            return result
        if request.mode.strip().lower() != "manager" and not resolved_tickers:
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings + ["No tickers were provided; sync-13dg completed without contacting EDGAR."],
                details={"mode": "issuer", "tickers": []},
            )
            self._checkpoints.record_result(result, cursor={"mode": "issuer", "tickers": []})
            return result
        try:
            records_written = 0
            skipped_existing = 0
            mode = self._normalize_mode(request.mode)
            detail_tickers = [] if mode == "manager" else list(resolved_tickers)
            if mode == "manager":
                for manager_cik in resolved_manager_ciks:
                    try:
                        filings = self._edgar_client.search_owner_filings(
                            manager_identifier=manager_cik,
                            forms=forms,
                            days_back=request.days_back,
                            date_from=request.date_from,
                            max_filings=request.max_filings,
                        )
                    except THIRTEENDG_TICKER_ERRORS as exc:
                        warnings.append(f"13D/G filing search skipped for manager {manager_cik}: {exc}")
                        continue
                    for filing in filings:
                        accession_number = self._accession_number_for_filing(filing)
                        existing_payload = self._raw_repository.load_record(accession_number)
                        if existing_payload is not None:
                            skipped_existing += 1
                            LOGGER.info(
                                "sync_13dg_reuse_existing_accession",
                                extra={
                                    "mode": "manager",
                                    "source_key": manager_cik,
                                    "accession_number": accession_number,
                                },
                            )
                            self._write_payload(
                                accession_number,
                                existing_payload,
                                source_mode="manager",
                                source_key=manager_cik,
                            )
                            records_written += 1
                            continue
                        try:
                            payload = self._edgar_client.build_13dg_payload(filing, "")
                            payload["ticker"] = self._security_identifiers.resolve_ticker(
                                str(payload.get("issuer_cusip", "") or ""),
                                str(payload.get("ticker", "") or ""),
                                str(payload.get("issuer_name", "") or payload.get("company_name", "") or ""),
                            )
                        except THIRTEENDG_PAYLOAD_FALLBACK_ERRORS as exc:
                            warnings.append(f"13D/G parse fallback for manager {manager_cik} {accession_number}: {exc}")
                            payload = self._build_fallback_payload(filing, "")
                        self._write_payload(accession_number, payload, source_mode="manager", source_key=manager_cik)
                        records_written += 1
            else:
                for ticker in resolved_tickers:
                    try:
                        filings = self._edgar_client.search_company_filings(
                            ticker=ticker,
                            forms=forms,
                            days_back=request.days_back,
                            date_from=request.date_from,
                            max_filings=request.max_filings,
                        )
                    except THIRTEENDG_TICKER_ERRORS as exc:
                        warnings.append(f"13D/G filing search skipped for {ticker}: {exc}")
                        continue
                    for filing in filings:
                        accession_number = self._accession_number_for_filing(filing)
                        existing_payload = self._raw_repository.load_record(accession_number)
                        if existing_payload is not None:
                            skipped_existing += 1
                            LOGGER.info(
                                "sync_13dg_reuse_existing_accession",
                                extra={
                                    "mode": "issuer",
                                    "source_key": ticker,
                                    "accession_number": accession_number,
                                },
                            )
                            self._write_payload(
                                accession_number,
                                existing_payload,
                                source_mode="issuer",
                                source_key=ticker,
                            )
                            records_written += 1
                            continue
                        try:
                            payload = self._edgar_client.build_13dg_payload(filing, ticker)
                        except THIRTEENDG_PAYLOAD_FALLBACK_ERRORS as exc:
                            warnings.append(f"13D/G parse fallback for {ticker} {accession_number}: {exc}")
                            payload = self._build_fallback_payload(filing, ticker)
                        self._write_payload(accession_number, payload, source_mode="issuer", source_key=ticker)
                        records_written += 1
            LOGGER.info(
                "sync_13dg_completed",
                extra={"rows_written": records_written, "skipped_existing_accessions": skipped_existing},
            )
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=records_written,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "mode": mode,
                    "tickers": detail_tickers,
                    "manager_ciks": list(resolved_manager_ciks),
                    "universe_source": request.universe_source,
                    "form_scope": request.form_scope,
                    "skipped_existing_accessions": skipped_existing,
                },
            )
        except (EdgarToolsUnavailable, SupabaseError) as exc:
            result = SyncResult.failed(
                job_name="sync-13dg",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={
                    "mode": self._normalize_mode(request.mode),
                    "tickers": [] if self._normalize_mode(request.mode) == "manager" else list(resolved_tickers),
                    "manager_ciks": list(resolved_manager_ciks),
                },
            )
        self._checkpoints.record_result(result, cursor=self._build_cursor(request, resolved_tickers, resolved_manager_ciks))
        return result

    def audit_coverage(self, request: Sync13DGRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        apply_edgar_environment(self._settings)
        forms = self._resolve_forms(request.form_scope)
        resolved_manager_ciks = self._resolve_manager_ciks(request)
        if request.dry_run:
            result = SyncResult.success(
                job_name="audit-13dg-coverage",
                started_at=started_at,
                checkpoints_updated=1,
                warnings=warnings + ["13D/G coverage audit dry-run does not contact EDGAR."],
                details={"manager_ciks": list(resolved_manager_ciks), "mode": "manager", "form_scope": request.form_scope},
            )
            self._checkpoints.record_result(result, cursor={"manager_ciks": list(resolved_manager_ciks), "mode": "manager"})
            return result
        manager_entries = self._resolve_manager_entries(resolved_manager_ciks)
        local_accessions = self._load_local_manager_accession_map(manager_entries)
        missing_rows: list[dict[str, object]] = []
        audited_count = 0
        for manager_entry in manager_entries:
            try:
                filings = self._edgar_client.search_owner_filings(
                    manager_identifier=manager_entry["manager_cik"],
                    forms=forms,
                    days_back=request.days_back,
                    date_from=request.date_from,
                    max_filings=request.max_filings,
                )
            except THIRTEENDG_TICKER_ERRORS as exc:
                warnings.append(f"13D/G audit skipped for manager {manager_entry['manager_cik']}: {exc}")
                continue
            audited_count += len(filings)
            known_accessions = local_accessions.get(str(manager_entry["manager_cik"]), set())
            for filing in filings:
                accession_number = self._accession_number_for_filing(filing)
                if accession_number in known_accessions:
                    continue
                report = filing.obj()
                issuer_info = getattr(report, "issuer_info", None)
                security_info = getattr(report, "security_info", None)
                missing_rows.append(
                    {
                        "manager_cik": str(manager_entry["manager_cik"]),
                        "manager_name": str(manager_entry["manager_name"]),
                        "accession_number": accession_number,
                        "filing_date": str(getattr(filing, "filing_date", "") or ""),
                        "form": str(getattr(filing, "form", "") or ""),
                        "issuer_name": str(getattr(issuer_info, "name", "") or ""),
                        "issuer_cusip": str(
                            getattr(issuer_info, "cusip", "") or getattr(security_info, "cusip", "") or ""
                        ),
                    }
                )
        details = {
            "manager_ciks": list(resolved_manager_ciks),
            "audited_filing_count": audited_count,
            "gap_count": len(missing_rows),
            "missing_rows": missing_rows[:100],
        }
        result = SyncResult.success(
            job_name="audit-13dg-coverage",
            started_at=started_at,
            rows_written=len(missing_rows),
            checkpoints_updated=1,
            warnings=warnings,
            details=details,
        )
        self._checkpoints.record_result(result, cursor={"manager_ciks": list(resolved_manager_ciks), "mode": "manager"})
        return result

    def _resolve_forms(self, form_scope: str) -> tuple[str, ...]:
        normalized_scope = form_scope.strip().lower()
        if normalized_scope == "all":
            return THIRTEENDG_FORM_TYPES
        if normalized_scope == "13d":
            return THIRTEENDG_13D_FORM_TYPES
        if normalized_scope == "13g":
            return THIRTEENDG_13G_FORM_TYPES
        raise ValueError(f"Unsupported form_scope={form_scope!r}; expected 'all', '13d', or '13g'.")

    def _normalize_mode(self, mode: str) -> str:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"issuer", "manager"}:
            raise ValueError(f"Unsupported sync-13dg mode={mode!r}; expected 'issuer' or 'manager'.")
        return normalized_mode

    def _resolve_manager_ciks(self, request: Sync13DGRequest) -> tuple[str, ...]:
        if request.manager_ciks:
            return tuple(str(value).strip() for value in request.manager_ciks if str(value).strip())
        if request.manager_scope.strip().lower() == "watchlist":
            return tuple(str(entry.manager_cik) for entry in self._watchlist_repository.list_entries())
        return ()

    def _resolve_manager_entries(self, manager_ciks: tuple[str, ...]) -> list[dict[str, str]]:
        watchlist_map = {str(entry.manager_cik): entry for entry in self._watchlist_repository.list_entries()}
        rows: list[dict[str, str]] = []
        for manager_cik in manager_ciks:
            watchlist_entry = watchlist_map.get(str(manager_cik))
            rows.append(
                {
                    "manager_cik": str(manager_cik),
                    "manager_name": watchlist_entry.manager_name if watchlist_entry is not None else str(manager_cik),
                }
            )
        return rows

    def _accession_number_for_filing(self, filing: object) -> str:
        return str(getattr(filing, "accession_number", None) or getattr(filing, "accession_no", "unknown-accession"))

    def _build_fallback_payload(self, filing: object, ticker: str) -> dict[str, object]:
        return {
            "ticker": ticker,
            "form": getattr(filing, "form", ""),
            "filing_date": str(getattr(filing, "filing_date", "")),
            "company_name": getattr(filing, "company", "") or getattr(filing, "company_name", ""),
            "accession_number": self._accession_number_for_filing(filing),
            "reporting_persons": [],
            "total_shares": None,
            "total_percent": None,
            "rule_designation": "",
            "issuer_name": "",
            "issuer_cusip": "",
            "security_title": "",
            "purpose_text": "",
        }

    def _write_payload(self, accession_number: str, payload: dict[str, object], source_mode: str, source_key: str) -> None:
        self._raw_repository.upsert_record(accession_number, payload)
        self._raw_repository.replace_reporting_person_rows(
            accession_number,
            self._build_reporting_person_rows(accession_number, payload),
        )
        self._raw_repository.upsert_sync_source_row(
            {
                "row_key": f"{accession_number}|{source_mode}|{source_key}",
                "accession_number": accession_number,
                "sync_mode": source_mode,
                "source_key": source_key,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _build_reporting_person_rows(self, accession_number: str, payload: dict[str, object]) -> list[dict[str, object]]:
        reporting_persons = payload.get("reporting_persons", [])
        rows: list[dict[str, object]] = []
        if not isinstance(reporting_persons, list):
            return rows
        for index, person in enumerate(reporting_persons, start=1):
            if not isinstance(person, dict):
                continue
            rows.append(
                {
                    "row_key": f"{accession_number}|{index}",
                    "accession_number": accession_number,
                    "person_index": index,
                    "reporting_person_name": str(person.get("name", "") or ""),
                    "reporting_person_cik": str(person.get("cik", "") or ""),
                    "reporting_person_type": str(person.get("type_of_reporting_person", "") or ""),
                    "aggregate_amount": person.get("aggregate_amount"),
                    "percent_of_class": person.get("percent_of_class"),
                    "sole_voting_power": person.get("sole_voting_power"),
                    "shared_voting_power": person.get("shared_voting_power"),
                    "sole_dispositive_power": person.get("sole_dispositive_power"),
                    "shared_dispositive_power": person.get("shared_dispositive_power"),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return rows

    def _load_local_manager_accession_map(self, manager_entries: list[dict[str, str]]) -> dict[str, set[str]]:
        if self._supabase_client is None:
            return {}
        manager_accessions = self._load_local_manager_accession_map_from_sync_sources(manager_entries)
        if manager_accessions:
            return manager_accessions
        rows: list[dict[str, object]] = []
        page_size = 1000
        offset = 0
        while True:
            page = self._supabase_client.fetch_rows(
                "raw_13dg_filings",
                limit=page_size,
                offset=offset,
                order="filing_date.desc",
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        manager_accessions = {}
        for row in rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            accession_number = str(row.get("accession_number", "") or payload.get("accession_number", "") or "").strip()
            if not accession_number:
                continue
            reporting_persons = payload.get("reporting_persons", [])
            if not isinstance(reporting_persons, list):
                continue
            for manager_entry in manager_entries:
                if self._payload_matches_manager(reporting_persons, manager_entry["manager_name"], manager_entry["manager_cik"]):
                    manager_accessions.setdefault(str(manager_entry["manager_cik"]), set()).add(accession_number)
        return manager_accessions

    def _load_local_manager_accession_map_from_sync_sources(
        self,
        manager_entries: list[dict[str, str]],
    ) -> dict[str, set[str]]:
        if self._supabase_client is None:
            return {}
        manager_accessions: dict[str, set[str]] = {}
        for manager_entry in manager_entries:
            try:
                rows = self._supabase_client.fetch_rows(
                    "raw_13dg_sync_sources",
                    limit=1000,
                    filters={
                        "sync_mode": "eq.manager",
                        "source_key": f"eq.{manager_entry['manager_cik']}",
                    },
                    order="synced_at.desc",
                )
            except SupabaseError:
                return {}
            if not rows:
                continue
            manager_accessions[str(manager_entry["manager_cik"])] = {
                str(row.get("accession_number", "") or "").strip()
                for row in rows
                if str(row.get("accession_number", "") or "").strip()
            }
        return manager_accessions

    def _payload_matches_manager(self, reporting_persons: list[object], manager_name: str, manager_cik: str) -> bool:
        normalized_manager_name = "".join(ch for ch in manager_name.lower() if ch.isalnum())
        normalized_manager_cik = "".join(ch for ch in str(manager_cik) if ch.isdigit())
        for person in reporting_persons:
            if not isinstance(person, dict):
                continue
            person_cik = "".join(ch for ch in str(person.get("cik", "") or "") if ch.isdigit())
            if normalized_manager_cik and person_cik and person_cik == normalized_manager_cik:
                return True
            person_name = "".join(ch for ch in str(person.get("name", "") or "").lower() if ch.isalnum())
            if not normalized_manager_name or not person_name:
                continue
            if person_name == normalized_manager_name or person_name in normalized_manager_name or normalized_manager_name in person_name:
                return True
        return False

    def _build_cursor(
        self,
        request: Sync13DGRequest,
        resolved_tickers: tuple[str, ...],
        resolved_manager_ciks: tuple[str, ...],
    ) -> dict[str, object]:
        mode = self._normalize_mode(request.mode)
        cursor: dict[str, object] = {"mode": mode}
        if mode == "manager":
            cursor["manager_ciks"] = list(resolved_manager_ciks)
        else:
            cursor["tickers"] = list(resolved_tickers)
        return cursor
