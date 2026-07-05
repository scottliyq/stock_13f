"""Backfill missing ticker fields in Supabase marts."""

from collections import Counter
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.sync_requests import BackfillTickersRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.repositories.marts import MartsRepository
from stock_13f.repositories.security_identifiers import normalize_issuer_name
from stock_13f.repositories.security_identifiers import SecurityIdentifierRepository


SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
MAX_UNRESOLVED_SAMPLES = 20


class TickerBackfillService:
    """Backfill missing tickers using local mappings, SEC caches, and optional OpenFIGI enrichment."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        repository: MartsRepository | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        self._repository = repository or MartsRepository(
            settings.paths.marts_dir,
            supabase_client=build_supabase_client(settings),
        )

    def backfill(self, request: BackfillTickersRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        try:
            warnings.extend(self._refresh_sec_company_caches())
            source_tables = self._load_table_rows()
            self._validate_source_tables(source_tables)
            before_missing = self._missing_summary(source_tables)
            if request.dry_run:
                result = SyncResult.success(
                    job_name="backfill-tickers",
                    started_at=started_at,
                    checkpoints_updated=1,
                    warnings=warnings,
                    details={
                        "before_missing": before_missing,
                        "with_openfigi": request.with_openfigi,
                    },
                )
                self._checkpoints.record_result(result, cursor={"job": "backfill-tickers"})
                return result

            openfigi_added = 0
            if request.with_openfigi:
                openfigi_added = self._enrich_missing_cusips_with_openfigi(
                    tables=source_tables,
                    batch_size=request.openfigi_batch_size,
                    sleep_seconds=request.openfigi_sleep_seconds,
                    max_batches=request.openfigi_max_batches,
                    warnings=warnings,
                )

            normalized_tables, resolution_stats = self._normalize_tables(source_tables)
            rows_written = self._replace_tables(normalized_tables)
            after_missing = self._missing_summary(normalized_tables)
            result = SyncResult.success(
                job_name="backfill-tickers",
                started_at=started_at,
                rows_written=rows_written,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "before_missing": before_missing,
                    "after_missing": after_missing,
                    "resolution_stats": resolution_stats,
                    "openfigi_mappings_added": openfigi_added,
                },
            )
        except SupabaseError as exc:
            result = SyncResult.failed(
                job_name="backfill-tickers",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={},
            )
        self._checkpoints.record_result(result, cursor={"job": "backfill-tickers"})
        return result

    def _company_tickers_cache_path(self) -> Path:
        return self._settings.paths.data_dir / "sec_company_tickers.json"

    def _company_tickers_exchange_cache_path(self) -> Path:
        return self._settings.paths.data_dir / "sec_company_tickers_exchange.json"

    def _refresh_sec_company_caches(self) -> list[str]:
        warnings: list[str] = []
        warnings.extend(self._write_json_cache(self._company_tickers_cache_path(), SEC_COMPANY_TICKERS_URL))
        warnings.extend(
            self._write_json_cache(
                self._company_tickers_exchange_cache_path(),
                SEC_COMPANY_TICKERS_EXCHANGE_URL,
            )
        )
        return warnings

    def _write_json_cache(self, output_path: Path, url: str) -> list[str]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = Request(url, headers={"User-Agent": self._settings.edgar_identity})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            if output_path.exists():
                return [f"Cache refresh skipped for {output_path.name}: {exc}"]
            raise SupabaseError(f"Unable to refresh required SEC cache {output_path.name}: {exc}") from exc
        output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return []

    def _load_table_rows(self) -> dict[str, list[dict[str, object]]]:
        return {
            "mart_13f_quarterly_movers": self._fetch_all_pages(
                self._repository.fetch_quarterly_movers,
                order="report_date.asc,security_type.asc,ranking_type.asc,rank.asc",
            ),
            "mart_manager_rebalance_detail": self._fetch_all_pages(
                self._repository.fetch_manager_rebalance_details,
                order="report_date.asc,manager_cik.asc,rank.asc",
            ),
            "mart_manager_security_latest": self._fetch_all_pages(
                self._repository.fetch_manager_security_latest_rows,
                order="report_date.asc,manager_cik.asc,cusip.asc",
            ),
        }

    def _fetch_all_pages(self, fetch_fn, order: str) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        offset = 0
        page_size = 1000
        while True:
            page = fetch_fn(limit=page_size, offset=offset, order=order)
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def _missing_summary(self, tables: dict[str, list[dict[str, object]]]) -> dict[str, object]:
        summary: dict[str, object] = {}
        for table_name, rows in tables.items():
            missing_rows = [row for row in rows if not str(row.get("ticker", "") or "").strip()]
            summary[table_name] = {
                "missing_count": len(missing_rows),
                "samples": [
                    {
                        "cusip": str(row.get("cusip", "") or ""),
                        "issuer": str(row.get("issuer", "") or row.get("company_name", "") or ""),
                    }
                    for row in missing_rows[:MAX_UNRESOLVED_SAMPLES]
                ],
            }
        return summary

    def _validate_source_tables(self, tables: dict[str, list[dict[str, object]]]) -> None:
        empty_tables = [table_name for table_name, rows in tables.items() if not rows]
        if empty_tables:
            joined = ", ".join(sorted(empty_tables))
            raise SupabaseError(
                f"Refusing to backfill tickers because source mart table(s) are empty: {joined}. "
                "Restore the marts with sync-13f before running backfill-tickers again."
            )

    def _build_known_issuer_map(self, tables: dict[str, list[dict[str, object]]]) -> dict[str, str]:
        issuer_candidates: dict[str, Counter[str]] = defaultdict(Counter)
        for rows in tables.values():
            for row in rows:
                ticker = str(row.get("ticker", "") or "").strip().upper()
                issuer = normalize_issuer_name(str(row.get("issuer", "") or row.get("company_name", "") or ""))
                if ticker and issuer:
                    issuer_candidates[issuer][ticker] += 1
        known_map: dict[str, str] = {}
        for issuer, counts in issuer_candidates.items():
            if len(counts) == 1:
                known_map[issuer] = next(iter(counts.keys()))
        return known_map

    def _security_identifiers(self) -> SecurityIdentifierRepository:
        return SecurityIdentifierRepository(
            self._settings.paths.data_dir / "cusip_ticker_map.csv",
            (
                self._company_tickers_cache_path(),
                self._company_tickers_exchange_cache_path(),
            ),
        )

    def _resolve_row_ticker(
        self,
        row: dict[str, object],
        identifiers: SecurityIdentifierRepository,
        known_issuer_map: dict[str, str],
    ) -> str:
        issuer = str(row.get("issuer", "") or row.get("company_name", "") or "")
        ticker = identifiers.resolve_ticker(
            str(row.get("cusip", "") or ""),
            str(row.get("ticker", "") or ""),
            issuer,
        )
        if ticker:
            return ticker
        return known_issuer_map.get(normalize_issuer_name(issuer), "")

    def _normalize_tables(
        self,
        source_tables: dict[str, list[dict[str, object]]],
    ) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
        identifiers = self._security_identifiers()
        known_issuer_map = self._build_known_issuer_map(source_tables)
        normalized_tables: dict[str, list[dict[str, object]]] = {}
        stats: dict[str, object] = {}
        for table_name, rows in source_tables.items():
            normalized_rows_by_key: dict[str, dict[str, object]] = {}
            updated_count = 0
            unresolved_samples: list[dict[str, str]] = []
            for row in rows:
                ticker = self._resolve_row_ticker(row, identifiers, known_issuer_map)
                normalized_row = self._normalize_table_row(table_name, row, ticker)
                normalized_rows_by_key[str(normalized_row["row_key"])] = normalized_row
                previous_ticker = str(row.get("ticker", "") or "").strip().upper()
                if ticker and ticker != previous_ticker:
                    updated_count += 1
                if not ticker and len(unresolved_samples) < MAX_UNRESOLVED_SAMPLES:
                    unresolved_samples.append(
                        {
                            "cusip": str(row.get("cusip", "") or ""),
                            "issuer": str(row.get("issuer", "") or row.get("company_name", "") or ""),
                        }
                    )
            normalized_rows = list(normalized_rows_by_key.values())
            normalized_tables[table_name] = normalized_rows
            stats[table_name] = {
                "updated": updated_count,
                "deduped": len(rows) - len(normalized_rows),
                "remaining_unresolved": sum(
                    1 for row in normalized_rows if not str(row.get("ticker", "") or "").strip()
                ),
                "samples": unresolved_samples,
            }
        return normalized_tables, stats

    def _normalize_table_row(
        self,
        table_name: str,
        row: dict[str, object],
        ticker: str,
    ) -> dict[str, object]:
        normalized_row = dict(row)
        normalized_ticker = ticker or None
        cusip = str(row.get("cusip", "") or "").strip().upper()
        issuer = str(row.get("issuer", "") or row.get("company_name", "") or "").strip()
        normalized_row["ticker"] = normalized_ticker
        normalized_row["cusip"] = cusip
        normalized_row["issuer"] = issuer
        if table_name == "mart_13f_quarterly_movers":
            normalized_row["row_key"] = (
                f"{row['report_date']}|{row['security_type']}|{row['ranking_type']}|{cusip}|{ticker or issuer}"
            )
            return normalized_row
        if table_name == "mart_manager_rebalance_detail":
            normalized_row["row_key"] = (
                f"{row['report_date']}|{row['manager_cik']}|{row['rank']}|{ticker or cusip}|{row['status']}"
            )
            return normalized_row
        normalized_row["row_key"] = f"{row['report_date']}|{row['manager_cik']}|{cusip}|{ticker or issuer}"
        return normalized_row

    def _replace_tables(self, tables: dict[str, list[dict[str, object]]]) -> int:
        rows_written = 0
        mover_rows = tables["mart_13f_quarterly_movers"]
        detail_rows = tables["mart_manager_rebalance_detail"]
        security_rows = tables["mart_manager_security_latest"]
        rows_written += self._repository.replace_quarterly_movers(
            report_dates=sorted({str(row["report_date"]) for row in mover_rows}),
            rows=mover_rows,
        )
        rows_written += self._repository.replace_manager_rebalance_details(
            report_dates=sorted({str(row["report_date"]) for row in detail_rows}),
            rows=detail_rows,
        )
        rows_written += self._repository.replace_manager_security_latest_rows(
            report_dates=sorted({str(row["report_date"]) for row in security_rows}),
            rows=security_rows,
        )
        return rows_written

    def _enrich_missing_cusips_with_openfigi(
        self,
        tables: dict[str, list[dict[str, object]]],
        batch_size: int,
        sleep_seconds: float,
        max_batches: int,
        warnings: list[str],
    ) -> int:
        import sys

        scripts_dir = self._settings.paths.scripts_dir
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import enrich_cusip_ticker_map_openfigi as enrich_module

        existing_rows_by_cusip = enrich_module.load_existing_map(self._settings.paths.data_dir / "cusip_ticker_map.csv")
        missing_by_cusip: dict[str, object] = {}
        for rows in tables.values():
            for row in rows:
                if str(row.get("ticker", "") or "").strip():
                    continue
                cusip = enrich_module.normalize_cusip(str(row.get("cusip", "") or ""))
                if not cusip or cusip in existing_rows_by_cusip:
                    continue
                missing_by_cusip.setdefault(
                    cusip,
                    enrich_module.MissingCusip(
                        cusip=cusip,
                        issuer=str(row.get("issuer", "") or row.get("company_name", "") or "").strip(),
                        security_type=str(row.get("security_type", "") or "stock").strip() or "stock",
                    ),
                )
        if not missing_by_cusip:
            return 0

        batches = enrich_module.batched(list(missing_by_cusip.values()), batch_size)
        if max_batches > 0:
            batches = batches[:max_batches]
        new_rows: list[dict[str, str]] = []
        for batch_index, batch in enumerate(batches, start=1):
            try:
                batch_rows = enrich_module.query_openfigi_batch_with_retry(
                    batch=batch,
                    sleep_seconds=sleep_seconds,
                )
            except (HTTPError, URLError, TimeoutError) as exc:
                warnings.append(f"OpenFIGI batch {batch_index} skipped: {exc}")
                continue
            new_rows.extend(batch_rows)
        if not new_rows:
            return 0
        merged_rows = enrich_module.merge_rows(existing_rows_by_cusip, new_rows)
        enrich_module.write_map(self._settings.paths.data_dir / "cusip_ticker_map.csv", merged_rows)
        return len(new_rows)
