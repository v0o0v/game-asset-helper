"""M11 Phase 6 Task 6.3 — find_asset 응답에 backend_used 필드.

per-asset 분석에 사용된 backend 이름을 검색 결과에 노출 — Claude 가 검색
결과를 활용하거나 사용자가 검색 카드 배지로 확인 가능.

shape:
    backend_used = {"image": "gemini" | None, "audio": "ollama" | None, "embed": "openai" | None}

legacy row (M11 마이그레이션 직후, AnalysisQueue write path 후속 patch 전)
는 모든 필드 None.
"""

from __future__ import annotations


def _find(deps, **kwargs):
    from assetcache.mcp.models import FindAssetRequest
    from assetcache.mcp.tools import tool_find_asset

    return tool_find_asset(deps, FindAssetRequest(**kwargs))


def test_find_asset_results_include_backend_used_field(
    mcp_tool_deps, populated_store
):
    """모든 result dict 에 backend_used 키 존재 (None 일 수도 있지만 있어야)."""
    deps = mcp_tool_deps()
    res = _find(deps, query="hero", count=5)
    assert len(res.results) > 0
    for r in res.results:
        assert "backend_used" in r
        bu = r["backend_used"]
        assert "image" in bu
        assert "audio" in bu
        assert "embed" in bu


def test_find_asset_legacy_rows_have_null_backend(mcp_tool_deps, populated_store):
    """populated_store 의 모든 asset 은 mark_asset_backends 호출 전 → 모두 None."""
    deps = mcp_tool_deps()
    res = _find(deps, query="hero", count=5)
    for r in res.results:
        bu = r["backend_used"]
        assert bu["image"] is None
        assert bu["audio"] is None
        assert bu["embed"] is None


def test_find_asset_returns_backend_after_mark(mcp_tool_deps, populated_store):
    """asset 에 mark_asset_backends 호출 후 find_asset 응답에 backend 이름 표시."""
    store, ids = populated_store
    deps = mcp_tool_deps()
    # hero.png 를 gemini(image) + openai(embed) 로 분석한 것으로 마킹
    store.mark_asset_backends(ids["hero"], image="gemini", embed="openai")

    res = _find(deps, query="hero", count=5)
    hero_results = [r for r in res.results if r["asset_id"] == ids["hero"]]
    assert len(hero_results) == 1
    bu = hero_results[0]["backend_used"]
    assert bu["image"] == "gemini"
    assert bu["audio"] is None
    assert bu["embed"] == "openai"


def test_find_asset_multiple_backends_per_modality(mcp_tool_deps, populated_store):
    """여러 asset 에 다른 backend 마킹 — 결과별로 정확히 반영."""
    store, ids = populated_store
    deps = mcp_tool_deps()
    store.mark_asset_backends(ids["hero"], image="gemini")
    store.mark_asset_backends(ids["coin"], image="claude")
    store.mark_asset_backends(ids["bgm_loop"], audio="ollama", embed="openai")

    res = _find(deps, query="anything", count=10)
    by_id = {r["asset_id"]: r for r in res.results}
    if ids["hero"] in by_id:
        assert by_id[ids["hero"]]["backend_used"]["image"] == "gemini"
    if ids["coin"] in by_id:
        assert by_id[ids["coin"]]["backend_used"]["image"] == "claude"
    if ids["bgm_loop"] in by_id:
        bgm_bu = by_id[ids["bgm_loop"]]["backend_used"]
        assert bgm_bu["audio"] == "ollama"
        assert bgm_bu["embed"] == "openai"
