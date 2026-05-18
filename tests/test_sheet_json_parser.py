"""M6 — sheet JSON 파서 (Aseprite Array/Hash + TexturePacker)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gah.core.sheet.json_parser import parse
from gah.core.sheet.types import AsepriteAtlas, TexturePackerAtlas

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def test_aseprite_array_8_frames():
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert isinstance(atlas, AsepriteAtlas)
    assert len(atlas.frames) == 8
    assert atlas.frames[0].x == 0 and atlas.frames[0].w == 32
    assert atlas.frames[7].x == 224


def test_aseprite_array_frame_tags():
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert len(atlas.tags) == 1
    walk = atlas.tags[0]
    assert walk.name == "walk"
    assert walk.start_frame == 0
    assert walk.end_frame == 7
    assert walk.source == "json_tag"


def test_aseprite_array_duration_to_fps_average():
    # 4×100ms + 4×80ms → 평균 90ms → 1000/90 ≈ 11.1 → round = 11
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert atlas.tags[0].fps_hint == 11


def test_aseprite_hash_natural_sort():
    # 키 자연 정렬: hero 0..hero 10 — 사전 정렬 시 'hero 10' 이 'hero 2' 앞으로 가는 함정 회피
    atlas = parse(FIXTURES / "hero_walk_aseprite_hash.json")
    assert isinstance(atlas, AsepriteAtlas)
    assert len(atlas.frames) == 11
    # 자연 정렬이면 인덱스 0 = "hero 0", 1 = "hero 1", ..., 10 = "hero 10"
    assert atlas.frames[0].x == 0
    assert atlas.frames[1].x == 32
    assert atlas.frames[10].x == 320  # 마지막이 'hero 10' 이어야 함


def test_aseprite_hash_no_frame_tags_returns_empty_tags():
    atlas = parse(FIXTURES / "hero_walk_aseprite_hash.json")
    assert atlas.tags == []


def test_texture_packer_4_frames():
    atlas = parse(FIXTURES / "icons_texturepacker.json")
    assert isinstance(atlas, TexturePackerAtlas)
    assert len(atlas.frames) == 4
    assert atlas.frames[0].name == "sword.png"


def test_unknown_format_returns_none(tmp_path):
    p = tmp_path / "unknown.json"
    p.write_text(json.dumps({"unrelated": True}))
    assert parse(p) is None


def test_empty_frames_returns_none(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"meta": {"app": "Aseprite"}, "frames": []}))
    assert parse(p) is None


def test_invalid_json_returns_none(tmp_path, caplog):
    p = tmp_path / "broken.json"
    p.write_text("{ not valid json")
    assert parse(p) is None
    assert any("json" in rec.message.lower() for rec in caplog.records)


def test_aseprite_meta_app_detection(tmp_path):
    # meta.app 이 'Aseprite' 시작이면 Aseprite 분기
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [{"filename":"a","frame":{"x":0,"y":0,"w":8,"h":8},"duration":100}],
        "meta": {"app": "Aseprite v1.4 (custom)"}
    }))
    atlas = parse(p)
    assert isinstance(atlas, AsepriteAtlas)


def test_duration_zero_fps_fallback_12(tmp_path):
    # 모든 duration=0 이면 fps_hint=12 (기본)
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [
            {"filename":"a","frame":{"x":0,"y":0,"w":8,"h":8},"duration":0},
            {"filename":"b","frame":{"x":8,"y":0,"w":8,"h":8},"duration":0},
        ],
        "meta": {"app": "Aseprite", "frameTags":[{"name":"x","from":0,"to":1}]}
    }))
    atlas = parse(p)
    assert atlas.tags[0].fps_hint == 12


def test_texture_packer_app_detection(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [{"filename":"a.png","frame":{"x":0,"y":0,"w":8,"h":8}}],
        "meta": {"app": "https://www.codeandweb.com/texturepacker"}
    }))
    atlas = parse(p)
    assert isinstance(atlas, TexturePackerAtlas)
