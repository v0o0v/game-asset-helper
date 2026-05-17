"""M5 bugfix 회귀 테스트 — assets.path 상대경로 → 절대경로 해석.

실제 버그: assets.path 는 library_root 기준 상대경로(예: kenney_m2_verify/hello.jpg)
이지만 thumbnail/audio endpoint 가 Path(asset.path) 를 절대경로로 취급해
FileNotFoundError 가 발생했다.

수정: WebDeps.library_root + resolve_asset_path() 헬퍼로 절대경로 조합.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app
from gah.web.deps import resolve_asset_path


# ── resolve_asset_path 단위 테스트 ─────────────────────────────────────


def test_resolve_asset_path_uses_library_root(deps_fixture, tmp_path):
    """library_root 가 설정된 경우 root / rel_path 로 절대경로 생성."""
    from gah.config import AppPaths, Config
    from gah.web.deps import WebDeps

    root = tmp_path / "my_library"
    deps_with_root = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=None,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        library_root=root,
    )
    result = resolve_asset_path(deps_with_root, "pack_a/hero.png")
    assert result == root / "pack_a" / "hero.png"


def test_resolve_asset_path_fallback_to_paths_library_dir(deps_fixture):
    """library_root=None 이면 paths.library_dir 로 폴백."""
    from gah.config import AppPaths, Config
    from gah.web.deps import WebDeps

    deps_no_root = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=None,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        library_root=None,
    )
    result = resolve_asset_path(deps_no_root, "pack_a/hero.png")
    assert result == deps_fixture.paths.library_dir / "pack_a" / "hero.png"


# ── /api/thumbnail HTTP 통합 테스트 ────────────────────────────────────


@pytest.fixture
def thumb_client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


def test_thumbnail_endpoint_resolves_relative_path(deps_fixture, thumb_client):
    """assets.path 가 상대경로일 때 thumbnail endpoint 가 200 + PNG 를 반환해야 한다.

    이 테스트는 버그 재현 → 수정 확인용 핵심 케이스다.
    library_root / rel_path 로 실제 파일을 읽어야 한다.
    """
    from PIL import Image

    # 실제 파일을 library_root 아래에 생성
    lib = deps_fixture.library_root or deps_fixture.paths.library_dir
    rel = "bugfix_pack/sprite.png"
    img_path = lib / rel
    img_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 32), (0, 128, 255, 255)).save(img_path)

    now = int(time.time())
    store = deps_fixture.store
    with store.write_lock:
        store.conn.execute(
            "INSERT INTO packs (name, display_name, vendor, enabled, added_at)"
            " VALUES (?,?,?,1,?)",
            ("bugfix_pack", "Bugfix Pack", "test", now),
        )
        pack_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # 핵심: path 에 상대경로 저장 (버그 재현 조건)
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
            "  added_at, analysis_state)"
            " VALUES (?,?,?,?,?,?,?)",
            (pack_id, rel, "sprite", "bugfix_hash", 512, now, "ok"),
        )
        asset_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO sprite_meta (asset_id, width, height, has_alpha,"
            "  is_pixel_art, dominant_colors)"
            " VALUES (?,?,?,?,?,?)",
            (asset_id, 32, 32, 1, 0, json.dumps([])),
        )
        store.conn.commit()

    r = thumb_client.get(f"/api/thumbnail/{asset_id}")
    assert r.status_code == 200, (
        f"상대경로 asset row 에 대해 200 이어야 함. 실제: {r.status_code}\n{r.text}"
    )
    assert r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG", "응답 본문이 PNG 헤더로 시작해야 함"


def test_thumbnail_endpoint_none_library_root_falls_back(deps_fixture):
    """library_root=None 인 WebDeps 에서도 paths.library_dir 폴백이 동작한다."""
    from PIL import Image
    from gah.web.deps import WebDeps

    deps_no_root = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=None,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        library_root=None,
    )

    lib = deps_no_root.paths.library_dir
    rel = "fallback_pack/tile.png"
    img_path = lib / rel
    img_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (200, 100, 50)).save(img_path)

    now = int(time.time())
    store = deps_no_root.store
    with store.write_lock:
        store.conn.execute(
            "INSERT OR IGNORE INTO packs (name, display_name, vendor, enabled, added_at)"
            " VALUES (?,?,?,1,?)",
            ("fallback_pack", "Fallback Pack", "test", now),
        )
        pack_id = store.conn.execute(
            "SELECT id FROM packs WHERE name='fallback_pack'"
        ).fetchone()[0]
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
            "  added_at, analysis_state)"
            " VALUES (?,?,?,?,?,?,?)",
            (pack_id, rel, "sprite", "fallback_hash", 256, now, "ok"),
        )
        asset_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO sprite_meta (asset_id, width, height, has_alpha,"
            "  is_pixel_art, dominant_colors)"
            " VALUES (?,?,?,?,?,?)",
            (asset_id, 16, 16, 0, 0, json.dumps([])),
        )
        store.conn.commit()

    with TestClient(build_app(deps_no_root)) as c:
        r = c.get(f"/api/thumbnail/{asset_id}")
    assert r.status_code == 200, f"library_root=None 폴백 실패: {r.status_code}\n{r.text}"
    assert r.content[:4] == b"\x89PNG"
