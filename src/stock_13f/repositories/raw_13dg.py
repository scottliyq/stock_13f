"""Raw 13D/G repository helpers."""

from datetime import datetime, timezone
from pathlib import Path
import json

from stock_13f.core.supabase import SupabaseRestClient


class Raw13DGRepository:
    """Persist normalized 13D/G payloads locally and optionally to Supabase."""

    def __init__(
        self,
        directory: Path,
        supabase_client: SupabaseRestClient | None = None,
        table_name: str = "raw_13dg_filings",
    ) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._supabase_client = supabase_client
        self._table_name = table_name

    def upsert_record(self, accession_number: str, payload: dict[str, object]) -> None:
        path = self._directory / f"{accession_number}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._supabase_client is None:
            return
        row = {
            "accession_number": accession_number,
            "ticker": payload.get("ticker", ""),
            "form": payload.get("form", ""),
            "filing_date": payload.get("filing_date") or None,
            "company_name": payload.get("company_name", ""),
            "payload": payload,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        self._supabase_client.upsert_rows(self._table_name, [row], on_conflict="accession_number")

    def replace_reporting_person_rows(self, accession_number: str, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        self._supabase_client.delete_rows(
            "raw_13dg_reporting_persons",
            filters={"accession_number": f"eq.{accession_number}"},
        )
        if not rows:
            return 0
        return self._supabase_client.upsert_rows(
            "raw_13dg_reporting_persons",
            rows,
            on_conflict="row_key",
        )

    def upsert_sync_source_row(self, row: dict[str, object]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "raw_13dg_sync_sources",
            [row],
            on_conflict="row_key",
        )
