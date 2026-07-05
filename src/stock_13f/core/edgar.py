"""Helpers for configuring edgar/edgartools runtime."""

import importlib
from importlib import util
from stock_13f.core.settings import Settings
import os


def apply_edgar_environment(settings: Settings) -> None:
    os.environ["EDGAR_IDENTITY"] = settings.edgar_identity
    os.environ["EDGAR_ACCESS_MODE"] = settings.edgar_access_mode
    os.environ["EDGAR_USE_LOCAL_DATA"] = "True" if settings.edgar_use_local_data else "False"
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(settings.edgar_local_data_dir)
    if util.find_spec("edgar") is None:
        return
    edgar_module = importlib.import_module("edgar")
    configure_http = getattr(edgar_module, "configure_http", None)
    if callable(configure_http):
        configure_http(use_system_certs=True)
