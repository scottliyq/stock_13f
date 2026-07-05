from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.services.backend_schedule_service import BackendScheduleService
from stock_13f.services.backend_schedule_service import BackendSchedulerConfig


ET = ZoneInfo("America/New_York")


@dataclass
class FakeResult:
    status: str = "success"
    rows_written: int = 1
    warnings: list[str] | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def sync_13f(self, request):
        self.calls.append(("sync-13f", request))
        return FakeResult()

    def sync_8k(self, request):
        self.calls.append(("sync-8k", request))
        return FakeResult()

    def sync_13dg(self, request):
        self.calls.append(("sync-13dg", request))
        return FakeResult()

    def audit_13dg_coverage(self, request):
        self.calls.append(("audit-13dg-coverage", request))
        return FakeResult()

    def rebuild_marts(self, request):
        self.calls.append(("rebuild-marts", request))
        return FakeResult()

    def sync_all(self, request):
        self.calls.append(("sync-all", request))
        return FakeResult()


def test_scheduler_config_loads_et_jobs_and_focus_windows(tmp_path: Path) -> None:
    config_path = tmp_path / "backend_schedule.toml"
    config_path.write_text(
        """
[scheduler]
timezone = "America/New_York"
poll_interval_seconds = 15

[[jobs]]
name = "sync_13g_daytime"
command = "sync-13dg"
schedule_type = "interval"
interval_minutes = 240
weekdays = ["mon", "wed", "fri"]
active_start = "08:00"
active_end = "20:00"
focus_dates = ["02-14", "05-15"]
focus_days_before = 1
focus_days_after = 2

[jobs.request]
form_scope = "13g"
max_filings = 50
""",
        encoding="utf-8",
    )

    config = BackendSchedulerConfig.load(config_path)

    assert config.timezone == "America/New_York"
    assert config.poll_interval_seconds == 15
    assert len(config.jobs) == 1
    job = config.jobs[0]
    assert job.name == "sync_13g_daytime"
    assert job.interval_minutes == 240
    assert job.request["form_scope"] == "13g"
    assert len(job.focus_windows) == 2


def test_scheduler_runs_only_matching_et_jobs() -> None:
    config = BackendSchedulerConfig.load(REPO_ROOT / "config" / "backend_schedule.toml")
    orchestrator = FakeOrchestrator()
    service = BackendScheduleService(config=config, orchestrator=orchestrator, dry_run=True)

    service.run_due_jobs(datetime(2026, 7, 6, 9, 30, tzinfo=ET))

    commands = [command for command, _ in orchestrator.calls]
    assert commands == ["sync-8k"]


def test_scheduler_triggers_13d_and_13g_on_focus_dates() -> None:
    config = BackendSchedulerConfig.load(REPO_ROOT / "config" / "backend_schedule.toml")
    orchestrator = FakeOrchestrator()
    service = BackendScheduleService(config=config, orchestrator=orchestrator, dry_run=True)

    service.run_due_jobs(datetime(2026, 5, 15, 12, 0, tzinfo=ET))

    commands = [command for command, _ in orchestrator.calls]
    assert commands == ["sync-8k", "sync-13dg", "sync-13dg"]
    assert orchestrator.calls[1][1].mode == "manager"
    assert orchestrator.calls[1][1].form_scope == "13d"
    assert orchestrator.calls[1][1].manager_scope == "watchlist"
    assert orchestrator.calls[2][1].mode == "manager"
    assert orchestrator.calls[2][1].form_scope == "13g"
    assert orchestrator.calls[2][1].manager_scope == "watchlist"


def test_scheduler_supports_audit_13dg_coverage_jobs(tmp_path: Path) -> None:
    config_path = tmp_path / "backend_schedule.toml"
    config_path.write_text(
        """
[scheduler]
timezone = "America/New_York"
poll_interval_seconds = 15

[[jobs]]
name = "audit_13dg"
command = "audit-13dg-coverage"
schedule_type = "interval"
interval_minutes = 240
weekdays = ["mon"]
active_start = "08:00"
active_end = "20:00"

[jobs.request]
days_back = 180
manager_scope = "watchlist"
form_scope = "all"
""",
        encoding="utf-8",
    )
    config = BackendSchedulerConfig.load(config_path)
    orchestrator = FakeOrchestrator()
    service = BackendScheduleService(config=config, orchestrator=orchestrator, dry_run=True)

    service.run_due_jobs(datetime(2026, 7, 6, 12, 0, tzinfo=ET))

    assert orchestrator.calls[0][0] == "audit-13dg-coverage"
    assert orchestrator.calls[0][1].days_back == 180


def test_scheduler_triggers_13f_peak_job_inside_focus_window() -> None:
    config = BackendSchedulerConfig.load(REPO_ROOT / "config" / "backend_schedule.toml")
    orchestrator = FakeOrchestrator()
    service = BackendScheduleService(config=config, orchestrator=orchestrator, dry_run=True)

    service.run_due_jobs(datetime(2026, 5, 15, 13, 0, tzinfo=ET))

    commands = [command for command, _ in orchestrator.calls]
    assert commands == ["sync-8k", "sync-13dg", "sync-13f"]
    assert orchestrator.calls[1][1].mode == "manager"
    assert orchestrator.calls[1][1].form_scope == "13d"
    assert orchestrator.calls[2][1].quarters == 1


def test_scheduler_triggers_daily_13dg_audit_after_close() -> None:
    config = BackendSchedulerConfig.load(REPO_ROOT / "config" / "backend_schedule.toml")
    orchestrator = FakeOrchestrator()
    service = BackendScheduleService(config=config, orchestrator=orchestrator, dry_run=True)

    service.run_due_jobs(datetime(2026, 7, 6, 20, 15, tzinfo=ET))

    commands = [command for command, _ in orchestrator.calls]
    assert commands == ["audit-13dg-coverage"]
    assert orchestrator.calls[0][1].manager_scope == "watchlist"
    assert orchestrator.calls[0][1].days_back == 180
