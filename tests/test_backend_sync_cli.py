import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))


spec = importlib.util.spec_from_file_location("backend_sync", SCRIPTS_DIR / "backend_sync.py")
backend_sync = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(backend_sync)


def test_build_parser_supports_required_subcommands() -> None:
    parser = backend_sync.build_parser()
    help_text = parser.format_help()
    assert "sync-13f" in help_text
    assert "sync-8k" in help_text
    assert "sync-13dg" in help_text
    assert "rebuild-marts" in help_text
    assert "sync-all" in help_text
    assert "show-status" in help_text


def test_split_tickers_normalizes_values() -> None:
    assert backend_sync._split_tickers("msft, aapl , nvda") == ("MSFT", "AAPL", "NVDA")
    assert backend_sync._split_tickers("") == ()
