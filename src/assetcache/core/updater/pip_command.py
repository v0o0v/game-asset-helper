"""사용자 환경 검출 후 적절한 upgrade 명령 반환."""

from __future__ import annotations

import shutil


def recommended_upgrade_command(package: str = "assetcache-mcp") -> str:
    if shutil.which("pipx"):
        return f"pipx upgrade {package}"
    if shutil.which("uv"):
        return f"uv tool upgrade {package}"
    return f"pip install -U {package}"
