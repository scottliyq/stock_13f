"""Adapter around the existing structured 13F dataset export script."""

from dataclasses import dataclass
from dataclasses import field
from datetime import date
from pathlib import Path
import sys


@dataclass(frozen=True)
class QuarterlyMoverBuildResult:
    latest_report_date: str
    report_dates: list[str]
    rows: list[dict[str, object]]
    manager_rebalance_summary_rows: list[dict[str, object]] = field(default_factory=list)
    manager_rebalance_detail_rows: list[dict[str, object]] = field(default_factory=list)
    manager_security_latest_rows: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class ManagerRebalanceRow:
    ticker: str
    issuer: str
    cusip: str
    status: str
    previous_value_usd: int
    current_value_usd: int
    value_change_usd: int


@dataclass(frozen=True)
class ManagerRebalanceSnapshot:
    manager_cik: str
    manager_name: str
    report_date: str
    previous_report_date: str
    current_holding_count: int
    previous_holding_count: int
    status_counts: dict[str, int]
    rows: list[ManagerRebalanceRow]
    warning: str = ""


@dataclass(frozen=True)
class ManagerSecurityPosition:
    manager_cik: str
    manager_name: str
    report_date: str
    previous_report_date: str
    ticker: str
    issuer: str
    cusip: str
    status: str
    previous_value_usd: int
    current_value_usd: int
    value_change_usd: int
    found_in_current: bool
    found_in_previous: bool
    warning: str = ""


