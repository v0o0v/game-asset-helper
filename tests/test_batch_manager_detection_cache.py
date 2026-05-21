"""M11.3 Phase 2 — BatchManager._detection_cache + classify cache 전달.

옵션 C — sweep 메모리 캐시.  BatchManager 인스턴스 lifetime 동안 유지되며
같은 sweep 안의 ``chat_image`` classify ↔ ``chat_spritesheet`` classify 가
``detect_sheet`` 결과를 공유한다.  최대 1024 entries — 초과 시 가장 오래된
entry 부터 evict.

cache 키는 ``asset_id`` (int).  값은 ``SheetDetection`` 또는 ``None``.
"""

import collections
from unittest.mock import MagicMock

from assetcache.core.batch.manager import BatchManager


def _make_manager(*, library_dir=None, threshold=1):
    store = MagicMock()
    chain = MagicMock()
    aq = MagicMock()
    cfg = MagicMock()
    cfg.batch.toggle = "auto"
    cfg.batch.threshold = threshold
    cfg.batch.expiry_grace_seconds = 86400
    return BatchManager(
        store=store, chain_registry=chain, analysis_queue=aq,
        cfg=cfg, library_dir=library_dir,
    ), store, chain, aq


def _gemini_backend():
    b = MagicMock()
    b.info.name = "gemini"
    b.supports_batch.return_value = True
    b.batch_chat.return_value = "batches/fake"
    return b


def _row(*, id: int, path: str = "pack/x.png"):
    r = MagicMock()
    r.id = id
    r.path = path
    r.kind = "sprite"
    return r


def test_detection_cache_initialized_as_ordered_dict_empty():
    """BatchManager 인스턴스화 시 _detection_cache 가 OrderedDict, empty."""
    mgr, *_ = _make_manager()
    assert isinstance(mgr._detection_cache, collections.OrderedDict)
    assert len(mgr._detection_cache) == 0


def test_detection_cache_evicts_oldest_at_max_size():
    """1024 entries 채운 후 +1 insert → 가장 오래된 entry 제거 (LRU)."""
    mgr, *_ = _make_manager()
    for i in range(1024):
        mgr._detection_cache[i] = None
    assert len(mgr._detection_cache) == 1024

    mgr._detection_cache[9999] = None
    assert len(mgr._detection_cache) == 1024
    assert 0 not in mgr._detection_cache  # 가장 오래된 entry evict
    assert 9999 in mgr._detection_cache


def test_detection_cache_reinsertion_moves_to_end(tmp_path):
    """기존 key 에 재할당 시 가장 최근 사용으로 이동 — eviction 면제."""
    mgr, *_ = _make_manager()
    for i in range(1024):
        mgr._detection_cache[i] = None
    # 0 을 다시 set → 끝으로 이동
    mgr._detection_cache[0] = None
    # 새 entry insert → 0 이 아닌 1 이 evict 돼야
    mgr._detection_cache[9999] = None
    assert 0 in mgr._detection_cache
    assert 1 not in mgr._detection_cache


def test_chat_image_passes_self_cache_to_classify(tmp_path, monkeypatch):
    """try_submit('chat_image') → classify_image_assets(cache=mgr._detection_cache)."""
    captured: dict = {}

    def spy(rows, *, library_dir, store, cache=None, save_sprite_meta=True,
            alpha_color_weight=0.5):
        captured["cache"] = cache
        captured["save_sprite_meta"] = save_sprite_meta
        # all-sheets short-circuit → if not rows: return None
        return [], []

    monkeypatch.setattr(
        "assetcache.core.batch.sheet_classifier.classify_image_assets",
        spy,
    )

    mgr, store, chain, aq = _make_manager(library_dir=tmp_path)
    store.count_pending_by_modality.return_value = 1
    store.fetch_pending_by_modality.return_value = [_row(id=1)]
    chain.first_backend.return_value = _gemini_backend()

    out = mgr.try_submit("chat_image")
    assert out is None  # all-sheets short-circuit
    assert "cache" in captured
    assert captured["cache"] is mgr._detection_cache


def test_chat_spritesheet_passes_self_cache_to_classify(tmp_path, monkeypatch):
    """try_submit('chat_spritesheet') → classify_image_assets(cache=mgr._detection_cache)."""
    captured: dict = {}

    def spy(rows, *, library_dir, store, cache=None, save_sprite_meta=True,
            alpha_color_weight=0.5):
        captured["cache"] = cache
        return [], []  # no hits → "if not sheet_results: return None"

    monkeypatch.setattr(
        "assetcache.core.batch.sheet_classifier.classify_image_assets",
        spy,
    )

    mgr, store, chain, aq = _make_manager(library_dir=tmp_path)
    store.count_pending_by_modality.return_value = 1
    store.fetch_pending_by_modality.return_value = [_row(id=2)]
    chain.first_backend.return_value = _gemini_backend()

    out = mgr.try_submit("chat_spritesheet")
    assert out is None
    assert "cache" in captured
    assert captured["cache"] is mgr._detection_cache


def test_consecutive_submissions_share_same_cache_instance(tmp_path, monkeypatch):
    """두 modality 연속 호출 → 같은 _detection_cache 객체 재사용."""
    captured_caches: list = []

    def spy(rows, *, library_dir, store, cache=None, save_sprite_meta=True,
            alpha_color_weight=0.5):
        captured_caches.append(cache)
        return [], []

    monkeypatch.setattr(
        "assetcache.core.batch.sheet_classifier.classify_image_assets",
        spy,
    )

    mgr, store, chain, aq = _make_manager(library_dir=tmp_path)
    store.count_pending_by_modality.return_value = 1
    store.fetch_pending_by_modality.return_value = [_row(id=3)]
    chain.first_backend.return_value = _gemini_backend()

    mgr.try_submit("chat_image")
    mgr.try_submit("chat_spritesheet")

    assert len(captured_caches) == 2
    assert captured_caches[0] is captured_caches[1]
    assert captured_caches[0] is mgr._detection_cache
