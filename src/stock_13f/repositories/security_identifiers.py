"""Security identifier helpers for issuer CUSIP and ticker normalization."""

from collections.abc import Iterable
from csv import DictReader
import json
from pathlib import Path
import re


ISSUER_TOKEN_ALIASES = {
    "INTL": "INTERNATIONAL",
    "INTL.": "INTERNATIONAL",
    "HLDG": "HOLDING",
    "HLDGS": "HOLDING",
    "HLDNGS": "HOLDING",
    "HOLDINGS": "HOLDING",
    "ENTMT": "ENTERTAINMENT",
    "FINL": "FINANCIAL",
    "PWR": "POWER",
    "SYS": "SYSTEMS",
    "SVCS": "SERVICES",
    "SVC": "SERVICES",
    "SPONSORD": "SPONSORED",
    "SPON": "SPONSORED",
    "AIRLS": "AIRLINES",
    "TR": "TRUST",
    "PL": "PLC",
    "GRDN": "GARDEN",
    "MFG": "MANUFACTURING",
    "RUBR": "RUBBER",
    "HLTH": "HEALTH",
    "FRAGRA": "FRAGRANCES",
    "AMER": "AMERICA",
    "REP": "REPRESENTING",
    "VTG": "VOTING",
    "SUB": "SUBORDINATE",
    "LT": "LTD",
    "TECHNOLOG": "TECHNOLOGY",
    "TECHNOLOGIES": "TECHNOLOGY",
    "LIMI": "LIMITED",
    "TECH": "TECHNOLOGY",
    "CORP": "CORPORATION",
    "CORP.": "CORPORATION",
    "CO": "COMPANY",
    "COS": "COMPANIES",
    "CTZNS": "CITIZENS",
    "PPTYS": "PROPERTIES",
    "INDS": "INDUSTRIES",
}
ISSUER_STOP_TOKENS = {
    "ADR",
    "ADS",
    "CLASS",
    "CL",
    "COM",
    "COMMON",
    "DELAWARE",
    "DEL",
    "CAYMAN",
    "ISLANDS",
    "ISRAEL",
    "ORD",
    "ORDINARY",
    "PUT",
    "PFD",
    "PLC",
    "PREFERRED",
    "REPRESENTING",
    "SER",
    "SERIES",
    "SHS",
    "SHR",
    "SHARES",
    "SPONSORED",
    "STOCK",
    "SUBORDINATE",
    "THE",
    "NEW",
    "UNIT",
    "USD",
    "VOTING",
    "LTD",
    "LIMITED",
    "AG",
    "AKT",
    "NAMEN",
    "NV",
    "BEN",
    "INT",
}


def _normalize_cusip(value: str) -> str:
    return "".join(str(value or "").strip().upper().split())


def normalize_issuer_name(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace("'", "")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[-/,.;:]+", " ", text)
    tokens = [token for token in text.split() if token]
    normalized_tokens: list[str] = []
    for index, token in enumerate(tokens):
        canonical = ISSUER_TOKEN_ALIASES.get(token, token)
        if token == "L" and index == len(tokens) - 1:
            canonical = "LTD"
        if canonical in ISSUER_STOP_TOKENS:
            continue
        normalized_tokens.append(canonical)
    while normalized_tokens and normalized_tokens[-1].isdigit():
        normalized_tokens.pop()
    while len(normalized_tokens) >= 2 and tuple(normalized_tokens[-2:]) in {("N", "V"), ("S", "A")}:
        normalized_tokens.pop()
        normalized_tokens.pop()
    while normalized_tokens and normalized_tokens[-1] in {"A", "B", "C", "L", "N"}:
        normalized_tokens.pop()
    return " ".join(normalized_tokens)


class SecurityIdentifierRepository:
    """Resolve tickers for issuer-centric and manager-centric 13D/G rows."""

    def __init__(
        self,
        map_path: Path,
        company_tickers_path: Path | Iterable[Path] | None = None,
    ) -> None:
        self._map_path = map_path
        self._company_tickers_path = company_tickers_path
        self._cusip_to_ticker: dict[str, str] | None = None
        self._issuer_to_ticker: dict[str, str] | None = None

    def resolve_ticker(
        self,
        issuer_cusip: str,
        fallback_ticker: str = "",
        issuer_name: str = "",
    ) -> str:
        normalized_cusip = _normalize_cusip(issuer_cusip)
        if normalized_cusip:
            ticker = self._load_cusip_map().get(normalized_cusip, "")
            if ticker:
                return ticker
        normalized_issuer = normalize_issuer_name(issuer_name)
        if normalized_issuer:
            ticker = self._load_issuer_map().get(normalized_issuer, "")
            if ticker:
                return ticker
            ticker = self._resolve_by_fuzzy_issuer(normalized_issuer)
            if ticker:
                return ticker
        return str(fallback_ticker or "").strip().upper()

    def _load_cusip_map(self) -> dict[str, str]:
        if self._cusip_to_ticker is not None:
            return self._cusip_to_ticker
        mapping, issuer_mapping = self._load_maps()
        self._cusip_to_ticker = mapping
        self._issuer_to_ticker = issuer_mapping
        return mapping

    def _load_issuer_map(self) -> dict[str, str]:
        if self._issuer_to_ticker is not None:
            return self._issuer_to_ticker
        mapping, issuer_mapping = self._load_maps()
        self._cusip_to_ticker = mapping
        self._issuer_to_ticker = issuer_mapping
        return issuer_mapping

    def _load_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        mapping: dict[str, str] = {}
        issuer_mapping: dict[str, str] = {}
        if not self._map_path.exists():
            return mapping, issuer_mapping
        with self._map_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = DictReader(handle)
            for row in reader:
                cusip = _normalize_cusip(str(row.get("cusip", "") or ""))
                ticker = str(row.get("ticker", "") or "").strip().upper()
                issuer = normalize_issuer_name(str(row.get("issuer", "") or ""))
                if cusip and ticker:
                    mapping[cusip] = ticker
                if issuer and ticker:
                    issuer_mapping[issuer] = ticker
        for cache_path in self._iter_company_ticker_paths():
            if not cache_path.exists():
                continue
            with cache_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for item in self._iter_company_ticker_items(payload):
                issuer = normalize_issuer_name(
                    str(
                        item.get("title", "")
                        or item.get("name", "")
                        or item.get("company_name", "")
                        or ""
                    )
                )
                ticker = str(item.get("ticker", "") or item.get("symbol", "") or "").strip().upper()
                if issuer and ticker:
                    issuer_mapping.setdefault(issuer, ticker)
        return mapping, issuer_mapping

    def _iter_company_ticker_paths(self) -> list[Path]:
        if self._company_tickers_path is None:
            return []
        if isinstance(self._company_tickers_path, Path):
            return [self._company_tickers_path]
        return [path for path in self._company_tickers_path if isinstance(path, Path)]

    def _iter_company_ticker_items(self, payload: object) -> list[dict[str, object]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        data_payload = payload.get("data")
        if isinstance(data_payload, list):
            return [item for item in data_payload if isinstance(item, dict)]
        return [item for item in payload.values() if isinstance(item, dict)]

    def _resolve_by_fuzzy_issuer(self, normalized_issuer: str) -> str:
        candidate_tickers = {
            ticker
            for issuer, ticker in self._load_issuer_map().items()
            if issuer.startswith(f"{normalized_issuer} ") or normalized_issuer.startswith(f"{issuer} ")
        }
        if len(candidate_tickers) == 1:
            return next(iter(candidate_tickers))
        return ""
