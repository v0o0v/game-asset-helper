"""Phase 5 task 5.4 — tray batch toggle smoke test (Qt headless).

트레이 메뉴에 Batch mode toggle 이 추가됐는지 + 상태 변경 시 cfg.batch.toggle 이
갱신되는지 검증한다.

QT_QPA_PLATFORM=offscreen 은 conftest.py qt_offscreen autouse fixture 가 보장.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path


# ─── fixture ─────────────────────────────────────────────────────────────────


# ─── Test 1: make_tray_icon 이 batch_toggle_action attribute 를 설정한 tray 반환 ──


def test_make_tray_icon_batch_submenu_exists(qapp, tmp_path):
    """make_tray_icon 이 반환하는 QSystemTrayIcon.contextMenu() 에
    'Batch' 라는 텍스트가 들어간 메뉴 항목 또는 sub-menu 가 있어야 한다.
    """
    from assetcache.tray import make_tray_icon

    tray = make_tray_icon(qapp)
    try:
        menu = tray.contextMenu()
        assert menu is not None

        # 메뉴 액션 중 'batch' (대소문자 무시) 가 포함된 항목이 하나 이상 있어야 한다.
        action_texts = [a.text().lower() for a in menu.actions()]
        sub_texts: list[str] = []
        for a in menu.actions():
            if a.menu() is not None:
                sub_texts.extend(sa.text().lower() for sa in a.menu().actions())

        all_texts = action_texts + sub_texts
        assert any("batch" in t for t in all_texts), (
            f"'batch' 텍스트 미발견 — 메뉴 항목: {action_texts}, 서브메뉴: {sub_texts}"
        )
    finally:
        tray.hide()


# ─── Test 2: cycle_batch_toggle 호출 시 cfg.batch.toggle 갱신 + save_config 호출 ─


def test_cycle_batch_toggle_updates_cfg(tmp_path):
    """cycle_batch_toggle(cfg, path) 이 auto→forced_on→forced_off→auto 순서로
    cfg.batch.toggle 을 갱신하고 save_config 를 호출해야 한다.
    """
    from assetcache.config import BatchConfig, Config, save_config
    from assetcache.tray import cycle_batch_toggle

    cfg_path = tmp_path / "config.toml"

    cfg = Config()
    cfg.batch = BatchConfig(toggle="auto")

    # auto → forced_on
    cycle_batch_toggle(cfg, cfg_path)
    assert cfg.batch.toggle == "forced_on"

    # forced_on → forced_off
    cycle_batch_toggle(cfg, cfg_path)
    assert cfg.batch.toggle == "forced_off"

    # forced_off → auto
    cycle_batch_toggle(cfg, cfg_path)
    assert cfg.batch.toggle == "auto"

    # 파일이 저장됐는지 확인
    assert cfg_path.exists()


def test_cycle_batch_toggle_persists_to_disk(tmp_path):
    """cycle_batch_toggle 후 disk 에 저장된 config 를 load_config 로 읽으면
    변경된 toggle 값이 반영돼 있어야 한다.
    """
    from assetcache.config import BatchConfig, Config, load_config
    from assetcache.tray import cycle_batch_toggle

    cfg_path = tmp_path / "config.toml"

    cfg = Config()
    cfg.batch = BatchConfig(toggle="auto")

    cycle_batch_toggle(cfg, cfg_path)  # auto → forced_on

    loaded = load_config(cfg_path)
    assert loaded.batch.toggle == "forced_on"
