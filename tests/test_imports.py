"""Smoke test: every module of gah must import without side effects."""

from __future__ import annotations

import importlib


MODULES = [
    "gah",
    "gah.__main__",
    "gah.config",
    "gah.logging_setup",
    "gah.platform",
    "gah.platform.single_instance",
    "gah.app",
    "gah.tray",
    "gah.core",
    "gah.core.asset_kind",
    "gah.core.manifest",
    "gah.core.store",
    "gah.core.pack_manager",
    "gah.core.scanner",
    "gah.core.watcher",
    "gah.ui",
    "gah.ui.main_window",
    "gah.ui.pack_view",
    "gah.ui.library_view",
    # M3 신규 모듈
    "gah.core.search",
    "gah.core.consistency",
    "gah.core.usage_tracker",
    "gah.mcp",
    "gah.mcp.models",
    "gah.mcp.tools",
    "gah.mcp.server",
]


def test_all_modules_importable() -> None:
    for name in MODULES:
        importlib.import_module(name)
