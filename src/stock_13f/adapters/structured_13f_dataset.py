"""Adapter around the existing structured 13F dataset export script."""

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class QuarterlyMoverBuildResult:
    latest_report_date: str
    report_dates: list[str]
    rows: list[dict[str, object]]


class Structured13FDatasetAdapter:
    """Wrap the current structured ZIP export pipeline for service reuse."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        scripts_dir = repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import export_13f_quarterly_rebalance_csv as export_module

        self._module = export_module

    def latest_available_report_date(self) -> str:
        return self._module.latest_available_report_date(self._module.date.today())

    def recent_report_dates(self, latest_report_date: str, quarter_count: int) -> list[str]:
        return self._module.recent_report_dates(latest_report_date, quarter_count)

    def build_quarterly_mover_rows(
        self,
        dataset_cache_dir: Path,
        user_agent: str,
        quarter_count: int,
        top_limit: int,
        latest_report_date: str | None,
        skip_download: bool,
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
        previous_quarter_data = None
        for report_date in comparison_report_dates_asc:
            zip_path = self._module.ensure_dataset_zip(
                report_date=report_date,
                cache_dir=dataset_cache_dir,
                user_agent=user_agent,
            )
            current_quarter_data = self._module.load_quarter_data(
                zip_path=zip_path,
                report_date=report_date,
            )
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
            previous_quarter_data = current_quarter_data

        return QuarterlyMoverBuildResult(
            latest_report_date=resolved_latest_report_date,
            report_dates=target_report_dates_desc,
            rows=rows,
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
