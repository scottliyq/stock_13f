"""Helpers for configuring edgar/edgartools runtime."""

from stock_13f.core.settings import Settings
import os


def apply_edgar_environment(settings: Settings) -> None:
    os.environ["EDGAR_IDENTITY"] = settings.edgar_identity
    os.environ["EDGAR_ACCESS_MODE"] = settings.edgar_access_mode
    os.environ["EDGAR_USE_LOCAL_DATA"] = "True" if settings.edgar_use_local_data else "False"
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(settings.edgar_local_data_dir)
