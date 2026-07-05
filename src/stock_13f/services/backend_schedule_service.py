"""Config-driven backend scheduler built on top of schedule."""

from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import datetime
from datetime import time as clock_time
from datetime import timedelta
from pathlib import Path
from typing import Any
from typing import Callable
from zoneinfo import ZoneInfo
import logging
import time
import tomllib

import schedule

from stock_13f.domain.sync_requests import RebuildMartsRequest
from stock_13f.domain.sync_requests import Audit13DGCoverageRequest
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_requests import Sync8KRequest
from stock_13f.domain.sync_requests import SyncAllRequest
from stock_13f.services.backend_orchestrator import BackendOrchestrator


LOGGER = logging.getLogger("stock_13f.services.backend_schedule")

WEEKDAY_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

SUPPORTED_COMMANDS = {
    "sync-13f",
    "sync-8k",
    "sync-13dg",
    "audit-13dg-coverage",
    "rebuild-marts",
    "sync-all",
}


def _parse_clock_time(raw_value: str) -> clock_time:
    cleaned = raw_value.strip()
    try:
        return clock_time.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid time value {raw_value!r}; expected HH:MM or HH:MM:SS.") from exc


def _normalize_weekdays(raw_values: list[str] | tuple[str, ...]) -> tuple[int, ...]:
    normalized: list[int] = []
    for value in raw_values:
        key = value.strip().lower()
        if key not in WEEKDAY_INDEX:
            raise ValueError(f"Unsupported weekday {value!r}; expected one of {sorted(WEEKDAY_INDEX)}.")
        normalized.append(WEEKDAY_INDEX[key])
    return tuple(normalized)


def _normalize_tickers(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, str):
        return tuple(part.strip().upper() for part in raw_value.split(",") if part.strip())
    if isinstance(raw_value, list):
        return tuple(str(part).strip().upper() for part in raw_value if str(part).strip())
    raise ValueError("tickers must be either a comma-separated string or a list of strings.")


@dataclass(frozen=True)
class ActiveWindow:
    start: clock_time
    end: clock_time

    def contains(self, value: clock_time) -> bool:
        if self.start <= self.end:
            return self.start <= value <= self.end
        return value >= self.start or value <= self.end

    def anchor_minutes(self) -> int:
        return self.start.hour * 60 + self.start.minute


@dataclass(frozen=True)
class FocusWindow:
    month_day: str
    days_before: int = 0
    days_after: int = 0

    def contains(self, current_date: date) -> bool:
        month_text, day_text = self.month_day.split("-", maxsplit=1)
        focus_date = date(current_date.year, int(month_text), int(day_text))
        return focus_date - timedelta(days=self.days_before) <= current_date <= focus_date + timedelta(days=self.days_after)


@dataclass(frozen=True)
class ScheduledJobConfig:
    name: str
    command: str
    schedule_type: str
    weekdays: tuple[int, ...] = ()
    active_window: ActiveWindow | None = None
    interval_minutes: int | None = None
    times: tuple[clock_time, ...] = ()
    focus_windows: tuple[FocusWindow, ...] = ()
    request: dict[str, object] = field(default_factory=dict)

    def describe(self) -> str:
        weekday_labels = ",".join(sorted(WEEKDAY_INDEX, key=WEEKDAY_INDEX.get)[index] for index in self.weekdays)
        window_label = ""
        if self.active_window is not None:
            window_label = (
                f" {self.active_window.start.strftime('%H:%M')}"
                f"-{self.active_window.end.strftime('%H:%M')}"
            )
        if self.schedule_type == "interval":
            cadence_label = f"every {self.interval_minutes} minute(s)"
        else:
            cadence_label = "at " + ", ".join(value.strftime("%H:%M") for value in self.times)
        return f"{self.name}: {self.command} {cadence_label}{window_label} [{weekday_labels}]"


@dataclass(frozen=True)
class BackendSchedulerConfig:
    timezone: str
    poll_interval_seconds: int
    jobs: tuple[ScheduledJobConfig, ...]

    @classmethod
    def load(cls, path: Path) -> "BackendSchedulerConfig":
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        scheduler_payload = payload.get("scheduler", {})
        if not isinstance(scheduler_payload, dict):
            raise ValueError("Missing [scheduler] section in scheduler config.")
        raw_jobs = payload.get("jobs", [])
        if not isinstance(raw_jobs, list) or not raw_jobs:
            raise ValueError("Scheduler config must define at least one [[jobs]] entry.")
        timezone_name = str(scheduler_payload.get("timezone", "America/New_York")).strip() or "America/New_York"
        poll_interval_seconds = int(scheduler_payload.get("poll_interval_seconds", 30))
        jobs = tuple(_build_scheduled_job(item) for item in raw_jobs)
        return cls(
            timezone=timezone_name,
            poll_interval_seconds=poll_interval_seconds,
            jobs=jobs,
        )


