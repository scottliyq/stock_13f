from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from stock_13f.core.edgar import apply_edgar_environment
from stock_13f.core.settings import BackendPaths
from stock_13f.core.settings import Settings


def build_settings(tmp_path: Path) -> Settings:
    paths = BackendPaths(
        repo_root=tmp_path,
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        backend_state_dir=tmp_path / "backend_state",
        checkpoints_path=tmp_path / "backend_state" / "checkpoints.json",
        edgar_cache_dir=tmp_path / "backend_state" / "edgar_cache",
        raw_8k_dir=tmp_path / "backend_state" / "raw_8k",
        raw_13dg_dir=tmp_path / "backend_state" / "raw_13dg",
        marts_dir=tmp_path / "backend_state" / "marts",
    )
    return Settings(
        paths=paths,
        edgar_identity="stock_13f test@example.com",
        edgar_access_mode="NORMAL",
        edgar_use_local_data=True,
        edgar_local_data_dir=paths.edgar_cache_dir,
        supabase_url="",
        supabase_secret_key="",
        supabase_publishable_key="",
    )


def test_apply_edgar_environment_uses_system_certs_when_edgar_is_available(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeEdgarModule:
        @staticmethod
        def configure_http(*, use_system_certs: bool) -> None:
            captured["use_system_certs"] = use_system_certs

    monkeypatch.setattr("stock_13f.core.edgar.util.find_spec", lambda name: object() if name == "edgar" else None)
    monkeypatch.setattr("stock_13f.core.edgar.importlib.import_module", lambda name: FakeEdgarModule())

    settings = build_settings(tmp_path)
    apply_edgar_environment(settings)

    assert captured["use_system_certs"] is True
