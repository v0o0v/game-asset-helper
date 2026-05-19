"""pip_command.recommended_upgrade_command 환경 분기 테스트."""
from __future__ import annotations

import pytest

from assetcache.core.updater.pip_command import recommended_upgrade_command


def test_returns_pipx_when_pipx_available(monkeypatch):
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "C:/pipx.exe" if name == "pipx" else None,
    )
    cmd = recommended_upgrade_command("assetcache-mcp")
    assert cmd == "pipx upgrade assetcache-mcp"


def test_returns_uv_tool_when_uv_available_no_pipx(monkeypatch):
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "C:/uv.exe" if name == "uv" else None,
    )
    cmd = recommended_upgrade_command("assetcache-mcp")
    assert cmd == "uv tool upgrade assetcache-mcp"


def test_returns_pip_when_neither_available(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    cmd = recommended_upgrade_command("assetcache-mcp")
    assert cmd == "pip install -U assetcache-mcp"