def _build_focus_windows(raw_job: dict[str, object]) -> tuple[FocusWindow, ...]:
    raw_dates = raw_job.get("focus_dates", [])
    if raw_dates in (None, ""):
        return ()
    if not isinstance(raw_dates, list):
        raise ValueError("focus_dates must be a list of MM-DD strings.")
    days_before = int(raw_job.get("focus_days_before", 0))
    days_after = int(raw_job.get("focus_days_after", 0))
    return tuple(
        FocusWindow(
            month_day=str(raw_value).strip(),
            days_before=days_before,
            days_after=days_after,
        )
        for raw_value in raw_dates
    )


def _build_scheduled_job(raw_job: dict[str, object]) -> ScheduledJobConfig:
    name = str(raw_job.get("name", "")).strip()
    command = str(raw_job.get("command", "")).strip()
    schedule_type = str(raw_job.get("schedule_type", "")).strip().lower()
    if not name:
        raise ValueError("Each scheduled job must define a non-empty name.")
    if command not in SUPPORTED_COMMANDS:
        raise ValueError(f"Unsupported scheduled command {command!r}.")
    if schedule_type not in {"interval", "clock"}:
        raise ValueError(f"Unsupported schedule_type={schedule_type!r}; expected 'interval' or 'clock'.")
    raw_weekdays = raw_job.get("weekdays", ["mon", "tue", "wed", "thu", "fri"])
    if not isinstance(raw_weekdays, list):
        raise ValueError("weekdays must be a list like ['mon', 'tue'].")
    weekdays = _normalize_weekdays(raw_weekdays)
    active_window: ActiveWindow | None = None
    if "active_start" in raw_job or "active_end" in raw_job:
        active_start = _parse_clock_time(str(raw_job.get("active_start", "00:00")))
        active_end = _parse_clock_time(str(raw_job.get("active_end", "23:59")))
        active_window = ActiveWindow(start=active_start, end=active_end)
    interval_minutes: int | None = None
    times: tuple[clock_time, ...] = ()
    if schedule_type == "interval":
        interval_minutes = int(raw_job.get("interval_minutes", 0))
        if interval_minutes <= 0:
            raise ValueError("interval schedule_type requires interval_minutes > 0.")
    else:
        raw_times = raw_job.get("times", [])
        if not isinstance(raw_times, list) or not raw_times:
            raise ValueError("clock schedule_type requires a non-empty times list.")
        times = tuple(_parse_clock_time(str(raw_time)) for raw_time in raw_times)
    request_payload = raw_job.get("request", {})
    if not isinstance(request_payload, dict):
        raise ValueError("request must be a table/dict under each [[jobs]] entry.")
    return ScheduledJobConfig(
        name=name,
        command=command,
        schedule_type=schedule_type,
        weekdays=weekdays,
        active_window=active_window,
        interval_minutes=interval_minutes,
        times=times,
        focus_windows=_build_focus_windows(raw_job),
        request=dict(request_payload),
    )


