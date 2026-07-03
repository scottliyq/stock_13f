"""13D/G sync service implementation."""

from datetime import datetime, timezone
import logging

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


LOGGER = logging.getLogger("stock_13f.services.sync_13dg")


class ThirteenDGSyncService:
    """Sync 13D/13G filings for an explicit ticker list using edgartools."""

    def __init__(
        self,
        settings: Settings,
        checkpoints: CheckpointRepository,
        raw_repository: Raw13DGRepository | None = None,
        edgar_client: EdgarToolsClient | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoints = checkpoints
        supabase_client = build_supabase_client(settings)
        self._edgar_client = edgar_client or EdgarToolsClient()
        self._raw_repository = raw_repository or Raw13DGRepository(
            settings.paths.raw_13dg_dir,
            supabase_client=supabase_client,
        )
        self._security_universe = SecurityUniverseRepository(supabase_client)

    def sync(self, request: Sync13DGRequest) -> SyncResult:
        started_at = datetime.now(timezone.utc)
        warnings = self._settings.validate_edgar() + self._settings.validate_supabase()
        self._settings.ensure_directories()
        apply_edgar_environment(self._settings)
        resolved_tickers = request.tickers or self._security_universe.resolve(request.universe_source)
        if request.dry_run:
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings + ["13D/G dry-run does not contact EDGAR."],
                details={
                    "tickers": list(resolved_tickers),
                    "days_back": request.days_back,
                    "universe_source": request.universe_source,
                },
            )
            self._checkpoints.record_result(result, cursor={"tickers": list(resolved_tickers)})
            return result
        if not resolved_tickers:
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=0,
                checkpoints_updated=1,
                warnings=warnings + ["No tickers were provided; sync-13dg completed without contacting EDGAR."],
                details={"tickers": []},
            )
            self._checkpoints.record_result(result, cursor={"tickers": []})
            return result
        try:
            records_written = 0
            for ticker in resolved_tickers:
                try:
                    filings = self._edgar_client.search_company_filings(
                        ticker=ticker,
                        forms=("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"),
                        days_back=request.days_back,
                        date_from=request.date_from,
                        max_filings=request.max_filings,
                    )
                except EdgarTickerLookupError as exc:
                    warnings.append(str(exc))
                    continue
                for filing in filings:
                    accession_number = getattr(filing, "accession_number", None) or getattr(
                        filing, "accession_no", "unknown-accession"
                    )
                    payload = {
                        "ticker": ticker,
                        "form": getattr(filing, "form", ""),
                        "filing_date": str(getattr(filing, "filing_date", "")),
                        "company_name": getattr(filing, "company", "") or getattr(filing, "company_name", ""),
                    }
                    self._raw_repository.upsert_record(str(accession_number), payload)
                    records_written += 1
            LOGGER.info("sync_13dg_completed", extra={"rows_written": records_written})
            result = SyncResult.success(
                job_name="sync-13dg",
                started_at=started_at,
                rows_written=records_written,
                checkpoints_updated=1,
                warnings=warnings,
                details={"tickers": list(resolved_tickers), "universe_source": request.universe_source},
            )
        except (EdgarToolsUnavailable, SupabaseError) as exc:
            result = SyncResult.failed(
                job_name="sync-13dg",
                started_at=started_at,
                error_summary=str(exc),
                warnings=warnings,
                details={"tickers": list(resolved_tickers)},
            )
        self._checkpoints.record_result(result, cursor={"tickers": list(resolved_tickers)})
        return result
