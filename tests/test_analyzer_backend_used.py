"""Phase 1 task 1.5 — AnalyzerResult.backend_used 필드.

backend_used 는 dict[str, str] — chain.chat() 의 두번째 반환값 + embedding encoder backend.
"""

from assetcache.core.analyzer.base import AnalyzerResult
from assetcache.core.searchable import SearchableTexts


def _make_searchable() -> SearchableTexts:
    return SearchableTexts(for_fts="", for_embed="")


def test_analyzer_result_backend_used_default_empty():
    """기본값 — empty dict."""
    r = AnalyzerResult(
        labels=[],
        searchable=_make_searchable(),
        embedding_vector=b"",
        embedding_dim=0,
        embedding_model="",
        sprite_meta=None,
        sound_meta=None,
        kind="sprite",
        state="pending",
        error=None,
        description="",
    )
    assert r.backend_used == {}


def test_analyzer_result_with_backend_used():
    r = AnalyzerResult(
        labels=[],
        searchable=_make_searchable(),
        embedding_vector=b"",
        embedding_dim=0,
        embedding_model="",
        sprite_meta=None,
        sound_meta=None,
        kind="sprite",
        state="pending",
        error=None,
        description="",
        backend_used={"image": "gemini", "embed": "ollama"},
    )
    assert r.backend_used == {"image": "gemini", "embed": "ollama"}
