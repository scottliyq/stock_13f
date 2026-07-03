from dataclasses import dataclass
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.supabase import _normalize_rest_base_url
from stock_13f.core.supabase import SupabaseRestClient
from stock_13f.core.supabase import SupabaseTableMissingError


@dataclass
class FakeResponse:
    status_code: int
    text: str
    payload: dict[str, object]

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.headers: dict[str, str] = {}

    def get(self, *args, **kwargs) -> FakeResponse:
        return self._response

    def post(self, *args, **kwargs) -> FakeResponse:
        return self._response

    def delete(self, *args, **kwargs) -> FakeResponse:
        return self._response


def test_normalize_rest_base_url_accepts_project_root() -> None:
    assert _normalize_rest_base_url("https://example.supabase.co") == "https://example.supabase.co/rest/v1"


def test_normalize_rest_base_url_accepts_rest_endpoint() -> None:
    assert _normalize_rest_base_url("https://example.supabase.co/rest/v1/") == "https://example.supabase.co/rest/v1"


def test_table_exists_returns_false_for_missing_table() -> None:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://example.supabase.co/rest/v1"
    client._timeout_seconds = 30
    client._session = FakeSession(
        FakeResponse(
            status_code=404,
            text='{"message":"Could not find the table in the schema cache"}',
            payload={"message": "Could not find the table 'public.foo' in the schema cache"},
        )
    )

    assert client.table_exists("foo") is False


def test_upsert_rows_raises_for_missing_table() -> None:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://example.supabase.co/rest/v1"
    client._timeout_seconds = 30
    client._session = FakeSession(
        FakeResponse(
            status_code=404,
            text='{"message":"Could not find the table in the schema cache"}',
            payload={"message": "Could not find the table 'public.foo' in the schema cache"},
        )
    )

    try:
        client.upsert_rows("foo", [{"id": 1}], on_conflict="id")
    except SupabaseTableMissingError as exc:
        assert "foo" in str(exc)
    else:
        raise AssertionError("expected SupabaseTableMissingError")


def test_fetch_rows_supports_filters_order_and_offset() -> None:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://example.supabase.co/rest/v1"
    client._timeout_seconds = 30
    response = FakeResponse(status_code=200, text="[]", payload=[{"ticker": "AAPL"}])
    session = FakeSession(response)
    client._session = session

    rows = client.fetch_rows(
        "foo",
        limit=50,
        offset=100,
        filters={"security_type": "eq.stock"},
        order="report_date.desc",
    )

    assert rows == [{"ticker": "AAPL"}]


def test_delete_rows_succeeds_on_204() -> None:
    client = SupabaseRestClient.__new__(SupabaseRestClient)
    client._base_url = "https://example.supabase.co/rest/v1"
    client._timeout_seconds = 30
    client._session = FakeSession(FakeResponse(status_code=204, text="", payload={}))

    client.delete_rows("foo", {"report_date": "eq.2026-03-31"})
