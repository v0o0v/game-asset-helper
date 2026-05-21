"""M5 — 트레이 측 FastAPI 의 실 사용 포트를 디스크 파일로 공유.

MCP server (별도 프로세스) 가 `paths.data_dir / "web.port"` 를 읽어
loopback URL (`http://127.0.0.1:<port>/internal/user-pick`) 을 알아낸다.
Atomic write 는 `os.replace` 가 Windows + POSIX 모두 보장.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_FILENAME = "web.port"


def write_web_port(data_dir: Path, port: int) -> None:
    """`data_dir/web.port` 에 포트 번호를 atomic 으로 쓴다."""
    tmp = data_dir / (_FILENAME + ".tmp")
    final = data_dir / _FILENAME
    tmp.write_text(f"{port}\n", encoding="utf-8")
    os.replace(tmp, final)


def read_web_port(data_dir: Path) -> int | None:
    """`data_dir/web.port` 에서 포트 번호를 읽는다. 없거나 잘못된 내용 → None."""
    final = data_dir / _FILENAME
    if not final.exists():
        return None
    try:
        return int(final.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        # race: exists() 체크 이후 파일이 사라짐 — 정상적으로 None 반환
        return None
    except ValueError as e:
        log.warning("web.port 파일 파싱 실패: %s", e)
        return None
    # 다른 OSError (PermissionError 등) 는 propagate — caller 가 알 필요 있음
