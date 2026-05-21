"""Phase 1 task 1.5 — AnalysisQueue._persist 가 backend_used 를 store 에 마킹."""

from unittest.mock import MagicMock

from assetcache.core.searchable import SearchableTexts


def _make_result(**overrides):
    base = dict(
        backend_used={},
        sprite_meta=None,
        sound_meta=None,
        labels=[],
        embedding_dim=0,
        embedding_vector=b"",
        embedding_model="",
        searchable=SearchableTexts(for_fts="", for_embed=""),
        kind="sprite",
        state="done",
        error=None,
        description="",
    )
    base.update(overrides)
    r = MagicMock()
    for k, v in base.items():
        setattr(r, k, v)
    return r


def test_persist_calls_mark_asset_backends_when_backend_used_present():
    from assetcache.core.analysis_queue import AnalysisQueue

    store = MagicMock()
    q = AnalysisQueue(
        store=store,
        sprite=MagicMock(),
        spritesheet=MagicMock(),
        sound=MagicMock(),
    )
    result = _make_result(backend_used={"image": "gemini", "embed": "ollama"})
    q._persist(123, result)
    store.mark_asset_backends.assert_called_once_with(
        123, image="gemini", audio=None, embed="ollama",
    )


def test_persist_skips_mark_asset_backends_when_empty():
    from assetcache.core.analysis_queue import AnalysisQueue

    store = MagicMock()
    q = AnalysisQueue(
        store=store,
        sprite=MagicMock(),
        spritesheet=MagicMock(),
        sound=MagicMock(),
    )
    result = _make_result(backend_used={})
    q._persist(123, result)
    store.mark_asset_backends.assert_not_called()
