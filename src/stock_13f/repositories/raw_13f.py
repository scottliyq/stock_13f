"""Raw 13F repository helpers."""

from datetime import datetime, timezone
from pathlib import Path
import json

from stock_13f.core.supabase import SupabaseRestClient


class Raw13FRepository:
    """Persist a lightweight 13F sync manifest locally and optionally to Supabase."""

    def __init__(
        self,
        path: Path,
        supabase_client: SupabaseRestClient | None = None,
        table_name: str = "raw_13f_sync_runs",
    ) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._supabase_client = supabase_client
        self._table_name = table_name

    def write_manifest(self, payload: dict[str, object]) -> None:
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._supabase_client is None:
            return
        latest_report_date = str(payload.get("latest_report_date", ""))
        quarters = int(payload.get("quarters", 0) or 0)
        top_limit = int(payload.get("top_limit", 0) or 0)
        row = {
            "run_key": f"{latest_report_date}|{quarters}|{top_limit}",
            "latest_report_date": latest_report_date or None,
            "quarters": quarters,
            "top_limit": top_limit,
            "output_paths": payload.get("output_paths", []),
            "payload": payload,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        self._supabase_client.upsert_rows(self._table_name, [row], on_conflict="run_key")
