from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.domain.manager_registry import list_default_managers


def test_default_manager_watchlist_contains_expected_entries() -> None:
    managers = list_default_managers()
    assert len(managers) == 11
    assert managers[0].manager_name == "Pershing Square Capital Management, L.P."
    assert managers[0].manager_cik == 1336528
    assert managers[-1].manager_name == "Eclipse Operations, LLC"
