"""Logging helpers for backend sync commands."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


DEFAULT_LOG_PATH = Path("data/backend_sync/backend_sync.log")
_CONFIGURED_HANDLER_MARKER = "_stock_13f_configured_handler"


def configure_logging(level: str, log_path: Path | None = None) -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    for handler in tuple(root_logger.handlers):
        if getattr(handler, _CONFIGURED_HANDLER_MARKER, False):
            root_logger.removeHandler(handler)
            handler.close()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    setattr(stream_handler, _CONFIGURED_HANDLER_MARKER, True)
    root_logger.addHandler(stream_handler)

    resolved_log_path = log_path or DEFAULT_LOG_PATH
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        resolved_log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    setattr(file_handler, _CONFIGURED_HANDLER_MARKER, True)
    root_logger.addHandler(file_handler)
