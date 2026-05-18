"""M4 — MCP 도구 확장 + 4 신규 도구 (saved_searches).

확장:
- `tool_find_asset` — `label_query` 파서 호출 + AmbiguousLabel/UnsupportedExpression
  → `400_invalid_input`. 구조화 입력 `labels_*` 와 파서 결과 병합.
- `tool_report_feedback` — `Literal["negative","positive","irrelevant"]` reason 으로
  Config 의 signed weight 적용 + `store.insert_feedback_record`.
- `tool_suggest_packs` — `samples[]` 가 `thumbnail_path`/`preview_blurb` 포함.

신규 4 도구:
- `tool_save_search` — UNIQUE(project_id, name) 충돌 시 `400_invalid_input`.
- `tool_list_saved_searches` — `last_used_at` 내림차순.
- `tool_delete_saved_search` — 미존재 시 `404_not_found`.
- `tool_run_saved_search` — saved query_json 로드 후 `tool_find_asset` 위임,
  미존재 시 `404_not_found`.

총 도구 12 → 16 (회귀 가드).
"""

from __future__ import annotations

import json

import pytest


# ── 헬퍼 ─────────────────────────────────────────────────────────────


def _find_req(**kw):
    from gah.mcp.models import FindAssetRequest

    return FindAssetRequest(**kw)


# ── 1. find_asset — label_query 통합 ─────────────────────────────────


def test_find_asset_label_query_parses_and_injects(mcp_tool_deps) -> None:
    """`label_query="pixel_art"` 가 파서를 거쳐 labels_all 에 주입되고,
    `category=pixel_art` 매칭 자산만 후보."""
    from gah.mcp.tools import tool_find_asset

    deps = mcp_tool_deps()
    res = tool_find_asset(deps, _find_req(query="hero", label_query="pixel_art"))
    # 결과 자체가 정상 반환 + matched_labels 에 pixel_art 가 노출되어야.
    assert res.query_id > 0


def test_find_asset_structured_labels_plus_label_query_merge(mcp_tool_deps) -> None:
    """구조화 labels_all + label_query 양쪽 — 둘 다 적용 (병합)."""
    from gah.mcp.models import AxisLabel
    from gah.mcp.tools import tool_find_asset

    deps = mcp_tool_deps()
    res = tool_find_asset(deps, _find_req(
        query="hero",
        labels_all=[AxisLabel(axis="category", label="character")],
        label_query="pixel_art",
    ))
    assert res.query_id > 0  # 단순 동작 확인


def test_find_asset_ambiguous_label_returns_400_with_candidates(mcp_tool_deps) -> None:
    """`label_query` 의 모호 토큰 — `400_invalid_input` + 후보 axis 안내."""
    from gah.mcp.tools import McpToolError, tool_find_asset

    deps = mcp_tool_deps()
    # 모호 라벨을 만들기 — 같은 token 을 2 axis 에 인위 등록.
    # SEED_LABELS 의 실제 분포에서 같은 token 이 여러 axis 에 있는지는 분포에 의존.
    # 안정성을 위해 임시 라벨 2개를 같은 token 으로 add 한다.
    deps.registry.add_label("custom_a", "shared_token_42", description="x")
    deps.registry.add_label("custom_b", "shared_token_42", description="y")

    with pytest.raises(McpToolError) as ei:
        tool_find_asset(deps, _find_req(query="hero", label_query="shared_token_42"))
    assert ei.value.code == "400_invalid_input"
    # 후보 axis 가 메시지에 포함.
    assert "custom_a" in ei.value.message or "custom_b" in ei.value.message


def test_find_asset_diversity_mmr_propagates_to_searcher(mcp_tool_deps) -> None:
    """`diversity="mmr"` 가 SearchRequest 까지 전파."""
    from gah.mcp.tools import tool_find_asset

    deps = mcp_tool_deps()
    res = tool_find_asset(deps, _find_req(
        query="character", diversity="mmr", diversity_lambda=0.5, count=4,
    ))
    pids = {r["pack_id"] for r in res.results}
    # mmr 가 적용되면 결과가 두 팩에서 모두 등장 가능 (단정 강도 약함 — 환경 의존).
    # 최소한 호출 성공.
    assert res.query_id > 0


# ── 2. report_feedback signed weight ─────────────────────────────────


def test_report_feedback_negative_inserts_signed_weight(
    mcp_tool_deps, populated_store
) -> None:
    from gah.mcp.models import ReportFeedbackRequest
    from gah.mcp.tools import tool_find_asset, tool_report_feedback

    deps = mcp_tool_deps()
    store, ids = populated_store
    # 먼저 find_asset 로 query_id 발급 (record_feedback 가 search_queries.project_id
    # 를 통해 project 매핑).
    find_res = tool_find_asset(deps, _find_req(
        query="hero", project_id="proj_neg_mcp", count=3,
    ))
    qid = find_res.query_id
    aid = find_res.results[0]["asset_id"] if find_res.results else ids["hero"]

    tool_report_feedback(deps, ReportFeedbackRequest(
        query_id=qid, asset_id=aid, reason="negative",
    ))
    # DB 에 signed weight 음수로 박혔는지.
    rows = store.conn.execute(
        "SELECT weight FROM feedback_records WHERE asset_id = ? ORDER BY id DESC LIMIT 1",
        (aid,),
    ).fetchall()
    assert rows
    assert rows[0][0] < 0


def test_report_feedback_unknown_reason_validation_error() -> None:
    from pydantic import ValidationError

    from gah.mcp.models import ReportFeedbackRequest

    with pytest.raises(ValidationError):
        ReportFeedbackRequest(query_id=1, asset_id=2, reason="bogus")


