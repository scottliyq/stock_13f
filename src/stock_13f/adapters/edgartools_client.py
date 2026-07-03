"""Thin wrapper around optional edgartools imports."""

from datetime import date
from datetime import timedelta
from pathlib import Path
import importlib


class EdgarToolsUnavailable(RuntimeError):
    """Raised when edgartools is required but unavailable."""


class EdgarTickerLookupError(RuntimeError):
    """Raised when a ticker cannot be resolved by edgartools."""


class EdgarToolsClient:
    """Lazy wrapper to keep edgartools optional until sync commands are used."""

    def __init__(self) -> None:
        self._edgar_module = None

    def is_available(self) -> bool:
        return importlib.util.find_spec("edgar") is not None

    def require_available(self) -> None:
        if not self.is_available():
            raise EdgarToolsUnavailable(
                "edgartools is not installed in the active environment. Install project dependencies first."
            )

    def _edgar(self):
        self.require_available()
        if self._edgar_module is None:
            self._edgar_module = importlib.import_module("edgar")
        return self._edgar_module

    def build_filing_date_range(self, days_back: int, date_from: str | None) -> str:
        if date_from:
            return f"{date_from}:{date.today().isoformat()}"
        return f"{(date.today() - timedelta(days=days_back)).isoformat()}:{date.today().isoformat()}"

    def search_company_filings(
        self,
        ticker: str,
        forms: tuple[str, ...],
        days_back: int,
        date_from: str | None,
        max_filings: int,
    ) -> list[object]:
        edgar = self._edgar()
        core_module = importlib.import_module("edgar.entity.core")
        company_not_found = getattr(core_module, "CompanyNotFoundError")
        try:
            company = edgar.Company(ticker)
        except company_not_found as exc:
            raise EdgarTickerLookupError(f"Ticker could not be resolved by edgartools: {ticker}") from exc
        filings = company.get_filings(form=list(forms))
        filing_date_range = self.build_filing_date_range(days_back, date_from)
        if hasattr(filings, "filter"):
            filings = filings.filter(filing_date=filing_date_range)
        return list(filings[:max_filings])
