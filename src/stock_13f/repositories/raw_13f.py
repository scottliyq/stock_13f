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
        filing_table_name: str = "raw_13f_filings",
    ) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._supabase_client = supabase_client
        self._table_name = table_name
        self._filing_table_name = filing_table_name

    def upsert_filing_rows(
        self,
        rows: list[dict[str, object]],
        batch_size: int = 100,
    ) -> int:
        if self._supabase_client is None:
            return 0
        written = 0
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            written += self._supabase_client.upsert_rows(
                self._filing_table_name,
                batch,
                on_conflict="accession_number",
            )
        return written

    def fetch_filing_rows(
        self,
        report_date: str,
        page_size: int = 1000,
        select: str = "*",
    ) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        rows: list[dict[str, object]] = []
        offset = 0
        while True:
            page = self._supabase_client.fetch_rows(
                self._filing_table_name,
                limit=page_size,
                offset=offset,
                filters={"report_date": f"eq.{report_date}"},
                order="manager_cik.asc,filing_date.desc,accession_number.desc",
                select=select,
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def fetch_filing_accessions(
        self,
        report_date: str,
        page_size: int = 1000,
    ) -> set[str]:
        return {
            str(row.get("accession_number", "") or "").strip()
            for row in self.fetch_filing_rows(
                report_date,
                page_size=page_size,
                select="accession_number",
            )
            if str(row.get("accession_number", "") or "").strip()
        }

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
