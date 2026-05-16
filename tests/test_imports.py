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
]


def test_all_modules_importable() -> None:
    for name in MODULES:
        importlib.import_module(name)
