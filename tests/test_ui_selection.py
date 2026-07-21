from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.ui.selection import resolve_multi_selection


def test_multi_selection_defaults_to_every_available_key() -> None:
    assert resolve_multi_selection(["101", "202", "303"], []) == ["101", "202", "303"]


def test_multi_selection_keeps_selected_subset() -> None:
    assert resolve_multi_selection(["101", "202", "303"], ["202"]) == ["202"]


def test_multi_selection_allows_explicit_empty_selection() -> None:
    assert resolve_multi_selection(["101", "202", "303"], [], allow_empty=True) == []


def test_multi_selection_drops_keys_outside_current_filter() -> None:
    assert resolve_multi_selection(["101", "202"], ["202", "303"]) == ["202"]
