from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.adapters.structured_13f_dataset import Structured13FDatasetAdapter


@dataclass(frozen=True)
class FakeManagerHolding:
    name_of_issuer: str
    title_of_class: str
    cusip: str
    put_call: str
    value_usd: int


@dataclass(frozen=True)
class FakeQuarterData:
    report_date: str
    manager_names_by_cik: dict[str, str]
    holdings_by_cik: dict[str, dict[str, FakeManagerHolding]]


class FakeExportModule:
    def __init__(self, current: FakeQuarterData, previous: FakeQuarterData) -> None:
        self._current = current
        self._previous = previous
        self.load_calls = 0

    def previous_quarter_end(self, report_date: date) -> date:
        assert report_date == date(2026, 3, 31)
        return date(2025, 12, 31)

    def dataset_zip_path(self, cache_dir: Path, report_date: str) -> Path:
        return cache_dir / f"{report_date}.zip"

    def load_quarter_data(self, zip_path: Path, report_date: str) -> FakeQuarterData:
        assert zip_path.exists()
        self.load_calls += 1
        if report_date == self._current.report_date:
            return self._current
        return self._previous

    def security_identity(self, cusip: str, name_of_issuer: str, title_of_class: str) -> tuple[str, str]:
        del title_of_class
        mapping = {
            "037833100": ("Apple Inc. (AAPL)", "AAPL"),
            "594918104": ("Microsoft Corp. (MSFT)", "MSFT"),
            "67066G104": ("NVIDIA Corp. (NVDA)", "NVDA"),
            "88160R101": ("Tesla, Inc. (TSLA)", "TSLA"),
        }
        return mapping[cusip]


class CacheOnlyExportModule:
    SECURITY_TYPES = ("stock", "etf")

    def __init__(self) -> None:
        self.ensure_calls = 0

    def recent_report_dates(self, latest_report_date: str, quarter_count: int) -> list[str]:
        del latest_report_date
        return ["2026-03-31", "2025-12-31"][:quarter_count]

    def dataset_zip_path(self, cache_dir: Path, report_date: str) -> Path:
        return cache_dir / f"{report_date}.zip"

    def ensure_dataset_zip(self, report_date: str, cache_dir: Path, user_agent: str) -> Path:
        del report_date, cache_dir, user_agent
        self.ensure_calls += 1
        raise AssertionError("cache-only builds must not call the downloader")

    def load_quarter_data(self, zip_path: Path, report_date: str) -> FakeQuarterData:
        assert zip_path.exists()
        return FakeQuarterData(report_date=report_date, manager_names_by_cik={}, holdings_by_cik={})

    def summarize_quarter(
        self,
        current_data: FakeQuarterData,
        previous_data: FakeQuarterData,
    ) -> list[dict[str, object]]:
        del current_data, previous_data
        return []

    def build_csv_rows(
        self,
        report_date: str,
        summaries: list[dict[str, object]],
        security_type: str,
        top_limit: int,
    ) -> list[dict[str, object]]:
        del report_date, summaries, security_type, top_limit
        return []


def test_build_quarterly_mover_rows_cache_only_does_not_download(tmp_path: Path) -> None:
    module = CacheOnlyExportModule()
    adapter = Structured13FDatasetAdapter(REPO_ROOT, export_module=module)
    (tmp_path / "2026-03-31.zip").touch()
    (tmp_path / "2025-12-31.zip").touch()

    result = adapter.build_quarterly_mover_rows(
        dataset_cache_dir=tmp_path,
        user_agent="test-agent",
        quarter_count=1,
        top_limit=100,
        latest_report_date="2026-03-31",
        skip_download=True,
    )

    assert result.report_dates == ["2026-03-31"]
    assert result.rows == []
    assert module.ensure_calls == 0


def test_build_manager_rebalance_snapshot_summarizes_latest_manager_changes(tmp_path: Path) -> None:
    previous = FakeQuarterData(
        report_date="2025-12-31",
        manager_names_by_cik={"0001234567": "Example Capital"},
        holdings_by_cik={
            "0001234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 100),
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 80),
                "88160R101|COMMON|COM": FakeManagerHolding("TESLA INC", "COM", "88160R101", "", 50),
            }
        },
    )
    current = FakeQuarterData(
        report_date="2026-03-31",
        manager_names_by_cik={"1234567": "Example Capital"},
        holdings_by_cik={
            "1234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 160),
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 20),
                "67066G104|COMMON|COM": FakeManagerHolding("NVIDIA CORP", "COM", "67066G104", "", 120),
            }
        },
    )
    module = FakeExportModule(current=current, previous=previous)
    adapter = Structured13FDatasetAdapter(REPO_ROOT, export_module=module)
    (tmp_path / "2026-03-31.zip").touch()
    (tmp_path / "2025-12-31.zip").touch()

    snapshot = adapter.build_manager_rebalance_snapshot(
        dataset_cache_dir=tmp_path,
        report_date="2026-03-31",
        manager_cik=1234567,
        top_limit=10,
    )

    assert snapshot.manager_name == "Example Capital"
    assert snapshot.previous_report_date == "2025-12-31"
    assert snapshot.current_holding_count == 3
    assert snapshot.previous_holding_count == 3
    assert snapshot.status_counts == {
        "new": 1,
        "increased": 1,
        "decreased": 1,
        "exited": 1,
        "unchanged": 0,
    }
    assert [row.ticker for row in snapshot.rows] == ["NVDA", "AAPL", "MSFT", "TSLA"]
    assert [row.status for row in snapshot.rows] == ["new", "increased", "decreased", "exited"]
    assert snapshot.rows[0].value_change_usd == 120
    assert snapshot.rows[-1].current_value_usd == 0


