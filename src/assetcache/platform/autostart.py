"""M8 — Windows 자동 시작 토글 (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).

표준 사용자 권한으로 HKCU 에 쓰기 가능. GPO 차단 시 OSError 가 발생,
호출처 (settings router) 가 캐치해 사용자에게 표시.

비-Windows 에서는 모든 함수가 no-op / False 반환.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "AssetCacheMCP"


def is_autostart_enabled() -> bool:
    """현재 HKCU\\...\\Run 에 GAH 키가 있는지."""
    if sys.platform != "win32":
        return False
    try:
        import winreg  # type: ignore[import-not-found]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            try:
                value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
                return bool(value)
            except FileNotFoundError:
                return False
    except OSError as e:
        log.warning("autostart 조회 실패: %s", e)
        return False


def set_autostart(enabled: bool, exe_path: Path | None = None) -> None:
    """`enabled=True` 면 키 등록, `False` 면 삭제. 비-Windows 는 no-op."""
    if sys.platform != "win32":
        log.info("autostart no-op on non-Windows (%s)", sys.platform)
        return
    import winreg  # type: ignore[import-not-found]
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            target = _resolve_exe_command(exe_path)
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, target)
            log.info("autostart enabled: %s", target)
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
                log.info("autostart disabled")
            except FileNotFoundError:
                log.debug("autostart 키 이미 없음 — no-op")


def _resolve_exe_command(exe_path: Path | None) -> str:
    """레지스트리에 넣을 실행 명령 문자열.

    우선순위:
      1. 인자 `exe_path` 가 명시되면 그 경로 + ' --tray'
      2. `sys.frozen` (PyInstaller 빌드) 이면 `sys.executable + " --tray"`
      3. dev 환경이면 `sys.executable + " -m assetcache --tray"` (pythonw 권장)
    """
    if exe_path is not None:
        return f'"{exe_path}" --tray'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    return f'"{sys.executable}" -m assetcache --tray'
