#!/usr/bin/env python3
"""Unified backend sync entrypoint for stock_13f."""

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.logging import configure_logging
from stock_13f.core.settings import Settings
from stock_13f.domain.sync_requests import Audit13DGCoverageRequest
from stock_13f.domain.sync_requests import BackfillTickersRequest
from stock_13f.domain.sync_requests import RebuildMartsRequest
from stock_13f.domain.sync_requests import Sync13DGRequest
from stock_13f.domain.sync_requests import Sync13FRequest
from stock_13f.domain.sync_requests import Sync8KRequest
from stock_13f.domain.sync_requests import SyncAllRequest
from stock_13f.services.backend_orchestrator import BackendOrchestrator


def _split_tickers(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return ()
    return tuple(part.strip().upper() for part in raw_value.split(",") if part.strip())


def _split_identifiers(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return ()
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--job-id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified backend sync entrypoint for stock_13f.")
    _add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_13f = subparsers.add_parser("sync-13f", help="Sync quarterly structured 13F data.")
    _add_common_args(sync_13f)
    sync_13f.add_argument("--mode", default="incremental")
    sync_13f.add_argument("--quarters", type=int, default=4)
    sync_13f.add_argument("--latest-report-date")
    sync_13f.add_argument("--top-limit", type=int, default=100)
    sync_13f.add_argument("--skip-download", action="store_true")
    sync_13f.add_argument("--enrich-openfigi", action="store_true")
    sync_13f.add_argument("--openfigi-batch-size", type=int, default=10)
    sync_13f.add_argument("--openfigi-sleep-seconds", type=float, default=1.0)

    sync_8k = subparsers.add_parser("sync-8k", help="Sync 8-K filings with edgartools.")
    _add_common_args(sync_8k)
    sync_8k.add_argument("--days-back", type=int, default=7)
    sync_8k.add_argument("--date-from")
    sync_8k.add_argument("--tickers")
    sync_8k.add_argument("--universe-source", default="movers")
    sync_8k.add_argument("--max-filings", type=int, default=100)

    sync_13dg = subparsers.add_parser("sync-13dg", help="Sync 13D/G filings with edgartools.")
    _add_common_args(sync_13dg)
    sync_13dg.add_argument("--mode", default="issuer")
    sync_13dg.add_argument("--days-back", type=int, default=30)
    sync_13dg.add_argument("--date-from")
    sync_13dg.add_argument("--tickers")
    sync_13dg.add_argument("--manager-ciks")
    sync_13dg.add_argument("--manager-scope", default="watchlist")
    sync_13dg.add_argument("--universe-source", default="dim")
    sync_13dg.add_argument("--max-filings", type=int, default=100)
    sync_13dg.add_argument("--form-scope", default="all")

    audit_13dg = subparsers.add_parser("audit-13dg-coverage", help="Audit 13D/G coverage for tracked managers.")
    _add_common_args(audit_13dg)
    audit_13dg.add_argument("--days-back", type=int, default=180)
    audit_13dg.add_argument("--date-from")
    audit_13dg.add_argument("--manager-ciks")
    audit_13dg.add_argument("--manager-scope", default="watchlist")
    audit_13dg.add_argument("--max-filings", type=int, default=100)
    audit_13dg.add_argument("--form-scope", default="all")

    rebuild = subparsers.add_parser("rebuild-marts", help="Rebuild local mart snapshots.")
    _add_common_args(rebuild)
    rebuild.add_argument("--rebuild", default="all")
    rebuild.add_argument("--export-legacy-csv", action="store_true")
    rebuild.add_argument("--export-legacy-reports", action="store_true")
    rebuild.add_argument("--top-limit-max", type=int, default=100)

    backfill_tickers = subparsers.add_parser("backfill-tickers", help="Backfill missing ticker fields in Supabase marts.")
    _add_common_args(backfill_tickers)
    backfill_tickers.add_argument("--with-openfigi", action="store_true")
    backfill_tickers.add_argument("--openfigi-batch-size", type=int, default=10)
    backfill_tickers.add_argument("--openfigi-sleep-seconds", type=float, default=3.0)
    backfill_tickers.add_argument("--openfigi-max-batches", type=int, default=0)

    sync_all = subparsers.add_parser("sync-all", help="Run every sync command in sequence.")
    _add_common_args(sync_all)
    sync_all.add_argument("--with-marts", action="store_true")
    sync_all.add_argument("--fail-fast", action="store_true")

    subparsers.add_parser("show-status", help="Show the latest checkpoint status for every backend job.")
    return parser


def _print_result(result) -> None:
    payload = {
        "job_name": result.job_name,
        "status": result.status,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "rows_written": result.rows_written,
        "checkpoints_updated": result.checkpoints_updated,
        "warnings": result.warnings,
        "error_summary": result.error_summary,
        "details": result.details,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    settings = Settings.load()
    orchestrator = BackendOrchestrator(settings)

    if args.command == "sync-13f":
        result = orchestrator.sync_13f(
            Sync13FRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                mode=args.mode,
                quarters=args.quarters,
                latest_report_date=args.latest_report_date,
                top_limit=args.top_limit,
                skip_download=args.skip_download,
                enrich_openfigi=args.enrich_openfigi,
                openfigi_batch_size=args.openfigi_batch_size,
                openfigi_sleep_seconds=args.openfigi_sleep_seconds,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "sync-8k":
        result = orchestrator.sync_8k(
            Sync8KRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                days_back=args.days_back,
                date_from=args.date_from,
                tickers=_split_tickers(args.tickers),
                universe_source=args.universe_source,
                max_filings=args.max_filings,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "sync-13dg":
        result = orchestrator.sync_13dg(
            Sync13DGRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                mode=args.mode,
                days_back=args.days_back,
                date_from=args.date_from,
                tickers=_split_tickers(args.tickers),
                manager_ciks=_split_identifiers(args.manager_ciks),
                manager_scope=args.manager_scope,
                universe_source=args.universe_source,
                max_filings=args.max_filings,
                form_scope=args.form_scope,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "audit-13dg-coverage":
        result = orchestrator.audit_13dg_coverage(
            Audit13DGCoverageRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                days_back=args.days_back,
                date_from=args.date_from,
                manager_ciks=_split_identifiers(args.manager_ciks),
                manager_scope=args.manager_scope,
                max_filings=args.max_filings,
                form_scope=args.form_scope,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "rebuild-marts":
        result = orchestrator.rebuild_marts(
            RebuildMartsRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                rebuild=args.rebuild,
                export_legacy_csv=args.export_legacy_csv,
                export_legacy_reports=args.export_legacy_reports,
                top_limit_max=args.top_limit_max,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "backfill-tickers":
        result = orchestrator.backfill_tickers(
            BackfillTickersRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                with_openfigi=args.with_openfigi,
                openfigi_batch_size=args.openfigi_batch_size,
                openfigi_sleep_seconds=args.openfigi_sleep_seconds,
                openfigi_max_batches=args.openfigi_max_batches,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    if args.command == "sync-all":
        result = orchestrator.sync_all(
            SyncAllRequest(
                dry_run=args.dry_run,
                log_level=args.log_level,
                job_id=args.job_id,
                with_marts=args.with_marts,
                fail_fast=args.fail_fast,
            )
        )
        _print_result(result)
        return 0 if result.status == "success" else 1

    statuses = orchestrator.show_status()
    print(json.dumps(statuses, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
