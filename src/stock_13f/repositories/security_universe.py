"""Security universe helpers derived from Supabase 13F movers data."""

from stock_13f.core.supabase import SupabaseRestClient


class SecurityUniverseRepository:
    """Resolve stock universes for downstream 8-K and 13D/G sync jobs."""

    def __init__(
        self,
        supabase_client: SupabaseRestClient | None,
        table_name: str = "mart_13f_quarterly_movers",
    ) -> None:
        self._supabase_client = supabase_client
        self._table_name = table_name

    def latest_movers_stock_tickers(self) -> tuple[str, ...]:
        if self._supabase_client is None:
            return ()
        latest_rows = self._supabase_client.fetch_rows(
            self._table_name,
            limit=1,
            filters={"security_type": "eq.stock"},
            order="report_date.desc",
        )
        if not latest_rows:
            return ()
        latest_report_date = str(latest_rows[0].get("report_date", "")).strip()
        if not latest_report_date:
            return ()
        rows = self._fetch_all_rows(
            filters={
                "security_type": "eq.stock",
                "report_date": f"eq.{latest_report_date}",
            }
        )
        return self._extract_unique_tickers(rows)

    def all_stock_tickers(self) -> tuple[str, ...]:
        if self._supabase_client is None:
            return ()
        return self._extract_unique_tickers(self._fetch_all_rows(filters={"security_type": "eq.stock"}))

    def resolve(self, universe_source: str) -> tuple[str, ...]:
        normalized = universe_source.strip().lower()
        if normalized == "movers":
            return self.latest_movers_stock_tickers()
        if normalized == "dim":
            return self.all_stock_tickers()
        return ()

    def _fetch_all_rows(self, filters: dict[str, str]) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        page_size = 1000
        offset = 0
        rows: list[dict[str, object]] = []
        while True:
            page = self._supabase_client.fetch_rows(
                self._table_name,
                limit=page_size,
                offset=offset,
                filters=filters,
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def _extract_unique_tickers(self, rows: list[dict[str, object]]) -> tuple[str, ...]:
        seen: set[str] = set()
        for row in rows:
            ticker = str(row.get("ticker", "") or "").strip().upper()
            if ticker:
                seen.add(ticker)
        return tuple(sorted(seen))
