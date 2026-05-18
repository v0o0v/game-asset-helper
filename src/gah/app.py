"""QApplication wiring for tray mode.

M5: main_window / library_view / labels_admin Qt UI 의존성 제거.
트레이 + 분석 큐 + 워처는 그대로, GUI 는 FastAPI 웹서버 + 시스템 브라우저로.

PySide6 imports remain function-scoped so importing ``gah.app`` in a
non-GUI context (CLI ``--version``, unit tests) does not require a Qt
platform plugin.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

from .config import AppPaths, Config
from .core.analysis_queue import AnalysisQueue
from .core.analyzer.sound import SoundAnalyzer
from .core.analyzer.sprite import SpriteAnalyzer
from .core.analyzer.spritesheet import SpritesheetAnalyzer  # M6
from .core.clip_labeler import ClipLabeler, OpenClipBackend
from .core.consistency import ConsistencyScorer
from .core.embedding import EmbeddingEncoder
from .core.labels import LabelRegistry
from .core.ollama_client import OllamaClient
from .core.scanner import reconcile_library
from .core.search import HybridSearcher
from .core.store import Store
from .core.usage_tracker import UsageTracker
from .core.watcher import LibraryWatcher
from .web.server import WebServer

log = logging.getLogger(__name__)


def _resolve_library_root(paths: AppPaths, config: Config) -> Path:
    if config.library_dir_override:
        return Path(config.library_dir_override).expanduser().resolve()
    return paths.library_dir


def run_tray(paths: AppPaths, config: Config, argv: Sequence[str] | None = None) -> int:
    """Boot the tray application. Returns the QApplication exit code.

    M5: main_window/library_view/labels_admin Qt 의존성 제거. 트레이 +
    분석 큐 + 워처는 그대로, GUI 는 FastAPI 웹서버 + 시스템 브라우저로.
    """
    from PySide6.QtWidgets import QApplication
    import webbrowser

    from .tray import make_tray_icon, notify_user_pick_request, update_tray_tooltip
    from .web.deps import WebDeps
    from .web.pending import PendingPickQueue
    from .web.sse_bus import broadcast as sse_broadcast
    from .web.tray_bridge import TrayBridge

    qapp = QApplication.instance() or QApplication(list(argv or sys.argv))
    qapp.setQuitOnLastWindowClosed(False)

    library_root = _resolve_library_root(paths, config)
    library_root.mkdir(parents=True, exist_ok=True)

    # ── store + label registry ──────────────────────────────────────
    store = Store(paths.db_path)
    store.initialize()
    registry = LabelRegistry(store)
    registry.bootstrap()

    # ── M1: reconcile library state ─────────────────────────────────
    report = reconcile_library(store, library_root)
    log.info(
        "library reconciled: +%d / -%d / =%d",
        len(report.added), len(report.removed), len(report.rescanned),
    )

    # ── M2: analysis pipeline ──────────────────────────────────────
    ollama = OllamaClient(
        base_url=config.ollama_url,
        model=config.model_image,
        timeout_seconds=config.analysis_timeout_seconds,
        max_retries=config.analysis_max_retries,
        parallel=config.ollama_parallel,
    )
    embedder = EmbeddingEncoder(ollama, model=config.model_embed)
    clip: ClipLabeler | None = None
    if config.clip_enable:
        try:
            backend = OpenClipBackend(
                model=config.clip_model,
                pretrained=config.clip_pretrained,
                cache_dir=paths.cache_dir / "clip",
            )
            clip = ClipLabeler(
                backend=backend, store=store,
                registry=registry, enabled=True,
            )
        except Exception:  # pragma: no cover - CLIP 실패는 분석 자체를 막지 않음
            log.exception("CLIP backend init failed; continuing without CLIP")
            clip = None

    sprite = SpriteAnalyzer(
        ollama=ollama, clip=clip, embedder=embedder, registry=registry,
    )
    spritesheet = SpritesheetAnalyzer(  # M6
        sprite=sprite, ollama=ollama,
        registry=registry, embedder=embedder, clip=clip,
    )
    sound = SoundAnalyzer(
        ollama=ollama, embedder=embedder, registry=registry,
        spectrogram_cache_dir=paths.cache_dir / "spectrograms",
        max_clip_seconds=config.audio_max_seconds,
        chunk_strategy=config.audio_chunk_strategy,
    )
    queue = AnalysisQueue(
        store, sprite=sprite,
        spritesheet=spritesheet,  # M6 신규 keyword
        sound=sound,
        concurrency=config.analysis_concurrency,
        library_root=library_root,
    )
    queue.start()
    queue.drain_pending()

    # ── M3: 검색 백엔드 ────────────────────────────────────────────
    consistency = ConsistencyScorer(store, config)
    usage = UsageTracker(store, config)
    searcher = HybridSearcher(store, embedder, consistency, registry, config)

    # ── M5: 웹 서버 ────────────────────────────────────────────────
    pending = PendingPickQueue(max_pending=config.claude_pick_max_pending)

    # Phase 4D: TrayBridge — uvicorn worker thread → Qt main thread 마샬링
    bridge = TrayBridge()

    deps = WebDeps(
        store=store, search=searcher, usage=usage, registry=registry,
        queue=queue, config=config, paths=paths, pending_picks=pending,
        tray_bridge=bridge,
        library_root=library_root,  # M5 bugfix: assets.path 상대경로 해석용
    )
    web = WebServer(deps)
    web.start()
    url = f"http://{config.web_host}:{web.actual_port}"

    # ── 워처 ───────────────────────────────────────────────────────
    def _on_pack_changed(pack_name: str) -> None:
        pack_row = store.get_pack_by_name(pack_name)
        if pack_row is not None:
            queue.enqueue_pack(pack_row.id)
        sse_broadcast("pack_changed", {"pack": pack_name})

    watcher = LibraryWatcher(
        window_seconds=config.watch_debounce_seconds,
        on_pack_changed=_on_pack_changed,
    )
    watcher.start(library_root)

    # ── 트레이 + 분석 큐 시그널 라우팅 ─────────────────────────────
    tray = make_tray_icon(qapp, on_open_main=lambda: webbrowser.open(url))
    queue.progressChanged.connect(lambda snap: update_tray_tooltip(tray, snap))
    queue.progressChanged.connect(
        lambda snap: sse_broadcast("analysis_progress", _snap_to_dict(snap))
    )
    # Phase 4D: bridge → tray 툴팁 갱신 (AutoConnection → main thread 마샬링)
    bridge.pickCountChanged.connect(lambda n: notify_user_pick_request(tray, n))

    # ── 브라우저 자동 진입 ─────────────────────────────────────────
    if config.web_open_browser_on_start:
        webbrowser.open(url)

    # state 보존 (디버그)
    qapp._gah_tray = tray  # type: ignore[attr-defined]
    qapp._gah_store = store  # type: ignore[attr-defined]
    qapp._gah_watcher = watcher  # type: ignore[attr-defined]
    qapp._gah_queue = queue  # type: ignore[attr-defined]
    qapp._gah_registry = registry  # type: ignore[attr-defined]
    qapp._gah_searcher = searcher  # type: ignore[attr-defined]
    qapp._gah_usage = usage  # type: ignore[attr-defined]
    qapp._gah_web = web  # type: ignore[attr-defined]

    log.info("GAH tray ready (url=%s, library=%s)", url, library_root)
    rc = qapp.exec()

    web.stop()
    queue.stop()
    watcher.stop()
    store.close()
    return rc


def _snap_to_dict(snap) -> dict:
    """AnalysisProgress 를 SSE 페이로드용 dict 로 변환."""
    from dataclasses import asdict
    d = asdict(snap)
    if d.get("in_flight_path") is not None:
        d["in_flight_path"] = str(d["in_flight_path"])
    return d
