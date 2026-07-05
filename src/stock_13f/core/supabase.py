"""Supabase REST helpers."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import json
import time

import requests

from stock_13f.core.settings import Settings


class SupabaseError(RuntimeError):
    """Raised when a Supabase request fails."""


class SupabaseTableMissingError(SupabaseError):
    """Raised when an expected Supabase table does not exist."""


@dataclass(frozen=True)
class SupabaseRuntimeConfig:
    url: str
    secret_key: str
    publishable_key: str


def build_supabase_config(settings: Settings) -> SupabaseRuntimeConfig:
    return SupabaseRuntimeConfig(
        url=settings.supabase_url,
        secret_key=settings.supabase_secret_key,
        publishable_key=settings.supabase_publishable_key,
    )


def _normalize_rest_base_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise SupabaseError("SUPABASE_URL is invalid.")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.path.rstrip("/") == "/rest/v1":
        return f"{origin}/rest/v1"
    if not parsed.path or parsed.path == "/":
        return f"{origin}/rest/v1"
    return f"{origin}{parsed.path.rstrip('/')}"


class SupabaseRestClient:
    """Minimal PostgREST client for the configured Supabase project."""

    def __init__(self, config: SupabaseRuntimeConfig, timeout_seconds: int = 30) -> None:
        self._config = config
        self._base_url = _normalize_rest_base_url(config.url)
        self._timeout_seconds = timeout_seconds
        self._max_retries = 3
        self._retry_delay_seconds = 1.0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "apikey": config.secret_key,
                "Authorization": f"Bearer {config.secret_key}",
                "Content-Type": "application/json",
            }
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def _request(self, method: str, url: str, failure_context: str, **kwargs) -> requests.Response:
        session_method = getattr(self._session, method)
        max_retries = max(int(getattr(self, "_max_retries", 3)), 1)
        retry_delay_seconds = float(getattr(self, "_retry_delay_seconds", 1.0))
        last_error: requests.RequestException | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return session_method(url, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                if attempt == max_retries:
                    break
                time.sleep(retry_delay_seconds * attempt)
        raise SupabaseError(f"Failed to {failure_context} after {max_retries} attempt(s): {last_error}") from last_error

    def table_exists(self, table_name: str) -> bool:
        response = self._request(
            "get",
            f"{self._base_url}/{table_name}",
            failure_context=f"inspect Supabase table {table_name!r}",
            params={"select": "*", "limit": "1"},
            timeout=self._timeout_seconds,
        )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {}
            message = str(payload.get("message", ""))
            if "schema cache" in message or "Could not find the table" in message:
                return False
        raise SupabaseError(
            f"Failed to inspect Supabase table {table_name!r}: {response.status_code} {response.text[:200]}"
        )

    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict[str, object]],
        on_conflict: str,
    ) -> int:
        if not rows:
            return 0
        response = self._request(
            "post",
            f"{self._base_url}/{table_name}",
            failure_context=f"upsert rows into {table_name!r}",
            params={"on_conflict": on_conflict},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            data=json.dumps(rows, ensure_ascii=False),
            timeout=self._timeout_seconds,
        )
        if response.status_code in {200, 201, 204}:
            return len(rows)
        if response.status_code == 404:
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {}
            message = str(payload.get("message", ""))
            if "schema cache" in message or "Could not find the table" in message:
                raise SupabaseTableMissingError(
                    f"Supabase table {table_name!r} does not exist. Apply the SQL schema before syncing."
                ) from None
        raise SupabaseError(
            f"Failed to upsert {len(rows)} row(s) into {table_name!r}: {response.status_code} {response.text[:400]}"
        )

    def fetch_rows(
        self,
        table_name: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, str] | None = None,
        order: str | None = None,
    ) -> list[dict[str, object]]:
        params: dict[str, str] = {"select": "*", "limit": str(limit), "offset": str(offset)}
        if filters is not None:
            params.update(filters)
        if order is not None:
            params["order"] = order
        response = self._request(
            "get",
            f"{self._base_url}/{table_name}",
            failure_context=f"fetch rows from {table_name!r}",
            params=params,
            timeout=self._timeout_seconds,
        )
        if response.status_code != 200:
            raise SupabaseError(
                f"Failed to fetch rows from {table_name!r}: {response.status_code} {response.text[:200]}"
            )
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseError(f"Unexpected response payload for table {table_name!r}.")
        return payload

    def delete_rows(
        self,
        table_name: str,
        filters: dict[str, str],
    ) -> None:
        response = self._request(
            "delete",
            f"{self._base_url}/{table_name}",
            failure_context=f"delete rows from {table_name!r}",
            params=filters,
            headers={"Prefer": "return=minimal"},
            timeout=self._timeout_seconds,
        )
        if response.status_code in {200, 204}:
            return
        raise SupabaseError(
            f"Failed to delete rows from {table_name!r}: {response.status_code} {response.text[:200]}"
        )


def build_supabase_client(settings: Settings) -> SupabaseRestClient | None:
    if not settings.supabase_url or not settings.supabase_secret_key:
        return None
    return SupabaseRestClient(build_supabase_config(settings))
