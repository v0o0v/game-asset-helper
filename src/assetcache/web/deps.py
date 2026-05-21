"""M5 — FastAPI 라우터들이 공유하는 의존성 묶음.

`request.app.state.deps` 에 저장되고, 각 라우터가 `Depends` 또는 직접
접근으로 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AppPaths, Config
from ..core.labels import LabelRegistry
from ..core.search import HybridSearcher
from ..core.store import Store
from ..core.usage_tracker import UsageTracker
from .pending import PendingPickQueue


@dataclass(frozen=True)
class WebDeps:
    store: Store
    search: HybridSearcher
    usage: UsageTracker
    registry: LabelRegistry
    queue: Any | None  # AnalysisQueue (M2/M2.1) — MCP-only 모드에선 None
    config: Config
    paths: AppPaths
    pending_picks: PendingPickQueue
    tray_bridge: Any | None = None  # Phase 4 task 4.10 에서 QObject 주입
    library_root: Path | None = None  # M5 bugfix — None 이면 paths.library_dir 폴백 (test 편의)
    llm_registry: Any | None = None  # M11 — BackendRegistry (settings UI 가 test_connection 등에서 사용). None 이면 라우터가 즉시 재생성
    batch_manager: Any | None = None  # M11.1 Phase 5 — BatchManager (cancel UI 용). None 이면 cancel 라우터 no-op


def resolve_asset_path(deps: WebDeps, rel_path: str) -> Path:
    """assets.path (library_root 기준 상대) → 절대 경로.

    deps.library_root 가 None 이면 deps.paths.library_dir 로 폴백
    (test fixtures 가 library_root 명시 주입 안 해도 동작).
    """
    root = deps.library_root or deps.paths.library_dir
    return root / rel_path