class Structured13FDatasetAdapter:
    """Wrap the current structured ZIP export pipeline for service reuse."""

    def __init__(self, repo_root: Path, export_module: object | None = None) -> None:
        self._repo_root = repo_root
        self._quarter_data_cache: dict[tuple[str, str], object] = {}
        if export_module is not None:
            self._module = export_module
            return
        scripts_dir = repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import export_13f_quarterly_rebalance_csv as export_module

        self._module = export_module

    def latest_available_report_date(self) -> str:
        return self._module.latest_available_report_date(self._module.date.today())

    def recent_report_dates(self, latest_report_date: str, quarter_count: int) -> list[str]:
        return self._module.recent_report_dates(latest_report_date, quarter_count)

    def build_manager_rebalance_snapshot(
        self,
        dataset_cache_dir: Path,
        report_date: str,
        manager_cik: int | str,
        top_limit: int,
    ) -> ManagerRebalanceSnapshot:
        normalized_manager_cik = self._normalize_manager_cik(manager_cik)
        previous_report_date = self._module.previous_quarter_end(date.fromisoformat(report_date)).isoformat()
        current_zip_path = self._module.dataset_zip_path(dataset_cache_dir, report_date)
        previous_zip_path = self._module.dataset_zip_path(dataset_cache_dir, previous_report_date)
        if not current_zip_path.exists() or not previous_zip_path.exists():
            warning = (
                f"Local 13F dataset is missing for {report_date} or {previous_report_date}; "
                "manager rebalance analysis is unavailable."
            )
            return ManagerRebalanceSnapshot(
                manager_cik=normalized_manager_cik,
                manager_name="",
                report_date=report_date,
                previous_report_date=previous_report_date,
                current_holding_count=0,
                previous_holding_count=0,
                status_counts=self._empty_status_counts(),
                rows=[],
                warning=warning,
            )

        current_quarter_data = self._load_quarter_data_cached(current_zip_path, report_date)
        previous_quarter_data = self._load_quarter_data_cached(previous_zip_path, previous_report_date)
        current_cik, current_holdings = self._resolve_manager_holdings(current_quarter_data.holdings_by_cik, normalized_manager_cik)
        previous_cik, previous_holdings = self._resolve_manager_holdings(
            previous_quarter_data.holdings_by_cik,
            normalized_manager_cik,
        )
        manager_name = self._resolve_manager_name(
            current_quarter_data.manager_names_by_cik,
            previous_quarter_data.manager_names_by_cik,
            current_cik,
            previous_cik,
            normalized_manager_cik,
        )
        if not current_holdings and not previous_holdings:
            warning = f"No 13F holdings were found for manager CIK {normalized_manager_cik} in {report_date}."
            return ManagerRebalanceSnapshot(
                manager_cik=normalized_manager_cik,
                manager_name=manager_name,
                report_date=report_date,
                previous_report_date=previous_report_date,
                current_holding_count=0,
                previous_holding_count=0,
                status_counts=self._empty_status_counts(),
                rows=[],
                warning=warning,
            )

        rows, status_counts = self._build_manager_rebalance_rows(
            current_holdings=current_holdings,
            previous_holdings=previous_holdings,
            top_limit=top_limit,
        )
        return ManagerRebalanceSnapshot(
            manager_cik=normalized_manager_cik,
            manager_name=manager_name,
            report_date=report_date,
            previous_report_date=previous_report_date,
            current_holding_count=len(current_holdings),
            previous_holding_count=len(previous_holdings),
            status_counts=status_counts,
            rows=rows,
        )

    def load_manager_security_position(
        self,
        dataset_cache_dir: Path,
        report_date: str,
        manager_cik: int | str,
        ticker: str = "",
        cusip: str = "",
    ) -> ManagerSecurityPosition:
        normalized_manager_cik = self._normalize_manager_cik(manager_cik)
        normalized_ticker = str(ticker or "").strip().upper()
        normalized_cusip = str(cusip or "").strip().upper()
        previous_report_date = self._module.previous_quarter_end(date.fromisoformat(report_date)).isoformat()
        current_zip_path = self._module.dataset_zip_path(dataset_cache_dir, report_date)
        previous_zip_path = self._module.dataset_zip_path(dataset_cache_dir, previous_report_date)
        if not current_zip_path.exists() or not previous_zip_path.exists():
            warning = (
                f"Local 13F dataset is missing for {report_date} or {previous_report_date}; "
                "manager security lookup is unavailable."
            )
            return ManagerSecurityPosition(
                manager_cik=normalized_manager_cik,
                manager_name="",
                report_date=report_date,
                previous_report_date=previous_report_date,
                ticker=normalized_ticker,
                issuer="",
                cusip=normalized_cusip,
                status="",
                previous_value_usd=0,
                current_value_usd=0,
                value_change_usd=0,
                found_in_current=False,
                found_in_previous=False,
                warning=warning,
            )

        current_quarter_data = self._load_quarter_data_cached(current_zip_path, report_date)
        previous_quarter_data = self._load_quarter_data_cached(previous_zip_path, previous_report_date)
        current_cik, current_holdings = self._resolve_manager_holdings(current_quarter_data.holdings_by_cik, normalized_manager_cik)
        previous_cik, previous_holdings = self._resolve_manager_holdings(
            previous_quarter_data.holdings_by_cik,
            normalized_manager_cik,
        )
        manager_name = self._resolve_manager_name(
            current_quarter_data.manager_names_by_cik,
            previous_quarter_data.manager_names_by_cik,
            current_cik,
            previous_cik,
            normalized_manager_cik,
        )
        current_holding = self._find_matching_holding(current_holdings, normalized_ticker, normalized_cusip)
        previous_holding = self._find_matching_holding(previous_holdings, normalized_ticker, normalized_cusip)
        if current_holding is None and previous_holding is None:
            warning = (
                f"No 13F holding matched manager CIK {normalized_manager_cik} "
                f"for ticker {normalized_ticker or '-'} / cusip {normalized_cusip or '-'} in {report_date}."
            )
            return ManagerSecurityPosition(
                manager_cik=normalized_manager_cik,
                manager_name=manager_name,
                report_date=report_date,
                previous_report_date=previous_report_date,
                ticker=normalized_ticker,
                issuer="",
                cusip=normalized_cusip,
                status="",
                previous_value_usd=0,
                current_value_usd=0,
                value_change_usd=0,
                found_in_current=False,
                found_in_previous=False,
                warning=warning,
            )

        reference = current_holding or previous_holding
        issuer, resolved_ticker = self._module.security_identity(
            getattr(reference, "cusip", ""),
            getattr(reference, "name_of_issuer", ""),
            getattr(reference, "title_of_class", ""),
        )
        resolved_cusip = str(getattr(reference, "cusip", "") or "").strip().upper()
        previous_value_usd = self._holding_value_usd(previous_holding)
        current_value_usd = self._holding_value_usd(current_holding)
        return ManagerSecurityPosition(
            manager_cik=normalized_manager_cik,
            manager_name=manager_name,
            report_date=report_date,
            previous_report_date=previous_report_date,
            ticker=resolved_ticker or normalized_ticker,
            issuer=issuer,
            cusip=resolved_cusip or normalized_cusip,
            status=self._classify_change_status(previous_holding, current_holding),
            previous_value_usd=previous_value_usd,
            current_value_usd=current_value_usd,
            value_change_usd=current_value_usd - previous_value_usd,
            found_in_current=current_holding is not None,
            found_in_previous=previous_holding is not None,
        )

    def build_quarterly_mover_rows(
        self,
        dataset_cache_dir: Path,
        user_agent: str,
        quarter_count: int,
        top_limit: int,
        latest_report_date: str | None,
        skip_download: bool,
        manager_ciks: set[str] | None = None,
    ) -> QuarterlyMoverBuildResult:
        resolved_latest_report_date = latest_report_date or self.latest_available_report_date()
        target_report_dates_desc = self._module.recent_report_dates(resolved_latest_report_date, quarter_count)
        comparison_report_dates_asc = list(
            reversed(self._module.recent_report_dates(resolved_latest_report_date, quarter_count + 1))
        )
        if not skip_download:
            for report_date in comparison_report_dates_asc:
                self._module.ensure_dataset_zip(
                    report_date=report_date,
                    cache_dir=dataset_cache_dir,
                    user_agent=user_agent,
                )

        rows: list[dict[str, object]] = []
        manager_rebalance_summary_rows: list[dict[str, object]] = []
        manager_rebalance_detail_rows: list[dict[str, object]] = []
        manager_security_latest_rows: list[dict[str, object]] = []
        previous_quarter_data = None
        for report_date in comparison_report_dates_asc:
            zip_path = self._module.ensure_dataset_zip(
                report_date=report_date,
                cache_dir=dataset_cache_dir,
                user_agent=user_agent,
            )
            current_quarter_data = self._load_quarter_data_cached(zip_path, report_date)
            if previous_quarter_data is not None and report_date in target_report_dates_desc:
                summaries = self._module.summarize_quarter(
                    current_data=current_quarter_data,
                    previous_data=previous_quarter_data,
                )
                for security_type in self._module.SECURITY_TYPES:
                    rows.extend(
                        self._module.build_csv_rows(
                            report_date=report_date,
                            summaries=summaries,
                            security_type=security_type,
                            top_limit=top_limit,
                        )
                    )
                summary_rows, detail_rows = self._build_manager_rebalance_dataset(
                    report_date=report_date,
                    current_quarter_data=current_quarter_data,
                    previous_quarter_data=previous_quarter_data,
                    manager_ciks=manager_ciks,
                )
                manager_security_latest_rows.extend(
                    self._build_manager_security_latest_dataset(
                        report_date=report_date,
                        current_quarter_data=current_quarter_data,
                        previous_quarter_data=previous_quarter_data,
                        manager_ciks=manager_ciks,
                    )
                )
                manager_rebalance_summary_rows.extend(summary_rows)
                manager_rebalance_detail_rows.extend(detail_rows)
            previous_quarter_data = current_quarter_data

        return QuarterlyMoverBuildResult(
            latest_report_date=resolved_latest_report_date,
            report_dates=target_report_dates_desc,
            rows=rows,
            manager_rebalance_summary_rows=manager_rebalance_summary_rows,
            manager_rebalance_detail_rows=manager_rebalance_detail_rows,
            manager_security_latest_rows=manager_security_latest_rows,
        )

    def export(
        self,
        dataset_cache_dir: Path,
        output_dir: Path,
        user_agent: str,
        quarter_count: int,
        top_limit: int,
        latest_report_date: str | None,
        skip_download: bool,
    ) -> list[Path]:
        return self._module.export_quarterly_rebalance_csvs(
            dataset_cache_dir=dataset_cache_dir,
            output_dir=output_dir,
            user_agent=user_agent,
            quarter_count=quarter_count,
            top_limit=top_limit,
            latest_report_date=latest_report_date,
            skip_download=skip_download,
        )

    def refresh_report_csvs(self, output_dir: Path) -> list[Path]:
        return self._module.refresh_report_csvs(output_dir)

    def enrich_cusip_ticker_map_with_openfigi(
        self,
        reports_dir: Path,
        batch_size: int,
        sleep_seconds: float,
    ) -> None:
        self._module.enrich_cusip_ticker_map_with_openfigi(
            map_path=self._module.CUSIP_TICKER_MAP_PATH,
            reports_dir=reports_dir,
            batch_size=batch_size,
            sleep_seconds=sleep_seconds,
        )

    def enrich_cusip_ticker_map_from_rows(
        self,
        rows: list[dict[str, object]],
        batch_size: int,
        sleep_seconds: float,
    ) -> int:
        scripts_dir = self._repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import enrich_cusip_ticker_map_openfigi as enrich_module

        existing_rows_by_cusip = enrich_module.load_existing_map(self._module.CUSIP_TICKER_MAP_PATH)
        missing_by_cusip: dict[str, object] = {}
        for row in rows:
            cusip = enrich_module.normalize_cusip(str(row.get("cusip", "") or ""))
            ticker = str(row.get("ticker", "") or "").strip().upper()
            issuer = str(row.get("issuer", "") or "").strip()
            security_type = str(row.get("security_type", "") or "stock").strip() or "stock"
            if not cusip or ticker or cusip in existing_rows_by_cusip:
                continue
            missing_by_cusip.setdefault(
                cusip,
                enrich_module.MissingCusip(
                    cusip=cusip,
                    issuer=issuer,
                    security_type=security_type,
                ),
            )
        if not missing_by_cusip:
            return 0

        new_rows: list[dict[str, str]] = []
        for batch in enrich_module.batched(list(missing_by_cusip.values()), batch_size):
            batch_rows = enrich_module.query_openfigi_batch_with_retry(
                batch=batch,
                sleep_seconds=sleep_seconds,
            )
            new_rows.extend(batch_rows)

        if not new_rows:
            return 0
        merged_rows = enrich_module.merge_rows(existing_rows_by_cusip, new_rows)
        enrich_module.write_map(self._module.CUSIP_TICKER_MAP_PATH, merged_rows)
        load_map = getattr(self._module, "load_cusip_ticker_map", None)
        if load_map is not None and hasattr(load_map, "cache_clear"):
            load_map.cache_clear()
        return len(new_rows)

    def _build_manager_rebalance_rows(
        self,
        current_holdings: dict[str, object],
        previous_holdings: dict[str, object],
        top_limit: int | None,
    ) -> tuple[list[ManagerRebalanceRow], dict[str, int]]:
        rows: list[ManagerRebalanceRow] = []
        status_counts = self._empty_status_counts()
        for security_key in sorted(current_holdings.keys() | previous_holdings.keys()):
            current_holding = current_holdings.get(security_key)
            previous_holding = previous_holdings.get(security_key)
            status = self._classify_change_status(previous_holding, current_holding)
            status_counts[status] += 1
            if status == "unchanged":
                continue
            reference = current_holding or previous_holding
            if reference is None:
                continue
            issuer, ticker = self._module.security_identity(
                getattr(reference, "cusip", ""),
                getattr(reference, "name_of_issuer", ""),
                getattr(reference, "title_of_class", ""),
            )
            previous_value_usd = self._holding_value_usd(previous_holding)
            current_value_usd = self._holding_value_usd(current_holding)
            rows.append(
                ManagerRebalanceRow(
                    ticker=ticker,
                    issuer=issuer,
                    cusip=str(getattr(reference, "cusip", "") or "").strip().upper(),
                    status=status,
                    previous_value_usd=previous_value_usd,
                    current_value_usd=current_value_usd,
                    value_change_usd=current_value_usd - previous_value_usd,
                )
            )
        rows.sort(
            key=lambda row: (
                -abs(row.value_change_usd),
                self._status_priority(row.status),
                row.ticker or row.issuer,
            )
        )
        if top_limit is None:
            return rows, status_counts
        return rows[:top_limit], status_counts

    def _build_manager_rebalance_dataset(
        self,
        report_date: str,
        current_quarter_data: object,
        previous_quarter_data: object,
        manager_ciks: set[str] | None = None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        current_holdings_by_cik = self._normalize_holdings_map(current_quarter_data.holdings_by_cik)
        previous_holdings_by_cik = self._normalize_holdings_map(previous_quarter_data.holdings_by_cik)
        current_names_by_cik = self._normalize_name_map(current_quarter_data.manager_names_by_cik)
        previous_names_by_cik = self._normalize_name_map(previous_quarter_data.manager_names_by_cik)
        summary_rows: list[dict[str, object]] = []
        detail_rows: list[dict[str, object]] = []
        for manager_cik in sorted(set(current_holdings_by_cik) | set(previous_holdings_by_cik)):
            if manager_ciks is not None and manager_cik not in manager_ciks:
                continue
            current_holdings = current_holdings_by_cik.get(manager_cik, {})
            previous_holdings = previous_holdings_by_cik.get(manager_cik, {})
            manager_name = current_names_by_cik.get(manager_cik) or previous_names_by_cik.get(manager_cik) or ""
            changed_rows, status_counts = self._build_manager_rebalance_rows(
                current_holdings=current_holdings,
                previous_holdings=previous_holdings,
                top_limit=None,
            )
            summary_rows.append(
                {
                    "row_key": f"{report_date}|{manager_cik}",
                    "report_date": report_date,
                    "previous_report_date": str(previous_quarter_data.report_date),
                    "manager_cik": int(manager_cik),
                    "manager_name": manager_name,
                    "current_holding_count": len(current_holdings),
                    "previous_holding_count": len(previous_holdings),
                    "new_count": status_counts["new"],
                    "increased_count": status_counts["increased"],
                    "decreased_count": status_counts["decreased"],
                    "exited_count": status_counts["exited"],
                    "unchanged_count": status_counts["unchanged"],
                }
            )
            for rank, row in enumerate(changed_rows, start=1):
                detail_rows.append(
                    {
                        "row_key": f"{report_date}|{manager_cik}|{rank}|{row.ticker or row.cusip}|{row.status}",
                        "report_date": report_date,
                        "previous_report_date": str(previous_quarter_data.report_date),
                        "manager_cik": int(manager_cik),
                        "manager_name": manager_name,
                        "rank": rank,
                        "ticker": row.ticker or None,
                        "issuer": row.issuer,
                        "cusip": row.cusip,
                        "status": row.status,
                        "previous_value_usd": row.previous_value_usd,
                        "current_value_usd": row.current_value_usd,
                        "value_change_usd": row.value_change_usd,
                    }
                )
        return summary_rows, detail_rows

    def _build_manager_security_latest_dataset(
        self,
        report_date: str,
        current_quarter_data: object,
        previous_quarter_data: object,
        manager_ciks: set[str] | None = None,
    ) -> list[dict[str, object]]:
        current_holdings_by_cik = self._normalize_holdings_map(current_quarter_data.holdings_by_cik)
        previous_holdings_by_cik = self._normalize_holdings_map(previous_quarter_data.holdings_by_cik)
        current_names_by_cik = self._normalize_name_map(current_quarter_data.manager_names_by_cik)
        previous_names_by_cik = self._normalize_name_map(previous_quarter_data.manager_names_by_cik)
        rows: list[dict[str, object]] = []
        for manager_cik in sorted(set(current_holdings_by_cik) | set(previous_holdings_by_cik)):
            if manager_ciks is not None and manager_cik not in manager_ciks:
                continue
            current_holdings = current_holdings_by_cik.get(manager_cik, {})
            previous_holdings = previous_holdings_by_cik.get(manager_cik, {})
            manager_name = current_names_by_cik.get(manager_cik) or previous_names_by_cik.get(manager_cik) or ""
            for security_key in sorted(set(current_holdings) | set(previous_holdings)):
                current_holding = current_holdings.get(security_key)
                previous_holding = previous_holdings.get(security_key)
                reference = current_holding or previous_holding
                if reference is None:
                    continue
                issuer, ticker = self._module.security_identity(
                    getattr(reference, "cusip", ""),
                    getattr(reference, "name_of_issuer", ""),
                    getattr(reference, "title_of_class", ""),
                )
                cusip = str(getattr(reference, "cusip", "") or "").strip().upper()
                previous_value_usd = self._holding_value_usd(previous_holding)
                current_value_usd = self._holding_value_usd(current_holding)
                status = self._classify_change_status(previous_holding, current_holding)
                rows.append(
                    {
                        "row_key": f"{report_date}|{manager_cik}|{cusip}|{ticker or issuer}",
                        "report_date": report_date,
                        "previous_report_date": str(previous_quarter_data.report_date),
                        "manager_cik": int(manager_cik),
                        "manager_name": manager_name,
                        "ticker": ticker or None,
                        "issuer": issuer,
                        "cusip": cusip,
                        "status": status,
                        "previous_value_usd": previous_value_usd,
                        "current_value_usd": current_value_usd,
                        "value_change_usd": current_value_usd - previous_value_usd,
                        "found_in_current": current_holding is not None,
                        "found_in_previous": previous_holding is not None,
                    }
                )
        return rows

    def _load_quarter_data_cached(self, zip_path: Path, report_date: str) -> object:
        cache_key = (str(zip_path), report_date)
        quarter_data = self._quarter_data_cache.get(cache_key)
        if quarter_data is not None:
            return quarter_data
        quarter_data = self._module.load_quarter_data(zip_path, report_date)
        self._quarter_data_cache[cache_key] = quarter_data
        return quarter_data

    def _normalize_holdings_map(
        self,
        holdings_by_cik: dict[str, dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        normalized: dict[str, dict[str, object]] = {}
        for manager_cik, holdings in holdings_by_cik.items():
            normalized[self._normalize_manager_cik(manager_cik)] = holdings
        return normalized

    def _normalize_name_map(self, names_by_cik: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for manager_cik, manager_name in names_by_cik.items():
            normalized[self._normalize_manager_cik(manager_cik)] = str(manager_name)
        return normalized

    def _resolve_manager_holdings(
        self,
        holdings_by_cik: dict[str, dict[str, object]],
        manager_cik: str,
    ) -> tuple[str, dict[str, object]]:
        for candidate_cik, holdings in holdings_by_cik.items():
            if self._normalize_manager_cik(candidate_cik) == manager_cik:
                return str(candidate_cik), holdings
        return "", {}

    def _resolve_manager_name(
        self,
        current_names_by_cik: dict[str, str],
        previous_names_by_cik: dict[str, str],
        current_cik: str,
        previous_cik: str,
        manager_cik: str,
    ) -> str:
        if current_cik:
            name = current_names_by_cik.get(current_cik, "")
            if name:
                return str(name)
        if previous_cik:
            name = previous_names_by_cik.get(previous_cik, "")
            if name:
                return str(name)
        for names_by_cik in (current_names_by_cik, previous_names_by_cik):
            for candidate_cik, candidate_name in names_by_cik.items():
                if self._normalize_manager_cik(candidate_cik) == manager_cik:
                    return str(candidate_name)
        return ""

    def _find_matching_holding(
        self,
        holdings: dict[str, object],
        ticker: str,
        cusip: str,
    ) -> object | None:
        normalized_ticker = str(ticker or "").strip().upper()
        normalized_cusip = str(cusip or "").strip().upper()
        for holding in holdings.values():
            holding_cusip = str(getattr(holding, "cusip", "") or "").strip().upper()
            issuer, holding_ticker = self._module.security_identity(
                holding_cusip,
                getattr(holding, "name_of_issuer", ""),
                getattr(holding, "title_of_class", ""),
            )
            del issuer
            if normalized_cusip and holding_cusip == normalized_cusip:
                return holding
            if normalized_ticker and str(holding_ticker or "").strip().upper() == normalized_ticker:
                return holding
        return None

    def _classify_change_status(self, previous_holding: object | None, current_holding: object | None) -> str:
        if previous_holding is None and current_holding is not None:
            return "new"
        if previous_holding is not None and current_holding is None:
            return "exited"
        previous_value_usd = self._holding_value_usd(previous_holding)
        current_value_usd = self._holding_value_usd(current_holding)
        if current_value_usd > previous_value_usd:
            return "increased"
        if current_value_usd < previous_value_usd:
            return "decreased"
        return "unchanged"

    def _holding_value_usd(self, holding: object | None) -> int:
        return int(getattr(holding, "value_usd", 0) or 0)

    def _normalize_manager_cik(self, value: int | str) -> str:
        normalized = str(value).strip()
        if not normalized:
            return ""
        stripped = normalized.lstrip("0")
        return stripped or "0"

    def _status_priority(self, status: str) -> int:
        priorities = {
            "new": 0,
            "increased": 1,
            "decreased": 2,
            "exited": 3,
            "unchanged": 4,
        }
        return priorities.get(status, 99)

    def _empty_status_counts(self) -> dict[str, int]:
        return {
            "new": 0,
            "increased": 0,
            "decreased": 0,
            "exited": 0,
            "unchanged": 0,
        }
