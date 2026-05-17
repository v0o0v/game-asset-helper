"""QApplication wiring for tray mode.

M2 layers the analysis stack on top of M1:
  store → label registry (seeded) → ollama / embedder / clip
       → sprite + sound analyzers → analysis queue
       → wired into watcher callbacks and into the main window's
         progress slot + tray tooltip.

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
from .core.clip_labeler import ClipLabeler, OpenClipBackend
from .core.embedding import EmbeddingEncoder
from .core.labels import LabelRegistry
from .core.ollama_client import OllamaClient
from .core.scanner import reconcile_library
from .core.store import Store
from .core.watcher import LibraryWatcher

log = logging.getLogger(__name__)


def _resolve_library_root(paths: AppPaths, config: Config) -> Path:
    if config.library_dir_override:
        return Path(config.library_dir_override).expanduser().resolve()
    return paths.library_dir


def run_tray(paths: AppPaths, config: Config, argv: Sequence[str] | None = None) -> int:
    """Boot the tray application. Returns the QApplication exit code."""
    from PySide6.QtWidgets import QApplication

    from .tray import make_tray_icon, update_tray_tooltip
    from .ui.main_window import MainWindow

    qapp = QApplication(list(argv or sys.argv))
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
        len(report.added),
        len(report.removed),
        len(report.rescanned),
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
    sound = SoundAnalyzer(
        ollama=ollama, embedder=embedder, registry=registry,
        spectrogram_cache_dir=paths.cache_dir / "spectrograms",
        max_clip_seconds=config.audio_max_seconds,
        chunk_strategy=config.audio_chunk_strategy,
    )
    queue = AnalysisQueue(
        store, sprite=sprite, sound=sound,
        concurrency=config.analysis_concurrency,
        library_root=library_root,
    )
    queue.start()
    queue.drain_pending()

    # ── GUI 연결 ────────────────────────────────────────────────────
    main_window = MainWindow(store)
    main_window.set_library_root(library_root)
    main_window.set_label_registry(registry)
    main_window.refresh()

    # 워처 이벤트는 GUI 스레드로 마샬링되어 _on_pack_changed 가 인테이크를 마치고
    # refresh 한 다음, pack 별 pending 을 분석 큐로 흘려보낸다.
    def _on_pack_changed(pack_name: str) -> None:
        main_window.packChanged.emit(pack_name)
        pack_row = store.get_pack_by_name(pack_name)
        if pack_row is not None:
            queue.enqueue_pack(pack_row.id)

    watcher = LibraryWatcher(
        window_seconds=config.watch_debounce_seconds,
        on_pack_changed=_on_pack_changed,
    )
    watcher.start(library_root)

    # ── 큐 → GUI 시그널 라우팅 ──────────────────────────────────────
    queue.analysisFinished.connect(main_window.on_asset_analyzed)
    queue.progressChanged.connect(main_window.update_progress)

    tray = make_tray_icon(
        qapp,
        on_open_main=main_window.show_and_raise,
        on_open_labels=main_window.open_labels_admin,
    )
    queue.progressChanged.connect(lambda snap: update_tray_tooltip(tray, snap))

    qapp._gah_tray = tray  # type: ignore[attr-defined]
    qapp._gah_store = store  # type: ignore[attr-defined]
    qapp._gah_watcher = watcher  # type: ignore[attr-defined]
    qapp._gah_main_window = main_window  # type: ignore[attr-defined]
    qapp._gah_queue = queue  # type: ignore[attr-defined]
    qapp._gah_registry = registry  # type: ignore[attr-defined]

    log.info("GAH tray ready (data_dir=%s, library=%s)", paths.data_dir, library_root)
    rc = qapp.exec()

    queue.stop()
    watcher.stop()
    store.close()
    return rc