class BackendScheduleService:
    """Run configured backend sync jobs on a schedule-driven loop."""

    def __init__(
        self,
        config: BackendSchedulerConfig,
        orchestrator: BackendOrchestrator,
        dry_run: bool = False,
        log_level: str = "INFO",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._orchestrator = orchestrator
        self._dry_run = dry_run
        self._log_level = log_level
        self._timezone = ZoneInfo(config.timezone)
        self._now_provider = now_provider or (lambda: datetime.now(self._timezone))
        self._last_run_markers: dict[str, str] = {}

    def register(self) -> None:
        schedule.clear("backend-scheduler")
        schedule.every().minute.do(self.run_due_jobs).tag("backend-scheduler")

    def run_due_jobs(self, now: datetime | None = None) -> None:
        current_time = self._normalize_now(now or self._now_provider())
        for job in self._config.jobs:
            if not self._should_run(job, current_time):
                continue
            marker = f"{current_time:%Y-%m-%dT%H:%M}"
            if self._last_run_markers.get(job.name) == marker:
                continue
            self._last_run_markers[job.name] = marker
            self._execute_job(job, current_time)

    def serve_forever(self) -> None:
        self.register()
        LOGGER.info(
            "backend_scheduler_started",
            extra={
                "timezone": self._config.timezone,
                "poll_interval_seconds": self._config.poll_interval_seconds,
                "job_count": len(self._config.jobs),
            },
        )
        try:
            while True:
                schedule.run_pending()
                time.sleep(self._config.poll_interval_seconds)
        except KeyboardInterrupt:
            LOGGER.info("backend_scheduler_stopped")

    def describe_jobs(self) -> list[str]:
        return [job.describe() for job in self._config.jobs]

    def _normalize_now(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self._timezone)
        return value.astimezone(self._timezone)

    def _should_run(self, job: ScheduledJobConfig, current_time: datetime) -> bool:
        if current_time.weekday() not in job.weekdays:
            return False
        if job.focus_windows and not any(window.contains(current_time.date()) for window in job.focus_windows):
            return False
        current_clock = current_time.timetz().replace(tzinfo=None)
        if job.active_window is not None and not job.active_window.contains(current_clock):
            return False
        if job.schedule_type == "interval":
            assert job.interval_minutes is not None
            anchor_minutes = 0
            if job.active_window is not None:
                anchor_minutes = job.active_window.anchor_minutes()
            current_minutes = current_time.hour * 60 + current_time.minute
            if current_minutes < anchor_minutes:
                return False
            return (current_minutes - anchor_minutes) % job.interval_minutes == 0
        return any(
            current_clock.hour == scheduled_time.hour and current_clock.minute == scheduled_time.minute
            for scheduled_time in job.times
        )

    def _execute_job(self, job: ScheduledJobConfig, current_time: datetime) -> None:
        result = self._run_backend_command(job)
        payload = {
            "scheduled_job": job.name,
            "backend_command": job.command,
            "scheduled_time_et": current_time.isoformat(),
            "status": result.status,
            "rows_written": result.rows_written,
            "warnings": result.warnings,
            "error_summary": result.error_summary,
        }
        if result.status == "success":
            LOGGER.info("scheduled_backend_job_completed", extra=payload)
            return
        LOGGER.error("scheduled_backend_job_failed", extra=payload)

    def _run_backend_command(self, job: ScheduledJobConfig):
        request = self._build_request(job.command, job.request)
        if job.command == "sync-13f":
            return self._orchestrator.sync_13f(request)
        if job.command == "sync-8k":
            return self._orchestrator.sync_8k(request)
        if job.command == "sync-13dg":
            return self._orchestrator.sync_13dg(request)
        if job.command == "audit-13dg-coverage":
            return self._orchestrator.audit_13dg_coverage(request)
        if job.command == "rebuild-marts":
            return self._orchestrator.rebuild_marts(request)
        return self._orchestrator.sync_all(request)

    def _build_request(self, command: str, request_payload: dict[str, object]):
        if command == "sync-13f":
            return Sync13FRequest(
                dry_run=self._dry_run,
                log_level=self._log_level,
                job_id=str(request_payload.get("job_id", "")).strip() or None,
                mode=str(request_payload.get("mode", "incremental")),
                quarters=int(request_payload.get("quarters", 4)),
                latest_report_date=_optional_string(request_payload.get("latest_report_date")),
                top_limit=int(request_payload.get("top_limit", 100)),
                skip_download=bool(request_payload.get("skip_download", False)),
                enrich_openfigi=bool(request_payload.get("enrich_openfigi", False)),
                openfigi_batch_size=int(request_payload.get("openfigi_batch_size", 10)),
                openfigi_sleep_seconds=float(request_payload.get("openfigi_sleep_seconds", 1.0)),
            )
        if command == "sync-8k":
            return Sync8KRequest(
                dry_run=self._dry_run,
                log_level=self._log_level,
                job_id=str(request_payload.get("job_id", "")).strip() or None,
                days_back=int(request_payload.get("days_back", 7)),
                date_from=_optional_string(request_payload.get("date_from")),
                tickers=_normalize_tickers(request_payload.get("tickers")),
                universe_source=str(request_payload.get("universe_source", "movers")),
                max_filings=int(request_payload.get("max_filings", 100)),
            )
        if command == "sync-13dg":
            return Sync13DGRequest(
                dry_run=self._dry_run,
                log_level=self._log_level,
                job_id=str(request_payload.get("job_id", "")).strip() or None,
                mode=str(request_payload.get("mode", "issuer")),
                days_back=int(request_payload.get("days_back", 30)),
                date_from=_optional_string(request_payload.get("date_from")),
                tickers=_normalize_tickers(request_payload.get("tickers")),
                manager_ciks=_normalize_tickers(request_payload.get("manager_ciks")),
                manager_scope=str(request_payload.get("manager_scope", "watchlist")),
                universe_source=str(request_payload.get("universe_source", "dim")),
                max_filings=int(request_payload.get("max_filings", 100)),
                form_scope=str(request_payload.get("form_scope", "all")),
            )
        if command == "audit-13dg-coverage":
            return Audit13DGCoverageRequest(
                dry_run=self._dry_run,
                log_level=self._log_level,
                job_id=str(request_payload.get("job_id", "")).strip() or None,
                days_back=int(request_payload.get("days_back", 180)),
                date_from=_optional_string(request_payload.get("date_from")),
                manager_ciks=_normalize_tickers(request_payload.get("manager_ciks")),
                manager_scope=str(request_payload.get("manager_scope", "watchlist")),
                max_filings=int(request_payload.get("max_filings", 100)),
                form_scope=str(request_payload.get("form_scope", "all")),
            )
        if command == "rebuild-marts":
            return RebuildMartsRequest(
                dry_run=self._dry_run,
                log_level=self._log_level,
                job_id=str(request_payload.get("job_id", "")).strip() or None,
                rebuild=str(request_payload.get("rebuild", "all")),
                export_legacy_csv=bool(request_payload.get("export_legacy_csv", False)),
                export_legacy_reports=bool(request_payload.get("export_legacy_reports", False)),
                top_limit_max=int(request_payload.get("top_limit_max", 100)),
            )
        return SyncAllRequest(
            dry_run=self._dry_run,
            log_level=self._log_level,
            job_id=str(request_payload.get("job_id", "")).strip() or None,
            with_marts=bool(request_payload.get("with_marts", False)),
            fail_fast=bool(request_payload.get("fail_fast", False)),
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
