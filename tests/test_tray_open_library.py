"""트레이 메뉴 "라이브러리 폴더 열기" — M11.10 piggyback UX 기능.

사용자가 트레이에서 library_dir 을 1-click 으로 탐색기로 열 수 있게 한다.
격리 data-dir LIVE 검증 시 sprite asset drop 위치를 즉시 찾아갈 수 있어
편의성 향상.

기능 요구:
1. cfg 가 전달되면 menu 에 "라이브러리 폴더 열기" QAction 추가.
2. 클릭 시 ``cfg.library_dir`` 을 OS 기본 탐색기로 연다.
3. ``library_dir`` 가 없으면 자동 mkdir (parents=True, exist_ok=True).
4. cfg 미전달 시 (legacy / 테스트) 항목 없음 — 기존 동작 보존.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@dataclass
class _FakeBatch:
    toggle: str = "auto"


@dataclass
class _FakeCfg:
    library_dir: Path
    batch: _FakeBatch = None

    def __post_init__(self) -> None:
        if self.batch is None:
            self.batch = _FakeBatch()


def test_menu_includes_open_library_action_when_cfg_given(qapp, tmp_path):
    """cfg 가 있으면 menu 에 '라이브러리 폴더 열기' 항목 포함."""
    from assetcache.tray import make_tray_icon
    cfg = _FakeCfg(library_dir=tmp_path / "library")
    tray = make_tray_icon(
        qapp, on_open_main=lambda: None,
        cfg=cfg, cfg_path=tmp_path / "config.toml",
    )
    try:
        actions = tray.contextMenu().actions()
        labels = [a.text() for a in actions]
        assert any("라이브러리" in t and "열기" in t for t in labels), \
            f"라이브러리 폴더 열기 항목 없음: {labels}"
    finally:
        tray.hide()


def test_open_library_action_creates_dir_if_missing(qapp, tmp_path):
    """library_dir 가 없으면 클릭 시 mkdir 자동 생성."""
    from assetcache.tray import make_tray_icon
    target = tmp_path / "library_missing"
    assert not target.exists()
    cfg = _FakeCfg(library_dir=target)
    tray = make_tray_icon(
        qapp, on_open_main=lambda: None,
        cfg=cfg, cfg_path=tmp_path / "config.toml",
    )
    try:
        actions = tray.contextMenu().actions()
        open_lib = next(a for a in actions if "라이브러리" in a.text())
        # QDesktopServices.openUrl 은 헤드리스에서 외부 프로그램 호출 — patch
        with patch("assetcache.tray.QDesktopServices") as fake_ds:
            fake_ds.openUrl.return_value = True
            open_lib.trigger()
        assert target.exists() and target.is_dir(), \
            "library_dir 가 자동 생성돼야 함"
    finally:
        tray.hide()


def test_open_library_action_calls_desktop_services(qapp, tmp_path):
    """클릭 시 QDesktopServices.openUrl 가 library_dir 로 호출됨."""
    from assetcache.tray import make_tray_icon
    target = tmp_path / "library"
    target.mkdir()
    cfg = _FakeCfg(library_dir=target)
    tray = make_tray_icon(
        qapp, on_open_main=lambda: None,
        cfg=cfg, cfg_path=tmp_path / "config.toml",
    )
    try:
        actions = tray.contextMenu().actions()
        open_lib = next(a for a in actions if "라이브러리" in a.text())
        with patch("assetcache.tray.QDesktopServices") as fake_ds:
            fake_ds.openUrl.return_value = True
            open_lib.trigger()
            assert fake_ds.openUrl.called, "QDesktopServices.openUrl 호출 안 됨"
            # 인자 = QUrl 객체.  toLocalFile 로 풀어 비교
            url_arg = fake_ds.openUrl.call_args.args[0]
            assert str(target) in url_arg.toLocalFile() or \
                str(target).replace("\\", "/") in url_arg.toLocalFile()
    finally:
        tray.hide()


def test_menu_without_cfg_has_no_library_action(qapp):
    """cfg 미전달 시 '라이브러리 폴더 열기' 항목 없음 (기존 동작 보존)."""
    from assetcache.tray import make_tray_icon
    tray = make_tray_icon(qapp, on_open_main=lambda: None)
    try:
        actions = tray.contextMenu().actions()
        labels = [a.text() for a in actions]
        assert not any("라이브러리" in t and "열기" in t for t in labels), \
            f"cfg 없이도 항목이 추가됨: {labels}"
    finally:
        tray.hide()
