from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.repositories.security_universe import SecurityUniverseRepository


class FakeSupabaseClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetch_rows(
        self,
        table_name: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        del table_name
        rows = list(self._rows)
        if filters:
            for key, value in filters.items():
                operator, operand = value.split(".", 1)
                if operator == "eq":
                    rows = [row for row in rows if str(row.get(key, "")) == operand]
        if order == "report_date.desc":
            rows.sort(key=lambda row: str(row.get("report_date", "")), reverse=True)
        return rows[offset : offset + limit]


def test_security_universe_reads_latest_and_all_stock_tickers_from_supabase() -> None:
    client = FakeSupabaseClient(
        [
            {"report_date": "2025-12-31", "security_type": "stock", "ticker": "AAPL"},
            {"report_date": "2025-12-31", "security_type": "stock", "ticker": "MSFT"},
            {"report_date": "2026-03-31", "security_type": "stock", "ticker": "NVDA"},
            {"report_date": "2026-03-31", "security_type": "stock", "ticker": "AAPL"},
            {"report_date": "2026-03-31", "security_type": "etf", "ticker": "QQQ"},
        ]
    )

    repository = SecurityUniverseRepository(client)

    assert repository.latest_movers_stock_tickers() == ("AAPL", "NVDA")
    assert repository.all_stock_tickers() == ("AAPL", "MSFT", "NVDA")
    assert repository.resolve("movers") == ("AAPL", "NVDA")
    assert repository.resolve("dim") == ("AAPL", "MSFT", "NVDA")
