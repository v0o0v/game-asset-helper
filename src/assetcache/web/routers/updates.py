"""PyPI 신버전 알림 라우터 — /api/updates/check 만."""

from __future__ import annotations

from fastapi import APIRouter

from assetcache.core.updater.checker import UpdateChecker
from assetcache.core.updater.pip_command import recommended_upgrade_command
from assetcache.core.updater.version import Version


def get_current_version() -> Version:
    from assetcache import __version__
    return Version.parse(__version__)


router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("/check")
async def check():
    current = get_current_version()
    checker = UpdateChecker(package_name="assetcache-mcp", current=current)
    result = await checker.check_once()
    return {
        "current": str(current),
        "latest": str(result.latest),
        "available": result.available,
        "command": recommended_upgrade_command("assetcache-mcp"),
        "release_notes_url": result.release_notes_url,
        "error": result.error,
    }
