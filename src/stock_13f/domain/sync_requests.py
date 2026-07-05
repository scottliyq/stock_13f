"""Request dataclasses for backend sync services."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BaseSyncRequest:
    dry_run: bool = False
    log_level: str = "INFO"
    job_id: str | None = None


@dataclass(frozen=True)
class Sync13FRequest(BaseSyncRequest):
    mode: str = "incremental"
    quarters: int = 4
    latest_report_date: str | None = None
    top_limit: int = 100
    skip_download: bool = False
    enrich_openfigi: bool = False
    openfigi_batch_size: int = 10
    openfigi_sleep_seconds: float = 1.0


@dataclass(frozen=True)
class Sync8KRequest(BaseSyncRequest):
    days_back: int = 7
    date_from: str | None = None
    tickers: tuple[str, ...] = ()
    universe_source: str = "movers"
    max_filings: int = 100


@dataclass(frozen=True)
class Sync13DGRequest(BaseSyncRequest):
    mode: str = "issuer"
    days_back: int = 30
    date_from: str | None = None
    tickers: tuple[str, ...] = ()
    manager_ciks: tuple[str, ...] = ()
    manager_scope: str = "watchlist"
    universe_source: str = "dim"
    max_filings: int = 100
    form_scope: str = "all"


@dataclass(frozen=True)
class Audit13DGCoverageRequest(BaseSyncRequest):
    days_back: int = 180
    date_from: str | None = None
    manager_ciks: tuple[str, ...] = ()
    manager_scope: str = "watchlist"
    max_filings: int = 100
    form_scope: str = "all"


@dataclass(frozen=True)
class RebuildMartsRequest(BaseSyncRequest):
    rebuild: str = "all"
    export_legacy_csv: bool = False
    export_legacy_reports: bool = False
    top_limit_max: int = 100


@dataclass(frozen=True)
class BackfillTickersRequest(BaseSyncRequest):
    with_openfigi: bool = False
    openfigi_batch_size: int = 10
    openfigi_sleep_seconds: float = 3.0
    openfigi_max_batches: int = 0


@dataclass(frozen=True)
class SyncAllRequest(BaseSyncRequest):
    with_marts: bool = False
    fail_fast: bool = False
    sync_13f_request: Sync13FRequest | None = None
    sync_8k_request: Sync8KRequest | None = None
    sync_13dg_request: Sync13DGRequest | None = None
    rebuild_marts_request: RebuildMartsRequest | None = None


@dataclass(frozen=True)
class ShowStatusRequest(BaseSyncRequest):
    output_path: Path | None = None
