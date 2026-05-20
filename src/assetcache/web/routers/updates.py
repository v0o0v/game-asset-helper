"""PyPI 신버전 알림 라우터 — /api/updates/check 만.

M11+ — module-level UpdateChecker singleton + asyncio.Lock 으로 ETag cache 가
실제 작동하도록 fix. 이전 코드는 라우터 호출마다 새 UpdateChecker 인스턴스를
생성 → cache 매번 빈 상태 → 모든 요청이 PyPI 200 OK GET. 페이지 진입마다
banner 가 호출하므로 사용자 navigate 시 spam.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter

from assetcache.core.updater.checker import UpdateChecker
from assetcache.core.updater.pip_command import recommended_upgrade_command
from assetcache.core.updater.version import Version


def get_current_version() -> Version:
    from assetcache import __version__
    return Version.parse(__version__)


router = APIRouter(prefix="/api/updates", tags=["updates"])


# M11+ — module-level singleton. lazy init (첫 호출 시 current version 결정).
_checker: Optional[UpdateChecker] = None
_checker_lock = asyncio.Lock()


def _get_checker() -> UpdateChecker:
    """singleton UpdateChecker — process 일생 동안 같은 instance 재사용.

    이전 라우터는 매 호출마다 새 instance 만들어 ETag cache 가 의미 없었음.
    같은 instance 를 유지하면 첫 호출 후 PyPI 가 304 (Not Modified) 응답으로
    payload 전송 안 함 — 응답 크기 ~5KB → 0.
    """
    global _checker
    if _checker is None:
        _checker = UpdateChecker(
            package_name="assetcache-mcp", current=get_current_version()
        )
    return _checker


@router.get("/check")
async def check():
    current = get_current_version()
    # asyncio.Lock 으로 동시 호출 직렬화 (singleton cache 의 race 회피).
    async with _checker_lock:
        result = await _get_checker().check_once()
    return {
        "current": str(current),
        "latest": str(result.latest),
        "available": result.available,
        "command": recommended_upgrade_command("assetcache-mcp"),
        "release_notes_url": result.release_notes_url,
        "error": result.error,
    }
