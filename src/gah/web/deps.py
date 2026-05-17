"""M5 — FastAPI 라우터들이 공유하는 의존성 묶음.

`request.app.state.deps` 에 저장되고, 각 라우터가 `Depends` 또는 직접
접근으로 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
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
