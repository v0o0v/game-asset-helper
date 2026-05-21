"""QApplication wiring for tray mode.

M5: main_window / library_view / labels_admin Qt UI 의존성 제거.
트레이 + 분석 큐 + 워처는 그대로, GUI 는 FastAPI 웹서버 + 시스템 브라우저로.

PySide6 imports remain function-scoped so importing ``assetcache.app`` in a
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
from .core.llm.registry import BackendRegistry
from .core.labels import LabelRegistry
from .core.scanner import reconcile_library
from .core.search import HybridSearcher
from .core.store import Store
from .core.usage_tracker import UsageTracker
from .core.watcher import LibraryWatcher
from .web.server import WebServer

log = logging.getLogger(__name__)


def _boot_unity_scan(config: Config, store: "Store") -> None:
    """M7 Task 2.5 D6: 부팅 직후 자동 스캔 (별도 스레드).

    ASSETSTORE_CACHE_PATH 환경변수 또는 Config 에서 캐시 경로를 탐지한다.
    경로가 없거나 임포트 실패 시 조용히 종료.
    """
    try:
        from assetcache.core.unity_import.cache_paths import detect_cache_path
        from assetcache.core.unity_import.scanner import UnityAssetStoreScanner
    except ImportError:
        log.debug("unity_import 모듈 없음 — 부팅 자동 스캔 skip")
        return
    cache = detect_cache_path(config)
    if cache is None:
        log.debug("Unity 캐시 경로 없음 — 부팅 자동 스캔 skip")
        return
    try:
        scanner = UnityAssetStoreScanner(store=store)
        result = scanner.run_once(cache_path=cache)
        if result.new > 0:
            log.info("Unity 캐시 스캔 완료: 새 패키지 %d개", result.new)
        else:
            log.debug("Unity 캐시 스캔 완료: 변경 없음")
    except Exception:
        log.exception("Unity 부팅 자동 스캔 오류")


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

    # ── M7: 부팅 자동 스캔 (Unity Asset Store) ────────────────────────
    import threading
    threading.Thread(
        target=_boot_unity_scan, args=(config, store), daemon=True,
    ).start()

    # ── M1: reconcile library state ─────────────────────────────────
    report = reconcile_library(store, library_root)
    log.info(
        "library reconciled: +%d / -%d / =%d",
        len(report.added), len(report.removed), len(report.rescanned),
    )

    # ── M2: analysis pipeline ──────────────────────────────────────
    # M11: BackendChain 으로 라우팅. Phase 0 default 는 ollama 1순위 + chain 1개.
    registry_llm = BackendRegistry.from_config(config)
    chain_image = registry_llm.get_chain("chat_image")
    chain_audio = registry_llm.get_chain("chat_audio")
    chain_embed = registry_llm.get_chain("text_embed")
    embedder = EmbeddingEncoder(chain_embed, model=config.model_embed)
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
        ollama=chain_image, clip=clip, embedder=embedder, registry=registry,
    )
    spritesheet = SpritesheetAnalyzer(  # M6
        sprite=sprite, ollama=chain_image,
        registry=registry, embedder=embedder, clip=clip,
    )
    sound = SoundAnalyzer(
        ollama=chain_audio, embedder=embedder, registry=registry,
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

    # M11.1 Task 3.7 — BatchManager 주입 (AnalysisQueue 생성 직후, start/drain 전)
    from .core.batch.manager import BatchManager as _BatchManager
    from .core.batch.poller import BatchPoller as _BatchPoller
    _batch_manager = _BatchManager(
        store=store,
        chain_registry=registry_llm,
        analysis_queue=queue,
        cfg=config,
        library_dir=library_root,
    )
    queue.set_batch_manager(_batch_manager)

    # M11.1 Task 4.4 — BatchPoller daemon thread (active batch job polling)
    _batch_poller = _BatchPoller(
        store=store,
        chain_registry=registry_llm,
        analysis_queue=queue,
        cfg=config,
    )
    _batch_poller.start()

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
        llm_registry=registry_llm,  # M11 Phase 5 — settings UI 의 test_connection 가 사용
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
    tray = make_tray_icon(
        qapp,
        on_open_main=lambda: webbrowser.open(url),
        cfg=config,
        cfg_path=paths.config_path,
    )
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
    qapp._assetcache_tray = tray  # type: ignore[attr-defined]
    qapp._assetcache_store = store  # type: ignore[attr-defined]
    qapp._assetcache_watcher = watcher  # type: ignore[attr-defined]
    qapp._assetcache_queue = queue  # type: ignore[attr-defined]
    qapp._assetcache_registry = registry  # type: ignore[attr-defined]
    qapp._assetcache_searcher = searcher  # type: ignore[attr-defined]
    qapp._assetcache_usage = usage  # type: ignore[attr-defined]
    qapp._assetcache_web = web  # type: ignore[attr-defined]

    log.info("GAH tray ready (url=%s, library=%s)", url, library_root)
    rc = qapp.exec()

    web.stop()
    _batch_poller.stop(timeout=5.0)
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
