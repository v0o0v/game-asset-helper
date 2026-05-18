"""M8 — Windows 자동 시작 토글 (HKCU\\...\\Run).

Task 10 에서 winreg 접근 본격 구현. 본 스켈레톤은 후속 task 가 import 만
하더라도 깨지지 않게 한다.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def is_autostart_enabled() -> bool:
    """현재 자동 시작 등록 여부. Task 10 에서 winreg 조회로 구현."""
    if sys.platform != "win32":
        return False
    return False  # Task 10 에서 본격 구현


def set_autostart(enabled: bool, exe_path: Path | None = None) -> None:
    """자동 시작 등록/해제. Task 10 에서 winreg.SetValueEx / DeleteValue 구현."""
    if sys.platform != "win32":
        log.info("autostart no-op on non-Windows")
        return
    # Task 10 에서 본격 구현
    return
