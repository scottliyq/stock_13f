#!/usr/bin/env python3
"""Unified scheduler entrypoint for stock_13f backend sync jobs."""

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.logging import configure_logging
from stock_13f.core.settings import Settings
from stock_13f.services.backend_orchestrator import BackendOrchestrator
from stock_13f.services.backend_schedule_service import BackendScheduleService
from stock_13f.services.backend_schedule_service import BackendSchedulerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified scheduler entrypoint for stock_13f backend sync jobs.")
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "config" / "backend_schedule.toml"),
        help="Path to the scheduler TOML config file.",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-jobs", action="store_true")
    parser.add_argument(
        "--run-due-now",
        action="store_true",
        help="Evaluate the current ET minute once and exit instead of starting the long-running loop.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    config = BackendSchedulerConfig.load(Path(args.config))
    service = BackendScheduleService(
        config=config,
        orchestrator=BackendOrchestrator(Settings.load()),
        dry_run=args.dry_run,
        log_level=args.log_level,
    )
    if args.list_jobs:
        for line in service.describe_jobs():
            print(line)
        return 0
    if args.run_due_now:
        service.run_due_jobs()
        return 0
    service.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
