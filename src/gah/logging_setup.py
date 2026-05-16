"""Idempotent logging setup for Game Asset Helper.

A single call to `setup_logging` installs both a console handler (INFO+)
and a rotating file handler (10MB × 5 backups), as specified in
DESIGN.md §9.  Repeat calls reconfigure the same handlers in place
instead of stacking new ones.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUPS = 5

# Sentinels marking handlers owned by setup_logging, so repeated calls
# don't stack additional handlers (idempotency requirement).
_FILE_HANDLER_ATTR = "_gah_file_handler"
_CONSOLE_HANDLER_ATTR = "_gah_console_handler"


def setup_logging(log_path: Path, level: int = logging.INFO) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)

    file_handler = _existing_handler(root, _FILE_HANDLER_ATTR)
    if file_handler is None:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUPS,
            encoding="utf-8",
        )
        setattr(file_handler, _FILE_HANDLER_ATTR, True)
        root.addHandler(file_handler)
    else:
        # may have been pointed at a different path on the second call (tests do this)
        if Path(file_handler.baseFilename) != log_path:
            file_handler.close()
            root.removeHandler(file_handler)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUPS,
                encoding="utf-8",
            )
            setattr(file_handler, _FILE_HANDLER_ATTR, True)
            root.addHandler(file_handler)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = _existing_handler(root, _CONSOLE_HANDLER_ATTR)
    if console_handler is None:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        setattr(console_handler, _CONSOLE_HANDLER_ATTR, True)
        root.addHandler(console_handler)
    console_handler.setLevel(max(level, logging.INFO))
    console_handler.setFormatter(formatter)


def _existing_handler(root: logging.Logger, marker_attr: str) -> logging.Handler | None:
    for h in root.handlers:
        if getattr(h, marker_attr, False):
            return h
    return None
