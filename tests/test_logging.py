"""Tests for gah.logging_setup."""

from __future__ import annotations

import logging
from pathlib import Path


def test_setup_logging_creates_log_file(tmp_path: Path, clean_root_logger) -> None:
    from gah.logging_setup import setup_logging

    log_path = tmp_path / "logs" / "gah.log"
    setup_logging(log_path)
    logging.getLogger("gah.test").info("hello")

    # flush handlers
    for h in logging.getLogger().handlers:
        h.flush()

    assert log_path.exists()
    assert log_path.stat().st_size > 0


def test_setup_logging_writes_record(tmp_path: Path, clean_root_logger) -> None:
    from gah.logging_setup import setup_logging

    log_path = tmp_path / "gah.log"
    setup_logging(log_path)
    logger = logging.getLogger("gah.t")
    logger.warning("special-marker-42")
    for h in logging.getLogger().handlers:
        h.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "special-marker-42" in content
    assert "WARNING" in content


def test_setup_logging_is_idempotent(tmp_path: Path, clean_root_logger) -> None:
    from gah.logging_setup import setup_logging

    log_path = tmp_path / "gah.log"
    setup_logging(log_path)
    handler_count_after_first = len(logging.getLogger().handlers)
    setup_logging(log_path)
    handler_count_after_second = len(logging.getLogger().handlers)
    assert handler_count_after_first == handler_count_after_second


def test_setup_logging_format_contains_level_and_message(
    tmp_path: Path, clean_root_logger
) -> None:
    from gah.logging_setup import setup_logging

    log_path = tmp_path / "gah.log"
    setup_logging(log_path)
    logging.getLogger("gah.formatcheck").error("boom-token")
    for h in logging.getLogger().handlers:
        h.flush()

    line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "ERROR" in line
    assert "gah.formatcheck" in line
    assert "boom-token" in line