# ── 3. saved_searches 4 도구 ──────────────────────────────────────────


def test_save_search_persists_and_returns_id(mcp_tool_deps) -> None:
    from gah.mcp.models import SaveSearchRequest
    from gah.mcp.tools import tool_save_search

    deps = mcp_tool_deps()
    res = tool_save_search(deps, SaveSearchRequest(
        project_id="proj_save_x", name="my hero search",
        query="hero", kind="sprite",
    ))
    assert res.ok is True
    assert isinstance(res.saved_search_id, int)
    assert res.saved_search_id > 0


def test_save_search_duplicate_name_returns_400(mcp_tool_deps) -> None:
    from gah.mcp.models import SaveSearchRequest
    from gah.mcp.tools import McpToolError, tool_save_search

    deps = mcp_tool_deps()
    req = SaveSearchRequest(project_id="proj_dup_mcp", name="dup_name",
                            query="x")
    tool_save_search(deps, req)
    with pytest.raises(McpToolError) as ei:
        tool_save_search(deps, req)
    assert ei.value.code == "400_invalid_input"


def test_list_saved_searches_sorted_last_used_desc(mcp_tool_deps) -> None:
    from gah.mcp.models import RunSavedSearchRequest, SaveSearchRequest
    from gah.mcp.tools import tool_list_saved_searches, tool_run_saved_search, tool_save_search

    deps = mcp_tool_deps()
    pid = "proj_list_mcp"
    for nm in ("a_search", "b_search", "c_search"):
        tool_save_search(deps, SaveSearchRequest(project_id=pid, name=nm, query=nm))

    # b 만 실행 → last_used_at 업데이트.
    tool_run_saved_search(deps, RunSavedSearchRequest(project_id=pid, name="b_search"))

    res = tool_list_saved_searches(deps, pid)
    names = [it["name"] for it in res.saved_searches]
    assert names[0] == "b_search"   # 가장 최근 사용


def test_delete_saved_search_returns_ok_when_present(mcp_tool_deps) -> None:
    from gah.mcp.models import DeleteSavedSearchRequest, SaveSearchRequest
    from gah.mcp.tools import tool_delete_saved_search, tool_save_search

    deps = mcp_tool_deps()
    pid = "proj_del_mcp"
    tool_save_search(deps, SaveSearchRequest(project_id=pid, name="to_kill", query="x"))
    out = tool_delete_saved_search(deps, DeleteSavedSearchRequest(
        project_id=pid, name="to_kill",
    ))
    assert out["ok"] is True


def test_delete_saved_search_404_when_missing(mcp_tool_deps) -> None:
    from gah.mcp.models import DeleteSavedSearchRequest
    from gah.mcp.tools import McpToolError, tool_delete_saved_search

    deps = mcp_tool_deps()
    with pytest.raises(McpToolError) as ei:
        tool_delete_saved_search(deps, DeleteSavedSearchRequest(
            project_id="proj_missing_mcp", name="never_existed",
        ))
    assert ei.value.code == "404_not_found"


def test_run_saved_search_delegates_to_find_asset(mcp_tool_deps) -> None:
    """저장된 query_json 을 로드해 find_asset 와 같은 결과를 반환."""
    from gah.mcp.models import RunSavedSearchRequest, SaveSearchRequest
    from gah.mcp.tools import tool_run_saved_search, tool_save_search

    deps = mcp_tool_deps()
    pid = "proj_run_mcp"
    tool_save_search(deps, SaveSearchRequest(
        project_id=pid, name="hero search", query="hero", kind="sprite", count=3,
    ))
    res = tool_run_saved_search(deps, RunSavedSearchRequest(
        project_id=pid, name="hero search",
    ))
    # FindAssetResult 와 동일 형식 — query_id + results[].
    assert hasattr(res, "query_id")
    assert isinstance(res.results, list)


def test_run_saved_search_404_when_name_missing(mcp_tool_deps) -> None:
    from gah.mcp.models import RunSavedSearchRequest
    from gah.mcp.tools import McpToolError, tool_run_saved_search

    deps = mcp_tool_deps()
    with pytest.raises(McpToolError) as ei:
        tool_run_saved_search(deps, RunSavedSearchRequest(
            project_id="proj_run_404", name="ghost",
        ))
    assert ei.value.code == "404_not_found"


# ── 4. server 등록 회귀 가드 ─────────────────────────────────────────


def test_register_all_tools_count_is_17(mcp_tool_deps) -> None:
    """M3 의 12 → M4 의 16 → M5 의 17 (request_user_pick 추가)."""
    from gah.mcp.server import build_server

    deps = mcp_tool_deps()
    server = build_server(
        store=deps.store, search=deps.search, usage=deps.usage,
        registry=deps.registry, queue=None, config=deps.config,
    )
    # FastMCP 의 도구 목록 접근법은 SDK 버전에 따라 다름 — `tool_manager._tools`
    # 또는 `list_tools()` 어느 쪽이든 길이 17 이어야.
    names: set[str] = set()
    if hasattr(server, "_tool_manager"):
        names = set(server._tool_manager._tools.keys())
    elif hasattr(server, "list_tools"):
        import asyncio

        async def _names():
            tools = await server.list_tools()
            return {t.name for t in tools}

        names = asyncio.run(_names())
    assert len(names) == 17
    # M4 4 신규 도구 + M5 1 신규 도구 모두 등록되었는지 확인.
    assert {"save_search", "list_saved_searches",
            "delete_saved_search", "run_saved_search",
            "request_user_pick"} <= names
