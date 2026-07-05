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
    subparsers_action = next(action for action in parser._actions if action.dest == "command")
    assert "sync-13f" in help_text
    assert "sync-8k" in help_text
    assert "sync-13dg" in help_text
    assert "audit-13dg-coverage" in help_text
    assert "rebuild-marts" in help_text
    assert "backfill-tickers" in help_text
    assert "sync-all" in help_text
    assert "show-status" in help_text
    assert "--form-scope" in subparsers_action.choices["sync-13dg"].format_help()
    assert "--manager-ciks" in subparsers_action.choices["sync-13dg"].format_help()
    assert "--manager-scope" in subparsers_action.choices["audit-13dg-coverage"].format_help()
    assert "--with-openfigi" in subparsers_action.choices["backfill-tickers"].format_help()


def test_split_tickers_normalizes_values() -> None:
    assert backend_sync._split_tickers("msft, aapl , nvda") == ("MSFT", "AAPL", "NVDA")
    assert backend_sync._split_tickers("") == ()


def test_split_identifiers_preserves_cik_text_values() -> None:
    assert backend_sync._split_identifiers("2045724, 1336528") == ("2045724", "1336528")
    assert backend_sync._split_identifiers("") == ()
