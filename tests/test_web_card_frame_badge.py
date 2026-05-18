"""M6 — 와이드/리스트 카드의 🎞 N frames 배지."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from gah.core.manifest import PackManifest
from gah.core.store import SpriteMeta
from gah.web.app import build_app

_NOW = int(time.time())


def _seed_spritesheet_asset(store) -> int:
    pid = store.upsert_pack(
        "p", PackManifest(None, "kenney", None, None, None), scanned_at=_NOW
    )
    aid = store.upsert_asset(pid, "p/hero.png", "spritesheet", "h", 1024, added_at=_NOW)
    store.save_sprite_meta(
        aid,
        SpriteMeta(
            width=256,
            height=32,
            has_alpha=True,
            is_pixel_art=True,
            dominant_colors=[],
            frame_w=32,
            frame_h=32,
            frame_count=8,
            animation_tags=["walk"],
            animations_json={
                "walk": {
                    "start_frame": 0,
                    "end_frame": 7,
                    "fps_hint": 12,
                    "source": "json_tag",
                }
            },
        ),
    )
    store.mark_asset_state(aid, "ok", error=None, analyzed_at=_NOW)
    return aid


def test_spritesheet_card_shows_frame_badge(deps_fixture):
    _seed_spritesheet_asset(deps_fixture.store)
    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" in r.text or "&#127902;" in r.text
    assert "8 frames" in r.text


def test_sprite_card_no_frame_badge(deps_fixture):
    pid = deps_fixture.store.upsert_pack(
        "p", PackManifest(None, "kenney", None, None, None), scanned_at=_NOW
    )
    aid = deps_fixture.store.upsert_asset(
        pid, "p/sword.png", "sprite", "h", 64, added_at=_NOW
    )
    deps_fixture.store.save_sprite_meta(
        aid,
        SpriteMeta(
            width=32,
            height=32,
            has_alpha=True,
            is_pixel_art=True,
            dominant_colors=[],
        ),
    )
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=_NOW)
    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text and "&#127902;" not in r.text


def test_sound_card_no_frame_badge(deps_fixture):
    pid = deps_fixture.store.upsert_pack(
        "p", PackManifest(None, "kenney", None, None, None), scanned_at=_NOW
    )
    aid = deps_fixture.store.upsert_asset(
        pid, "p/x.wav", "sound", "h", 128, added_at=_NOW
    )
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=_NOW)
    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text and "&#127902;" not in r.text


def test_spritesheet_with_null_frame_count_no_badge(deps_fixture):
    pid = deps_fixture.store.upsert_pack(
        "p", PackManifest(None, "kenney", None, None, None), scanned_at=_NOW
    )
    aid = deps_fixture.store.upsert_asset(
        pid, "p/x.png", "spritesheet", "h", 64, added_at=_NOW
    )
    deps_fixture.store.save_sprite_meta(
        aid,
        SpriteMeta(
            width=128,
            height=32,
            has_alpha=True,
            is_pixel_art=True,
            dominant_colors=[],
            frame_count=None,
        ),
    )
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=_NOW)
    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text and "&#127902;" not in r.text


def test_frame_badge_aria_label(deps_fixture):
    _seed_spritesheet_asset(deps_fixture.store)
    app = build_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    # aria-label="N frames" 또는 title="N frames" 로 접근성 확보
    assert 'aria-label="8 frames"' in r.text or 'title="8 frames"' in r.text