def test_build_manager_rebalance_snapshot_reuses_cached_quarter_data(tmp_path: Path) -> None:
    previous = FakeQuarterData(
        report_date="2025-12-31",
        manager_names_by_cik={
            "0001234567": "Example Capital",
            "0007654321": "Second Capital",
        },
        holdings_by_cik={
            "0001234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 100),
            },
            "0007654321": {
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 70),
            },
        },
    )
    current = FakeQuarterData(
        report_date="2026-03-31",
        manager_names_by_cik={
            "1234567": "Example Capital",
            "7654321": "Second Capital",
        },
        holdings_by_cik={
            "1234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 130),
            },
            "7654321": {
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 90),
            },
        },
    )
    module = FakeExportModule(current=current, previous=previous)
    adapter = Structured13FDatasetAdapter(REPO_ROOT, export_module=module)
    (tmp_path / "2026-03-31.zip").touch()
    (tmp_path / "2025-12-31.zip").touch()

    adapter.build_manager_rebalance_snapshot(
        dataset_cache_dir=tmp_path,
        report_date="2026-03-31",
        manager_cik=1234567,
        top_limit=10,
    )
    adapter.build_manager_rebalance_snapshot(
        dataset_cache_dir=tmp_path,
        report_date="2026-03-31",
        manager_cik=7654321,
        top_limit=10,
    )

    assert module.load_calls == 2


def test_build_manager_rebalance_dataset_filters_to_requested_manager_ciks() -> None:
    previous = FakeQuarterData(
        report_date="2025-12-31",
        manager_names_by_cik={
            "0001234567": "Example Capital",
            "0007654321": "Second Capital",
        },
        holdings_by_cik={
            "0001234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 100),
            },
            "0007654321": {
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 70),
            },
        },
    )
    current = FakeQuarterData(
        report_date="2026-03-31",
        manager_names_by_cik={
            "1234567": "Example Capital",
            "7654321": "Second Capital",
        },
        holdings_by_cik={
            "1234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 130),
            },
            "7654321": {
                "594918104|COMMON|COM": FakeManagerHolding("MICROSOFT CORP", "COM", "594918104", "", 90),
            },
        },
    )
    module = FakeExportModule(current=current, previous=previous)
    adapter = Structured13FDatasetAdapter(REPO_ROOT, export_module=module)

    summary_rows, detail_rows = adapter._build_manager_rebalance_dataset(
        report_date="2026-03-31",
        current_quarter_data=current,
        previous_quarter_data=previous,
        manager_ciks={"1234567"},
    )

    assert [row["manager_cik"] for row in summary_rows] == [1234567]
    assert [row["manager_cik"] for row in detail_rows] == [1234567]


def test_build_manager_security_latest_dataset_keeps_all_current_and_previous_positions() -> None:
    previous = FakeQuarterData(
        report_date="2025-12-31",
        manager_names_by_cik={"0001234567": "Example Capital"},
        holdings_by_cik={
            "0001234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 100),
                "88160R101|COMMON|COM": FakeManagerHolding("TESLA INC", "COM", "88160R101", "", 50),
            }
        },
    )
    current = FakeQuarterData(
        report_date="2026-03-31",
        manager_names_by_cik={"1234567": "Example Capital"},
        holdings_by_cik={
            "1234567": {
                "037833100|COMMON|COM": FakeManagerHolding("APPLE INC", "COM", "037833100", "", 160),
                "67066G104|COMMON|COM": FakeManagerHolding("NVIDIA CORP", "COM", "67066G104", "", 120),
            }
        },
    )
    module = FakeExportModule(current=current, previous=previous)
    adapter = Structured13FDatasetAdapter(REPO_ROOT, export_module=module)

    rows = adapter._build_manager_security_latest_dataset(
        report_date="2026-03-31",
        current_quarter_data=current,
        previous_quarter_data=previous,
        manager_ciks={"1234567"},
    )

    keyed = {row["ticker"]: row for row in rows}
    assert set(keyed) == {"AAPL", "NVDA", "TSLA"}
    assert keyed["AAPL"]["status"] == "increased"
    assert keyed["AAPL"]["current_value_usd"] == 160
    assert keyed["NVDA"]["status"] == "new"
    assert keyed["NVDA"]["found_in_current"] is True
    assert keyed["TSLA"]["status"] == "exited"
    assert keyed["TSLA"]["found_in_current"] is False
