"""Watchlist repository backed by the in-code manager registry."""

from stock_13f.domain.manager_registry import ManagerRegistryEntry, list_default_managers


class WatchlistRepository:
    """Expose the default manager watchlist."""

    def list_entries(self) -> list[ManagerRegistryEntry]:
        return list_default_managers()
