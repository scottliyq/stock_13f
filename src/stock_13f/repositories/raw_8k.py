"""Raw 8-K repository helpers."""

from datetime import datetime, timezone
from pathlib import Path
import json

from stock_13f.core.supabase import SupabaseRestClient


class Raw8KRepository:
    """Persist normalized 8-K payloads locally and optionally to Supabase."""

    def __init__(
        self,
        directory: Path,
        supabase_client: SupabaseRestClient | None = None,
        table_name: str = "raw_8k_filings",
    ) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._supabase_client = supabase_client
        self._table_name = table_name

    def record_path(self, accession_number: str) -> Path:
        return self._directory / f"{accession_number}.json"

    def load_record(self, accession_number: str) -> dict[str, object] | None:
        path = self.record_path(accession_number)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def upsert_record(self, accession_number: str, payload: dict[str, object]) -> None:
        path = self.record_path(accession_number)
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
