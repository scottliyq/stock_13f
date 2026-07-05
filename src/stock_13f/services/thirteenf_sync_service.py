"""13F sync service implementation."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen

from stock_13f.adapters.structured_13f_dataset import Structured13FDatasetAdapter
from stock_13f.core.edgar import apply_edgar_environment
from stock_13f.core.settings import Settings
from stock_13f.core.supabase import build_supabase_client
from stock_13f.core.supabase import SupabaseError
from stock_13f.domain.manager_registry import list_default_managers
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_results import SyncResult
from stock_13f.repositories.checkpoints import CheckpointRepository
from stock_13f.repositories.marts import MartsRepository
from stock_13f.repositories.raw_13f import Raw13FRepository
from stock_13f.repositories.security_identifiers import SecurityIdentifierRepository


LOGGER = logging.getLogger("stock_13f.services.sync_13f")
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class ThirteenFSyncService:
    """Run the existing quarterly 13F export pipeline via a unified service API."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        adapter: Structured13FDatasetAdapter | None = None,
        raw_repository: Raw13FRepository | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        supabase_client = build_supabase_client(settings)
        self._adapter = adapter or Structured13FDatasetAdapter(settings.paths.repo_root)
        self._raw_repository = raw_repository or Raw13FRepository(
            settings.paths.backend_state_dir / "raw_13f_manifest.json",
            supabase_client=supabase_client,
        )
        self._marts_repository = MartsRepository(
            settings.paths.marts_dir,
            supabase_client=supabase_client,
        )
        self._security_identifiers = SecurityIdentifierRepository(
            settings.paths.data_dir / "cusip_ticker_map.csv",
            (
                settings.paths.data_dir / "sec_company_tickers.json",
                settings.paths.data_dir / "sec_company_tickers_exchange.json",
            ),
        )

    def _refresh_security_identifiers(self) -> None:
        self._security_identifiers = SecurityIdentifierRepository(
            self._settings.paths.data_dir / "cusip_ticker_map.csv",
            (
                self._settings.paths.data_dir / "sec_company_tickers.json",
                self._settings.paths.data_dir / "sec_company_tickers_exchange.json",
            ),
        )

    def _company_tickers_cache_path(self) -> Path:
        return self._settings.paths.data_dir / "sec_company_tickers.json"

    def _refresh_company_tickers_cache(self) -> None:
        cache_path = self._company_tickers_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            modified_at = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
            if (datetime.now(timezone.utc) - modified_at).total_seconds() < 86_400:
                return
        request = Request(
            SEC_COMPANY_TICKERS_URL,
            headers={"User-Agent": self._settings.edgar_identity},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _resolve_ticker(self, row: dict[str, object]) -> str:
        return self._security_identifiers.resolve_ticker(
            str(row.get("cusip", "") or ""),
            str(row.get("ticker", "") or ""),
            str(row.get("issuer", "") or row.get("company_name", "") or ""),
        )

    def _normalize_mover_row(self, row: dict[str, object]) -> dict[str, object]:
        report_date = str(row["report_date"])
        security_type = str(row["security_type"])
        ranking_type = str(row["ranking_type"])
        cusip = str(row["cusip"]).strip().upper()
        issuer = str(row["issuer"]).strip()
        ticker = self._resolve_ticker(row)
        row_key = f"{report_date}|{security_type}|{ranking_type}|{cusip}|{ticker or issuer}"
        return {
            "row_key": row_key,
            "report_date": report_date,
            "security_type": security_type,
            "ranking_type": ranking_type,
            "rank": int(row["rank"]),
            "issuer": issuer,
            "cusip": cusip,
            "ticker": ticker or None,
            "business_summary": str(row.get("business_summary", "") or "").strip(),
            "new_manager_count": int(row["new_manager_count"]),
            "new_entry_total_value_usd": int(row["new_entry_total_value_usd"]),
            "reduced_manager_count": int(row["reduced_manager_count"]),
            "reduced_total_value_usd": int(row["reduced_total_value_usd"]),
            "holder_manager_count": int(row["holder_manager_count"]),
            "total_holding_value_usd": int(row["total_holding_value_usd"]),
        }

    def _normalize_manager_rebalance_detail_row(self, row: dict[str, object]) -> dict[str, object]:
        report_date = str(row["report_date"])
        manager_cik = int(row["manager_cik"])
        rank = int(row["rank"])
        status = str(row["status"]).strip()
        ticker = self._resolve_ticker(row)
        cusip = str(row.get("cusip", "") or "").strip().upper()
        return {
            **dict(row),
            "row_key": f"{report_date}|{manager_cik}|{rank}|{ticker or cusip}|{status}",
            "ticker": ticker or None,
            "cusip": cusip,
            "issuer": str(row.get("issuer", "") or "").strip(),
        }

    def _normalize_manager_security_latest_row(self, row: dict[str, object]) -> dict[str, object]:
        report_date = str(row["report_date"])
        manager_cik = int(row["manager_cik"])
        ticker = self._resolve_ticker(row)
        cusip = str(row.get("cusip", "") or "").strip().upper()
        issuer = str(row.get("issuer", "") or "").strip()
        return {
            **dict(row),
            "row_key": f"{report_date}|{manager_cik}|{cusip}|{ticker or issuer}",
            "ticker": ticker or None,
            "cusip": cusip,
            "issuer": issuer,
        }

    def sync(self, request: Sync13FRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        apply_edgar_environment(self._settings)
        self._refresh_company_tickers_cache()
        self._refresh_security_identifiers()
        resolved_latest_report_date = request.latest_report_date or self._adapter.latest_available_report_date()
        if request.dry_run:
            report_dates = self._adapter.recent_report_dates(resolved_latest_report_date, request.quarters)
            result = SyncResult.success(
                job_name="sync-13f",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings,
                details={
                    "mode": request.mode,
                    "report_dates": report_dates,
                    "top_limit": request.top_limit,
                },
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result

        try:
            tracked_manager_ciks = {str(manager.manager_cik) for manager in list_default_managers() if manager.is_active}
            build_result = self._adapter.build_quarterly_mover_rows(
                dataset_cache_dir=self._settings.paths.data_dir / "13f_universe",
                user_agent=self._settings.edgar_identity,
                quarter_count=request.quarters,
                top_limit=request.top_limit,
                latest_report_date=resolved_latest_report_date,
                skip_download=request.skip_download,
                manager_ciks=tracked_manager_ciks,
            )
            if request.enrich_openfigi:
                security_rows_for_enrichment = [
                    *build_result.rows,
                    *build_result.manager_rebalance_detail_rows,
                    *build_result.manager_security_latest_rows,
                ]
                enriched_count = self._adapter.enrich_cusip_ticker_map_from_rows(
                    security_rows_for_enrichment,
                    batch_size=request.openfigi_batch_size,
                    sleep_seconds=request.openfigi_sleep_seconds,
                )
                warnings.append(f"enrich_openfigi added {enriched_count} cusip mappings for this sync run.")
                self._refresh_security_identifiers()
            mover_rows_by_key: dict[str, dict[str, object]] = {}
            for row in build_result.rows:
                normalized_row = self._normalize_mover_row(row)
                mover_rows_by_key[str(normalized_row["row_key"])] = normalized_row
            mover_rows = list(mover_rows_by_key.values())
            upserted_rows = self._marts_repository.replace_quarterly_movers(
                report_dates=build_result.report_dates,
                rows=mover_rows,
            )
            summary_rows_by_key = {
                str(row["row_key"]): dict(row) for row in build_result.manager_rebalance_summary_rows
            }
            detail_rows_by_key = {
                str(normalized_row["row_key"]): normalized_row
                for normalized_row in (
                    self._normalize_manager_rebalance_detail_row(row)
                    for row in build_result.manager_rebalance_detail_rows
                )
            }
            security_latest_rows_by_key = {
                str(normalized_row["row_key"]): normalized_row
                for normalized_row in (
                    self._normalize_manager_security_latest_row(row)
                    for row in build_result.manager_security_latest_rows
                )
            }
            upserted_rows += self._marts_repository.replace_manager_rebalance_summaries(
                report_dates=build_result.report_dates,
                rows=list(summary_rows_by_key.values()),
            )
            upserted_rows += self._marts_repository.replace_manager_rebalance_details(
                report_dates=build_result.report_dates,
                rows=list(detail_rows_by_key.values()),
            )
            upserted_rows += self._marts_repository.replace_manager_security_latest_rows(
                report_dates=build_result.report_dates,
                rows=list(security_latest_rows_by_key.values()),
            )
            manifest = {
                "latest_report_date": build_result.latest_report_date,
                "quarters": request.quarters,
                "top_limit": request.top_limit,
                "report_dates": build_result.report_dates,
                "row_count": len(mover_rows),
                "manager_rebalance_summary_count": len(summary_rows_by_key),
                "manager_rebalance_detail_count": len(detail_rows_by_key),
                "manager_security_latest_count": len(security_latest_rows_by_key),
                "output_paths": [],
            }
            self._raw_repository.write_manifest(manifest)
            LOGGER.info("sync_13f_completed", extra={"report_dates": build_result.report_dates, "row_count": len(mover_rows)})
            result = SyncResult.success(
                job_name="sync-13f",
                started_at=started_at,
                rows_written=upserted_rows,
                checkpoints_updated=1,
                warnings=warnings,
                details=manifest,
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result
        except SupabaseError as exc:
            result = SyncResult.failed(
                job_name="sync-13f",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            self._checkpoints.record_result(
                result,
                cursor={"latest_report_date": resolved_latest_report_date, "quarters": request.quarters},
            )
            return result
