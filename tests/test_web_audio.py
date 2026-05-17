"""M5 — 사운드 인라인 ▶ 재생 (/api/audio/{id} + /ui/audio-player/{id}) 검증."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ─── populated_deps / populated_client ────────────────────────────────


@pytest.fixture
def populated_deps(tmp_path, populated_store, fake_embedder):
    """에셋이 채워진 WebDeps — 오디오 라우트 테스트용."""
    from gah.config import AppPaths, Config
    from gah.core.labels import LabelRegistry
    from gah.core.consistency import ConsistencyScorer
    from gah.core.usage_tracker import UsageTracker
    from gah.core.search import HybridSearcher
    from gah.web.deps import WebDeps
    from gah.web.pending import PendingPickQueue

    store, _ids = populated_store
    cfg = Config()
    paths = AppPaths(
        data_dir=tmp_path,
        library_dir=tmp_path / "library",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "metadata.db",
        config_path=tmp_path / "config.toml",
        log_path=tmp_path / "logs" / "gah.log",
        lock_path=tmp_path / "gah.lock",
    )
    paths.ensure_dirs()
    registry = LabelRegistry(store)
    registry.bootstrap()
    consistency = ConsistencyScorer(store, cfg)
    usage = UsageTracker(store, cfg)
    searcher = HybridSearcher(store, fake_embedder, consistency, registry, cfg)
    pending = PendingPickQueue(max_pending=cfg.claude_pick_max_pending)
    return WebDeps(
        store=store,
        search=searcher,
        usage=usage,
        registry=registry,
        queue=None,
        config=cfg,
        paths=paths,
        pending_picks=pending,
    )


@pytest.fixture
def populated_client(populated_deps):
    with TestClient(build_app(populated_deps)) as c:
        yield c


# ─── /api/audio 에러 케이스 ────────────────────────────────────────────


def test_audio_missing_id_returns_404(client):
    """존재하지 않는 asset_id → 404."""
    r = client.get("/api/audio/99999")
    assert r.status_code == 404


def test_audio_invalid_id_returns_422(client):
    """숫자가 아닌 asset_id → 422."""
    r = client.get("/api/audio/notanumber")
    assert r.status_code == 422


def test_audio_player_fragment_missing_id_returns_404(client):
    """audio-player fragment — 미존재 id → 404."""
    r = client.get("/ui/audio-player/99999")
    assert r.status_code == 404


def test_audio_player_fragment_invalid_id_returns_422(client):
    """audio-player fragment — 숫자 아님 → 422."""
    r = client.get("/ui/audio-player/notanumber")
    assert r.status_code == 422


# ─── sprite asset 에 audio 요청 → 404 ────────────────────────────────


def test_audio_sprite_kind_returns_404(populated_client):
    """sprite asset 에 audio 요청 → 404 (sound kind 아님)."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    sprites = [a for a in store.list_assets(limit=20) if a.kind == "sprite"]
    if not sprites:
        pytest.skip("populated_client 에 sprite asset 없음")
    asset_id = sprites[0].id
    r = populated_client.get(f"/api/audio/{asset_id}")
    assert r.status_code == 404


def test_audio_player_sprite_kind_returns_404(populated_client):
    """sprite asset 에 audio-player fragment 요청 → 404."""
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    sprites = [a for a in store.list_assets(limit=20) if a.kind == "sprite"]
    if not sprites:
        pytest.skip("populated_client 에 sprite asset 없음")
    asset_id = sprites[0].id
    r = populated_client.get(f"/ui/audio-player/{asset_id}")
    assert r.status_code == 404


# ─── sound asset → audio-player fragment HTML ─────────────────────────


def test_audio_player_fragment_html_with_existing_sound(populated_client, tmp_path):
    """sound asset audio-player fragment — sound kind → 200 + <audio> 태그 포함."""
    from pathlib import Path
    import numpy as np
    import soundfile as sf
    from gah.core.store import Store

    store: Store = populated_client.app.state.deps.store
    sounds = [a for a in store.list_assets(limit=20) if a.kind == "sound"]
    if not sounds:
        pytest.skip("populated_client 에 sound asset 없음")

    # 실제 파일이 존재하는 sound 를 찾기 위해 asset path 를 실제 파일로 업데이트
    # (populated_store 의 path 는 가상 경로이므로 audio fragment 만 확인)
    asset_id = sounds[0].id

    r = populated_client.get(f"/ui/audio-player/{asset_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<audio" in r.text
    assert f"/api/audio/{asset_id}" in r.text
