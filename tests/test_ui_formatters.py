from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.ui.formatters import format_int
from stock_13f.ui.formatters import format_usd


def test_format_int_handles_none() -> None:
    assert format_int(None) == "-"


def test_format_int_formats_commas() -> None:
    assert format_int(1234567) == "1,234,567"


def test_format_usd_formats_billions() -> None:
    assert format_usd(2_400_000_000) == "$2.4B"


def test_format_usd_handles_invalid_value() -> None:
    assert format_usd("bad") == "-"
