"""Application settings for backend sync commands."""

from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path
import os


class SettingsError(RuntimeError):
    """Raised when required runtime settings are missing."""


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BackendPaths:
    repo_root: Path
    src_dir: Path
    scripts_dir: Path
    data_dir: Path
    reports_dir: Path
    backend_state_dir: Path
    checkpoints_path: Path
    edgar_cache_dir: Path
    raw_8k_dir: Path
    raw_13dg_dir: Path
    marts_dir: Path


@dataclass(frozen=True)
class Settings:
    paths: BackendPaths
    edgar_identity: str
    edgar_access_mode: str
    edgar_use_local_data: bool
    edgar_local_data_dir: Path
    supabase_url: str
    supabase_secret_key: str
    supabase_publishable_key: str

    @classmethod
    def load(cls) -> "Settings":
        repo_root = Path(__file__).resolve().parents[3]
        load_dotenv(repo_root / ".env", override=False)
        backend_state_dir = repo_root / "data" / "backend_sync"
        paths = BackendPaths(
            repo_root=repo_root,
            src_dir=repo_root / "src",
            scripts_dir=repo_root / "scripts",
            data_dir=repo_root / "data",
            reports_dir=repo_root / "reports",
            backend_state_dir=backend_state_dir,
            checkpoints_path=backend_state_dir / "checkpoints.json",
            edgar_cache_dir=Path(
                os.environ.get(
                    "EDGAR_LOCAL_DATA_DIR",
                    backend_state_dir / "edgar_cache",
                )
            ),
            raw_8k_dir=backend_state_dir / "raw_8k",
            raw_13dg_dir=backend_state_dir / "raw_13dg",
            marts_dir=backend_state_dir / "marts",
        )
        return cls(
            paths=paths,
            edgar_identity=os.environ.get("EDGAR_IDENTITY", "").strip(),
            edgar_access_mode=os.environ.get("EDGAR_ACCESS_MODE", "NORMAL").strip() or "NORMAL",
            edgar_use_local_data=_parse_bool(os.environ.get("EDGAR_USE_LOCAL_DATA"), True),
            edgar_local_data_dir=paths.edgar_cache_dir,
            supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
            supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY", "").strip(),
            supabase_publishable_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.paths.backend_state_dir,
            self.paths.raw_8k_dir,
            self.paths.raw_13dg_dir,
            self.paths.marts_dir,
            self.edgar_local_data_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def validate_edgar(self) -> list[str]:
        warnings: list[str] = []
        if not self.edgar_identity:
            raise SettingsError("EDGAR_IDENTITY is required for backend sync commands.")
        if self.edgar_access_mode not in {"NORMAL", "CAUTION", "CRAWL"}:
            warnings.append(
                f"Unsupported EDGAR_ACCESS_MODE={self.edgar_access_mode!r}; expected NORMAL, CAUTION, or CRAWL."
            )
        return warnings

    def validate_supabase(self) -> list[str]:
        warnings: list[str] = []
        if not self.supabase_url:
            warnings.append("SUPABASE_URL is not set.")
        if not self.supabase_secret_key:
            warnings.append("SUPABASE_SECRET_KEY is not set.")
        if not self.supabase_publishable_key:
            warnings.append("SUPABASE_PUBLISHABLE_KEY is not set.")
        return warnings
