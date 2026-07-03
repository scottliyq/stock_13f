#!/usr/bin/env python3
"""Enrich local CUSIP to ticker mappings with OpenFIGI."""

import argparse
import csv
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger("enrich_cusip_ticker_map_openfigi")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP_PATH = REPO_ROOT / "data" / "cusip_ticker_map.csv"
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports" / "13_following" / "data"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
DEFAULT_MAX_RETRIES = 5


@dataclass(frozen=True)
class MissingCusip:
    cusip: str
    issuer: str
    security_type: str


def normalize_cusip(cusip: str) -> str:
    return cusip.strip().upper()


def load_existing_map(map_path: Path) -> dict[str, dict[str, str]]:
    if not map_path.exists():
        return {}
    rows_by_cusip: dict[str, dict[str, str]] = {}
    with map_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        for row in csv.DictReader(input_file):
            cusip = normalize_cusip(row.get("cusip", ""))
            ticker = row.get("ticker", "").strip().upper()
            if not cusip or not ticker:
                continue
            rows_by_cusip[cusip] = {
                "cusip": cusip,
                "ticker": ticker,
                "issuer": row.get("issuer", "").strip(),
            }
    return rows_by_cusip


def collect_missing_cusips(
    reports_dir: Path,
    existing_rows_by_cusip: dict[str, dict[str, str]],
) -> list[MissingCusip]:
    missing_by_cusip: dict[str, MissingCusip] = {}
    for path in sorted(reports_dir.glob("*_13f_quarterly_rebalance_*_top*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as input_file:
            for row in csv.DictReader(input_file):
                cusip = normalize_cusip(row.get("cusip", ""))
                if not cusip or cusip in existing_rows_by_cusip:
                    continue
                if row.get("ticker", "").strip():
                    continue
                missing_by_cusip.setdefault(
                    cusip,
                    MissingCusip(
                        cusip=cusip,
                        issuer=row.get("issuer", "").strip(),
                        security_type=row.get("security_type", "").strip(),
                    ),
                )
    return list(missing_by_cusip.values())


def batched[T](items: list[T], batch_size: int) -> list[list[T]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def query_openfigi_batch(batch: list[MissingCusip]) -> list[dict[str, str]]:
    payload = json.dumps(
        [
            {
                "idType": "ID_CUSIP",
                "idValue": item.cusip,
                "exchCode": "US",
            }
            for item in batch
        ]
    ).encode()
    request = urllib.request.Request(
        OPENFIGI_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw_results = json.loads(response.read().decode())
    mappings: list[dict[str, str]] = []
    for item, result in zip(batch, raw_results, strict=True):
        candidates = result.get("data", [])
        if not candidates:
            continue
        candidate = candidates[0]
        ticker = str(candidate.get("ticker", "")).strip().upper().rstrip("*")
        if not ticker:
            continue
        mappings.append(
            {
                "cusip": item.cusip,
                "ticker": ticker,
                "issuer": candidate.get("name", "").strip() or item.issuer,
            }
        )
    return mappings


def retry_delay_seconds(
    error: urllib.error.HTTPError | urllib.error.URLError | TimeoutError,
    attempt: int,
    base_sleep_seconds: float,
) -> float:
    if isinstance(error, urllib.error.HTTPError):
        retry_after = error.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), base_sleep_seconds)
            except ValueError:
                return max(base_sleep_seconds, float(2**attempt))
    return max(base_sleep_seconds, float(2**attempt))


def query_openfigi_batch_with_retry(
    batch: list[MissingCusip],
    sleep_seconds: float,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> list[dict[str, str]]:
    for attempt in range(max_retries):
        try:
            return query_openfigi_batch(batch)
        except urllib.error.HTTPError as error:
            is_retryable = error.code == 429 or error.code >= 500
            if not is_retryable or attempt == max_retries - 1:
                raise
            delay_seconds = retry_delay_seconds(error, attempt + 1, sleep_seconds)
            LOGGER.warning(
                "openfigi_batch_retrying",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "batch_size": len(batch),
                    "http_code": error.code,
                    "delay_seconds": delay_seconds,
                },
            )
            time.sleep(delay_seconds)
        except urllib.error.URLError as error:
            if attempt == max_retries - 1:
                raise
            delay_seconds = retry_delay_seconds(error, attempt + 1, sleep_seconds)
            LOGGER.warning(
                "openfigi_batch_retrying",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "batch_size": len(batch),
                    "reason": str(error.reason),
                    "delay_seconds": delay_seconds,
                },
            )
            time.sleep(delay_seconds)
        except TimeoutError as error:
            if attempt == max_retries - 1:
                raise
            delay_seconds = retry_delay_seconds(error, attempt + 1, sleep_seconds)
            LOGGER.warning(
                "openfigi_batch_retrying",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "batch_size": len(batch),
                    "reason": str(error),
                    "delay_seconds": delay_seconds,
                },
            )
            time.sleep(delay_seconds)
    return []


