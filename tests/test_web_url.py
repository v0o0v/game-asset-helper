"""M5 — web.port 파일 R/W (MCP loopback URL 공유) 검증."""
from __future__ import annotations
import logging
import pytest
from pathlib import Path

from gah.web.url import read_web_port, write_web_port


def test_write_creates_file(tmp_path: Path) -> None:
    write_web_port(tmp_path, 9874)
    assert (tmp_path / "web.port").read_text(encoding="utf-8").strip() == "9874"


def test_read_returns_int(tmp_path: Path) -> None:
    (tmp_path / "web.port").write_text("9876", encoding="utf-8")
    assert read_web_port(tmp_path) == 9876


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_web_port(tmp_path) is None


def test_write_is_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    write_web_port(tmp_path, 9874)
    assert not (tmp_path / "web.port.tmp").exists()
    assert (tmp_path / "web.port").exists()


def test_read_invalid_returns_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "web.port").write_text("notanumber\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_web_port(tmp_path) is None
    assert any("web.port" in r.message for r in caplog.records)
