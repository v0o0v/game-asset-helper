"""M8 — autostart.py winreg get/set 단위 테스트 (mock)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from assetcache.platform import autostart


@pytest.fixture
def mock_winreg(monkeypatch):
    """winreg 모듈 자체를 MagicMock 으로 대체 (Windows 외 환경에서도 import 가능)."""
    mock = MagicMock()
    mock.HKEY_CURRENT_USER = "HKCU"
    mock.KEY_SET_VALUE = 2
    mock.REG_SZ = 1
    monkeypatch.setitem(sys.modules, "winreg", mock)
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    return mock


def test_is_enabled_returns_true_when_key_exists(mock_winreg):
    mock_winreg.OpenKey.return_value.__enter__.return_value = MagicMock()
    mock_winreg.QueryValueEx.return_value = ("C:/path/exe --tray", 1)
    assert autostart.is_autostart_enabled() is True


def test_is_enabled_returns_false_when_key_missing(mock_winreg):
    mock_winreg.OpenKey.return_value.__enter__.return_value = MagicMock()
    mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
    assert autostart.is_autostart_enabled() is False


def test_is_enabled_returns_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    assert autostart.is_autostart_enabled() is False


def test_set_enabled_writes_value(mock_winreg, tmp_path):
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key
    exe = tmp_path / "assetcache.exe"
    exe.write_bytes(b"\x00")  # exists
    autostart.set_autostart(True, exe_path=exe)
    mock_winreg.SetValueEx.assert_called_once()
    args = mock_winreg.SetValueEx.call_args[0]
    assert args[1] == "AssetCacheMCP"  # value name
    assert str(exe) in args[4]  # 명령에 exe 경로 포함


def test_set_enabled_deletes_value_when_disabled(mock_winreg):
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key
    autostart.set_autostart(False)
    mock_winreg.DeleteValue.assert_called_once_with(key, "AssetCacheMCP")


def test_set_handles_missing_value_on_disable(mock_winreg):
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key
    mock_winreg.DeleteValue.side_effect = FileNotFoundError()
    # 이미 없는 키 삭제 시도는 무시 (예외 안 던짐)
    autostart.set_autostart(False)


def test_set_noop_on_non_windows(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    autostart.set_autostart(True)  # 예외 없이 통과


def test_resolve_exe_command_uses_frozen_path(monkeypatch):
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", "C:/dist/GAH.exe")
    cmd = autostart._resolve_exe_command(None)
    assert "C:/dist/GAH.exe" in cmd
    assert "--tray" in cmd


def test_resolve_exe_command_uses_dev_pythonw(monkeypatch):
    monkeypatch.setattr(autostart.sys, "frozen", False, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", "C:/Python/python.exe")
    cmd = autostart._resolve_exe_command(None)
    assert "python" in cmd.lower()
    assert "-m assetcache" in cmd
    assert "--tray" in cmd
