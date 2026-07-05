"""Marts repository helpers."""

from pathlib import Path
import json

from stock_13f.core.supabase import SupabaseRestClient


class MartsRepository:
    """Persist local mart snapshots and optionally mirror them to Supabase."""

    def __init__(
        self,
        directory: Path,
        supabase_client: SupabaseRestClient | None = None,
    ) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._supabase_client = supabase_client

    def write_snapshot(self, name: str, payload: dict[str, object]) -> Path:
        path = self._directory / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def upsert_quarterly_movers(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_13f_quarterly_movers",
            rows,
            on_conflict="row_key",
        )

    def replace_quarterly_movers(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        if self._supabase_client is None:
            return 0
        for report_date in sorted(set(report_dates)):
            self._supabase_client.delete_rows(
                "mart_13f_quarterly_movers",
                filters={"report_date": f"eq.{report_date}"},
            )
        return self.upsert_quarterly_movers(rows)

    def fetch_quarterly_movers(
        self,
        limit: int = 1000,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        return self._supabase_client.fetch_rows(
            "mart_13f_quarterly_movers",
            limit=limit,
            offset=offset,
            filters=filters,
            order=order,
        )

    def upsert_manager_rebalance_summaries(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_manager_rebalance_summary",
            rows,
            on_conflict="row_key",
        )

    def replace_manager_rebalance_summaries(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        if self._supabase_client is None:
            return 0
        for report_date in sorted(set(report_dates)):
            self._supabase_client.delete_rows(
                "mart_manager_rebalance_summary",
                filters={"report_date": f"eq.{report_date}"},
            )
        return self.upsert_manager_rebalance_summaries(rows)

    def fetch_manager_rebalance_summaries(
        self,
        limit: int = 1000,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        return self._supabase_client.fetch_rows(
            "mart_manager_rebalance_summary",
            limit=limit,
            offset=offset,
            filters=filters,
            order=order,
        )

    def upsert_manager_rebalance_details(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_manager_rebalance_detail",
            rows,
            on_conflict="row_key",
        )

    def replace_manager_rebalance_details(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        if self._supabase_client is None:
            return 0
        for report_date in sorted(set(report_dates)):
            self._supabase_client.delete_rows(
                "mart_manager_rebalance_detail",
                filters={"report_date": f"eq.{report_date}"},
            )
        return self.upsert_manager_rebalance_details(rows)

    def fetch_manager_rebalance_details(
        self,
        limit: int = 1000,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        return self._supabase_client.fetch_rows(
            "mart_manager_rebalance_detail",
            limit=limit,
            offset=offset,
            filters=filters,
            order=order,
        )

    def upsert_manager_security_latest_rows(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_manager_security_latest",
            rows,
            on_conflict="row_key",
        )

    def replace_manager_security_latest_rows(
        self,
        report_dates: list[str],
        rows: list[dict[str, object]],
    ) -> int:
        if self._supabase_client is None:
            return 0
        for report_date in sorted(set(report_dates)):
            self._supabase_client.delete_rows(
                "mart_manager_security_latest",
                filters={"report_date": f"eq.{report_date}"},
            )
        return self.upsert_manager_security_latest_rows(rows)

    def fetch_manager_security_latest_rows(
        self,
        limit: int = 1000,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        if self._supabase_client is None:
            return []
        return self._supabase_client.fetch_rows(
            "mart_manager_security_latest",
            limit=limit,
            offset=offset,
            filters=filters,
            order=order,
        )

    def upsert_manager_watchlist(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "dim_manager_watchlist",
            rows,
            on_conflict="manager_cik",
        )

    def upsert_manager_profiles(self, rows: list[dict[str, object]]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_manager_profile",
            rows,
            on_conflict="manager_cik",
        )

    def upsert_research_snapshot(self, row: dict[str, object]) -> int:
        if self._supabase_client is None:
            return 0
        return self._supabase_client.upsert_rows(
            "mart_manager_research_snapshot",
            [row],
            on_conflict="snapshot_key",
        )
