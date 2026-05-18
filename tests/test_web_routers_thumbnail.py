"""M5 — /api/thumbnail/{asset_id} (lazy 256×256 PNG) 검증."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


def test_thumbnail_unknown_id_returns_404(client):
    """존재하지 않는 asset_id → 404."""
    assert client.get("/api/thumbnail/99999").status_code == 404


def test_thumbnail_zero_id(client):
    """asset_id=0 (잘못된 id) → 404 또는 422."""
    assert client.get("/api/thumbnail/0").status_code in (404, 422)


def test_thumbnail_negative_id_returns_404_or_422(client):
    """음수 asset_id → FastAPI path 변환 오류 또는 404."""
    assert client.get("/api/thumbnail/-1").status_code in (404, 422)


def test_thumbnail_string_id_returns_422(client):
    """asset_id 가 정수 아니면 422 Pydantic 검증."""
    assert client.get("/api/thumbnail/notanumber").status_code == 422


def test_thumbnail_sprite_asset_returns_png(client, deps_fixture, tmp_path):
    """실제 sprite 자산 등록 후 200 + image/png."""
    from PIL import Image
    import time, json

    # 64x64 PNG 생성
    p = deps_fixture.paths.library_dir / "test_pack" / "hero.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(p)

    now = int(time.time())
    store = deps_fixture.store
    with store.write_lock:
        store.conn.execute(
            "INSERT INTO packs (name, display_name, vendor, enabled, added_at)"
            " VALUES (?,?,?,1,?)",
            ("test_pack", "Test Pack", "test", now),
        )
        pack_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
            "  added_at, analysis_state)"
            " VALUES (?,?,?,?,?,?,?)",
            (pack_id, str(p), "sprite", "abc123", 1024, now, "ok"),
        )
        asset_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO sprite_meta (asset_id, width, height, has_alpha,"
            "  is_pixel_art, dominant_colors)"
            " VALUES (?,?,?,?,?,?)",
            (asset_id, 64, 64, 1, 0, json.dumps([])),
        )
        store.conn.commit()

    r = client.get(f"/api/thumbnail/{asset_id}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # PNG 헤더 확인
    assert r.content[:4] == b"\x89PNG"


def test_thumbnail_etag_contains_asset_id(client, deps_fixture):
    """ETag 헤더가 '{asset_id}:{mtime_ns}' 형식이어야 충돌 방지 보장."""
    from PIL import Image
    import time, json

    p = deps_fixture.paths.library_dir / "etag_pack" / "shield.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(p)

    now = int(time.time())
    store = deps_fixture.store
    with store.write_lock:
        store.conn.execute(
            "INSERT INTO packs (name, display_name, vendor, enabled, added_at)"
            " VALUES (?,?,?,1,?)",
            ("etag_pack", "ETag Pack", "test", now),
        )
        pack_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
            "  added_at, analysis_state)"
            " VALUES (?,?,?,?,?,?,?)",
            (pack_id, str(p), "sprite", "etag999", 512, now, "ok"),
        )
        asset_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.execute(
            "INSERT INTO sprite_meta (asset_id, width, height, has_alpha,"
            "  is_pixel_art, dominant_colors)"
            " VALUES (?,?,?,?,?,?)",
            (asset_id, 32, 32, 1, 0, json.dumps([])),
        )
        store.conn.commit()

    r = client.get(f"/api/thumbnail/{asset_id}")
    assert r.status_code == 200
    etag = r.headers.get("etag", "")
    # ETag 형식: "{asset_id}:{mtime_ns}"
    assert etag.startswith(f'"{asset_id}:'), (
        f"ETag 이 asset_id prefix 를 포함해야 함: {etag!r}"
    )


def test_thumbnail_sound_returns_404(client, deps_fixture):
    """sound 자산 → 썸네일 없음 → 404."""
    import time

    now = int(time.time())
    store = deps_fixture.store
    with store.write_lock:
        store.conn.execute(
            "INSERT OR IGNORE INTO packs (name, display_name, vendor, enabled, added_at)"
            " VALUES (?,?,?,1,?)",
            ("snd_pack", "Sound Pack", "test", now),
        )
        pack_id = store.conn.execute(
            "SELECT id FROM packs WHERE name='snd_pack'"
        ).fetchone()[0]
        store.conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
            "  added_at, analysis_state)"
            " VALUES (?,?,?,?,?,?,?)",
            (pack_id, "/lib/snd_pack/jump.wav", "sound", "def456", 512, now, "ok"),
        )
        sound_id = store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        store.conn.commit()

    r = client.get(f"/api/thumbnail/{sound_id}")
    assert r.status_code == 404