def merge_rows(
    existing_rows_by_cusip: dict[str, dict[str, str]],
    new_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    merged_rows = dict(existing_rows_by_cusip)
    for row in new_rows:
        merged_rows[row["cusip"]] = row
    return merged_rows


def write_map(map_path: Path, rows_by_cusip: dict[str, dict[str, str]]) -> None:
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with map_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["cusip", "ticker", "issuer"])
        writer.writeheader()
        for cusip in sorted(rows_by_cusip):
            writer.writerow(rows_by_cusip[cusip])


def enrich_cusip_ticker_map_with_openfigi(
    map_path: Path,
    reports_dir: Path,
    batch_size: int,
    sleep_seconds: float,
) -> int:
    existing_rows_by_cusip = load_existing_map(map_path)
    missing_items = collect_missing_cusips(reports_dir, existing_rows_by_cusip)
    if not missing_items:
        LOGGER.info("no_missing_cusips_found", extra={"reports_dir": str(reports_dir)})
        return 0

    LOGGER.info("openfigi_enrichment_started", extra={"missing_count": len(missing_items)})
    new_rows: list[dict[str, str]] = []
    skipped_batch_count = 0
    for index, batch in enumerate(batched(missing_items, batch_size), start=1):
        try:
            batch_rows = query_openfigi_batch_with_retry(
                batch=batch,
                sleep_seconds=sleep_seconds,
            )
        except urllib.error.HTTPError as error:
            skipped_batch_count += 1
            LOGGER.warning(
                "openfigi_batch_skipped",
                extra={
                    "batch_index": index,
                    "batch_size": len(batch),
                    "http_code": error.code,
                },
            )
            continue
        except urllib.error.URLError as error:
            skipped_batch_count += 1
            LOGGER.warning(
                "openfigi_batch_skipped",
                extra={
                    "batch_index": index,
                    "batch_size": len(batch),
                    "reason": str(error.reason),
                },
            )
            continue
        except TimeoutError:
            skipped_batch_count += 1
            LOGGER.warning(
                "openfigi_batch_skipped",
                extra={
                    "batch_index": index,
                    "batch_size": len(batch),
                    "reason": "timeout",
                },
            )
            continue
        new_rows.extend(batch_rows)
        LOGGER.info(
            "openfigi_batch_completed",
            extra={
                "batch_index": index,
                "batch_size": len(batch),
                "mapped_count": len(batch_rows),
            },
        )
        if index * batch_size < len(missing_items):
            time.sleep(sleep_seconds)

    merged_rows = merge_rows(existing_rows_by_cusip, new_rows)
    write_map(map_path, merged_rows)
    LOGGER.info(
        "openfigi_enrichment_finished",
        extra={
            "map_path": str(map_path),
            "new_rows": len(new_rows),
            "skipped_batches": skipped_batch_count,
            "total_rows": len(merged_rows),
        },
    )
    return len(new_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich local CUSIP to ticker mappings with OpenFIGI.")
    parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    enrich_cusip_ticker_map_with_openfigi(
        map_path=args.map_path,
        reports_dir=args.reports_dir,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
