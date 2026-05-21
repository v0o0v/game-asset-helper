"""M11.3 Phase 3 — BatchPoller._try_enrich_with_sheet sprite_meta cache.

옵션 B — DB cross-sweep cache.  sprite_meta 에 시트 정보 (animations_json 또는
frame_w) 가 이미 저장돼 있으면 (Phase 1 의 classify_image_assets 가 채움)
``detect_sheet`` 호출 우회 + animations_json 으로 AnimationSpec 재구성 + 같은
animation 라벨 반환.

cache hit 조건: ``existing.animations_json`` is truthy OR ``existing.frame_w`` is
not None.  둘 다 비어 있으면 일반 sprite — legacy detect_sheet path.
"""

from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.poller import BatchPoller
from assetcache.core.store import SpriteMeta


def _make_poller(*, library_dir, sprite_meta=None):
    store = MagicMock()
    store.list_active_batch_jobs.return_value = []
    store.get_sprite_meta.return_value = sprite_meta
    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 0.05
    p = BatchPoller(
        store=store,
        chain_registry=MagicMock(),
        analysis_queue=MagicMock(),
        cfg=cfg,
        registry=MagicMock(),
        library_dir=library_dir,
    )
    return p, store


def _enriched_meta(*, animations_json=None, frame_w=32):
    return SpriteMeta(
        width=128, height=32, has_alpha=True,
        is_pixel_art=True, dominant_colors=["#ff0000"],
        frame_w=frame_w, frame_h=32, frame_count=4,
        animation_tags=list(animations_json.keys()) if animations_json else None,
        animations_json=animations_json,
    )


def test_cache_hit_with_animations_json_skips_detect_sheet(tmp_path, monkeypatch):
    """sprite_meta.animations_json 있으면 detect_sheet 우회 + 라벨 재구성."""
    animations_json = {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
        "idle": {"start_frame": 4, "end_frame": 7, "fps_hint": 12, "source": "json_tag"},
    }
    existing = _enriched_meta(animations_json=animations_json)
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=existing)

    import assetcache.core.batch.poller as poller_mod

    def fake_detect(_path):
        raise AssertionError("detect_sheet should not be called on cache hit")

    monkeypatch.setattr(poller_mod, "detect_sheet", fake_detect)

    asset = MagicMock(id=400, path="pack/hero.png")
    base_meta = MagicMock()  # overridden by cache
    result = p._try_enrich_with_sheet(asset, base_meta)

    assert result is not None
    enriched, anim_labels = result
    assert enriched is existing
    assert {l.label for l in anim_labels} == {"walk", "idle"}
    for label in anim_labels:
        assert label.axis == "animation"
        assert label.weight == "primary"
        assert label.score == 1.0


def test_cache_hit_with_frame_w_only_returns_no_anim_labels(tmp_path, monkeypatch):
    """grid-only 시트 (animations_json=None, frame_w 채워짐) 도 cache hit, 라벨은 빈 리스트."""
    existing = _enriched_meta(animations_json=None, frame_w=32)
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=existing)

    import assetcache.core.batch.poller as poller_mod

    monkeypatch.setattr(
        poller_mod, "detect_sheet",
        lambda _: pytest.fail("detect_sheet should not be called"),
    )

    asset = MagicMock(id=401, path="pack/grid.png")
    result = p._try_enrich_with_sheet(asset, MagicMock())

    assert result is not None
    enriched, anim_labels = result
    assert enriched is existing
    assert anim_labels == []


def test_cache_miss_when_sprite_meta_lacks_sheet_fields(tmp_path, monkeypatch):
    """sprite_meta 있지만 frame_w=None + animations_json=None → legacy detect path 실행."""
    sprite_only = SpriteMeta(
        width=32, height=32, has_alpha=True,
        is_pixel_art=False, dominant_colors=[],
        frame_w=None, frame_h=None, frame_count=None,
        animation_tags=None, animations_json=None,
    )
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=sprite_only)

    called = {"count": 0}
    import assetcache.core.batch.poller as poller_mod

    def fake_detect(_, *, alpha_color_weight=0.5):
        called["count"] += 1
        return None

    monkeypatch.setattr(poller_mod, "detect_sheet", fake_detect)

    (tmp_path / "pack").mkdir(parents=True)
    (tmp_path / "pack/x.png").touch()

    asset = MagicMock(id=402, path="pack/x.png")
    result = p._try_enrich_with_sheet(asset, MagicMock())

    assert called["count"] == 1
    assert result is None  # detect_sheet miss → no enrichment


def test_cache_miss_when_get_sprite_meta_returns_none(tmp_path, monkeypatch):
    """sprite_meta=None (저장 안 됨) → detect_sheet 호출 (legacy)."""
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=None)

    called = {"count": 0}
    import assetcache.core.batch.poller as poller_mod

    def fake_detect(_, *, alpha_color_weight=0.5):
        called["count"] += 1
        return None

    monkeypatch.setattr(poller_mod, "detect_sheet", fake_detect)

    (tmp_path / "pack").mkdir(parents=True)
    (tmp_path / "pack/x.png").touch()

    asset = MagicMock(id=403, path="pack/x.png")
    p._try_enrich_with_sheet(asset, MagicMock())

    assert called["count"] == 1


def test_cache_hit_labels_equal_to_detection_to_animation_labels(tmp_path, monkeypatch):
    """캐시 hit 시 재구성된 라벨이 detection_to_animation_labels 출력과 동등."""
    animations_json = {
        "attack": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
    }
    existing = _enriched_meta(animations_json=animations_json)
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=existing)

    import assetcache.core.batch.poller as poller_mod

    monkeypatch.setattr(
        poller_mod, "detect_sheet",
        lambda _: pytest.fail("no detect"),
    )

    asset = MagicMock(id=404, path="pack/hero.png")
    result = p._try_enrich_with_sheet(asset, MagicMock())

    assert result is not None
    _, anim_labels = result
    assert len(anim_labels) == 1
    label = anim_labels[0]
    assert label.axis == "animation"
    assert label.label == "attack"
    assert label.score == 1.0
    assert label.source == "gemma"
    assert label.weight == "primary"


def test_cache_hit_get_sprite_meta_called_once_with_asset_id(tmp_path, monkeypatch):
    """get_sprite_meta(asset.id) 가 정확히 1회 호출됨."""
    existing = _enriched_meta(animations_json={
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
    })
    p, store = _make_poller(library_dir=tmp_path, sprite_meta=existing)

    import assetcache.core.batch.poller as poller_mod
    monkeypatch.setattr(
        poller_mod, "detect_sheet",
        lambda _: pytest.fail("no detect"),
    )

    asset = MagicMock(id=999, path="pack/x.png")
    p._try_enrich_with_sheet(asset, MagicMock())

    store.get_sprite_meta.assert_called_once_with(999)
