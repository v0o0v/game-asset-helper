"""M3 — MCP 12 도구의 동작 검증 (in-process)."""

from __future__ import annotations

import pytest


def _find(deps, **kwargs):
    from gah.mcp.models import FindAssetRequest
    from gah.mcp.tools import tool_find_asset

    return tool_find_asset(deps, FindAssetRequest(**kwargs))


# ─────────────────────────────────────────────────────────────────────


def test_find_asset_returns_results_with_query_id(mcp_tool_deps):
    deps = mcp_tool_deps()
    res = _find(deps, query="hero pixel", count=3)
    assert hasattr(res, "query_id")
    assert isinstance(res.results, list)


def test_find_asset_rejects_invalid_kind(mcp_tool_deps):
    from pydantic import ValidationError

    deps = mcp_tool_deps()
    with pytest.raises(ValidationError):
        _find(deps, query="hero", kind="bogus")


def test_find_asset_propagates_labels_filter_to_searcher(mcp_tool_deps, populated_store):
    _, ids = populated_store
    deps = mcp_tool_deps()
    res = _find(
        deps, query="anything",
        labels_all=[{"axis": "category", "label": "character"}],
    )
    result_ids = {r["asset_id"] for r in res.results}
    assert result_ids <= {ids["hero"]}


def test_get_asset_by_id(mcp_tool_deps, populated_store):
    from gah.mcp.models import GetAssetRequest
    from gah.mcp.tools import tool_get_asset

    _, ids = populated_store
    deps = mcp_tool_deps()
    res = tool_get_asset(deps, GetAssetRequest(asset_id=ids["hero"]))
    assert res.asset_id == ids["hero"]
    assert "hero" in res.path


def test_get_asset_by_path(mcp_tool_deps, populated_store):
    from gah.mcp.models import GetAssetRequest
    from gah.mcp.tools import tool_get_asset

    _, ids = populated_store
    deps = mcp_tool_deps()
    res = tool_get_asset(deps, GetAssetRequest(path="pack_a/assets/hero.png"))
    assert res.asset_id == ids["hero"]


def test_get_asset_404_when_missing(mcp_tool_deps):
    from gah.mcp.models import GetAssetRequest
    from gah.mcp.tools import McpToolError, tool_get_asset

    deps = mcp_tool_deps()
    with pytest.raises(McpToolError) as exc_info:
        tool_get_asset(deps, GetAssetRequest(asset_id=9_999_999))
    assert exc_info.value.code == "404_not_found"


def test_list_assets_pagination(mcp_tool_deps):
    from gah.mcp.models import ListAssetsRequest
    from gah.mcp.tools import tool_list_assets

    deps = mcp_tool_deps()
    page1 = tool_list_assets(deps, ListAssetsRequest(page=1, page_size=2))
    assert len(page1.assets) <= 2
    page2 = tool_list_assets(deps, ListAssetsRequest(page=2, page_size=2))
    page1_ids = {a["asset_id"] for a in page1.assets}
    page2_ids = {a["asset_id"] for a in page2.assets}
    assert not (page1_ids & page2_ids)  # disjoint


def test_list_packs_includes_asset_counts(mcp_tool_deps):
    from gah.mcp.tools import tool_list_packs

    deps = mcp_tool_deps()
    res = tool_list_packs(deps)
    assert len(res.packs) == 2
    counts = res.packs[0]["asset_counts"]
    assert "sprite" in counts or "sound" in counts


def test_suggest_packs_returns_pack_score_breakdown(mcp_tool_deps):
    from gah.mcp.models import SuggestPacksRequest
    from gah.mcp.tools import tool_suggest_packs

    deps = mcp_tool_deps()
    res = tool_suggest_packs(deps, SuggestPacksRequest(query="character"))
    if res.packs:
        first = res.packs[0]
        assert "score" in first
        assert "score_breakdown" in first


def test_suggest_packs_groups_by_pack(mcp_tool_deps, populated_store):
    from gah.mcp.models import SuggestPacksRequest
    from gah.mcp.tools import tool_suggest_packs

    _, ids = populated_store
    deps = mcp_tool_deps()
    res = tool_suggest_packs(deps, SuggestPacksRequest(query="anything"))
    pack_ids = [p["pack_id"] for p in res.packs]
    assert len(pack_ids) == len(set(pack_ids))  # no duplicates
    assert set(pack_ids) <= {ids["pack_a"], ids["pack_b"]}


def test_record_asset_use_persists(mcp_tool_deps, populated_store):
    from gah.mcp.models import RecordAssetUseRequest
    from gah.mcp.tools import tool_record_asset_use

    store, ids = populated_store
    deps = mcp_tool_deps()
    res = tool_record_asset_use(deps, RecordAssetUseRequest(
        project_id="proj1", asset_id=ids["hero"], query_id=None, context="t",
    ))
    assert res.ok is True
    assert res.usage_id > 0
    n = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE asset_id=?", (ids["hero"],)
    ).fetchone()[0]
    assert n == 1


def test_record_asset_use_affects_next_consistency(mcp_tool_deps, populated_store):
    from gah.mcp.models import RecordAssetUseRequest
    from gah.mcp.tools import tool_record_asset_use

    _, ids = populated_store
    deps = mcp_tool_deps()

    first = _find(deps, query="hero pixel", project_id="proj_cs")
    before_results = [r for r in first.results if r["asset_id"] == ids["hero"]]

    tool_record_asset_use(deps, RecordAssetUseRequest(
        project_id="proj_cs", asset_id=ids["hero"], query_id=first.query_id, context=None,
    ))

    second = _find(deps, query="hero pixel", project_id="proj_cs")
    after_results = [r for r in second.results if r["asset_id"] == ids["hero"]]
    if before_results and after_results:
        before_c = before_results[0]["score_breakdown"]["consistency"]
        after_c = after_results[0]["score_breakdown"]["consistency"]
        assert after_c > before_c


def test_set_project_pin_persists(mcp_tool_deps):
    from gah.mcp.models import SetProjectPinRequest
    from gah.mcp.tools import tool_set_project_pin

    deps = mcp_tool_deps()
    res = tool_set_project_pin(deps, SetProjectPinRequest(
        project_id="proj_pin", pinned_pack_id=None, blocked_pack_ids=[],
    ))
    assert res["ok"] is True


def test_set_project_pin_makes_pack_first_in_next_search(mcp_tool_deps, populated_store):
    from gah.mcp.models import SetProjectPinRequest
    from gah.mcp.tools import tool_set_project_pin

    _, ids = populated_store
    deps = mcp_tool_deps()
    tool_set_project_pin(deps, SetProjectPinRequest(
        project_id="proj_pin2", pinned_pack_id=ids["pack_b"], blocked_pack_ids=[],
    ))
    res = _find(deps, query="anything", project_id="proj_pin2")
    if res.results:
        assert res.results[0]["pack_id"] == ids["pack_b"]


def test_request_rescan_pack_enqueues_via_queue(mcp_tool_deps, populated_store):
    from gah.mcp.models import RequestRescanRequest
    from gah.mcp.tools import tool_request_rescan

    _, ids = populated_store

    enqueue_log: list[int] = []

    class _FakeQueue:
        def enqueue_pack(self, pack_id):
            enqueue_log.append(pack_id)
            return 3  # pretend 3 assets enqueued

        def enqueue_asset(self, asset_id):
            enqueue_log.append(-asset_id)
            return 1

    deps = mcp_tool_deps(queue=_FakeQueue())
    res = tool_request_rescan(deps, RequestRescanRequest(pack_id=ids["pack_a"]))
    assert res["enqueued"] == 3
    assert enqueue_log == [ids["pack_a"]]


def test_request_rescan_without_queue_returns_warning(mcp_tool_deps, populated_store):
    from gah.mcp.models import RequestRescanRequest
    from gah.mcp.tools import tool_request_rescan

    _, ids = populated_store
    deps = mcp_tool_deps(queue=None)
    res = tool_request_rescan(deps, RequestRescanRequest(pack_id=ids["pack_a"]))
    assert "warnings" in res
    assert any("no live worker" in w for w in res["warnings"])


def test_report_feedback_logs_and_returns_ok(mcp_tool_deps, populated_store):
    from gah.mcp.models import ReportFeedbackRequest
    from gah.mcp.tools import tool_report_feedback

    store, ids = populated_store
    deps = mcp_tool_deps()
    p = store.upsert_project("proj_fb")
    qid = store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])
    res = tool_report_feedback(deps, ReportFeedbackRequest(
        # M4: reason 은 Literal['negative','positive','irrelevant'] — 자유 문자열 금지.
        query_id=qid, asset_id=ids["hero"], reason="negative",
    ))
    assert res["ok"] is True


def test_list_label_axes_returns_24(mcp_tool_deps):
    from gah.mcp.tools import tool_list_label_axes

    deps = mcp_tool_deps()
    res = tool_list_label_axes(deps)
    assert len(res.axes) == 24  # 14 visual + 10 sound (M2 seed)


def test_list_labels_includes_signature(mcp_tool_deps):
    from gah.mcp.models import ListLabelsRequest
    from gah.mcp.tools import tool_list_labels

    deps = mcp_tool_deps()
    res = tool_list_labels(deps, ListLabelsRequest(axis="style"))
    assert res.signature  # non-empty hex string
    assert len(res.signature) >= 8


def test_list_labels_signature_changes_after_add(mcp_tool_deps):
    from gah.mcp.models import ListLabelsRequest
    from gah.mcp.tools import tool_list_labels

    deps = mcp_tool_deps()
    sig_before = tool_list_labels(deps, ListLabelsRequest()).signature
    deps.registry.add_label("style", "my_custom_test_label", description="x")
    sig_after = tool_list_labels(deps, ListLabelsRequest()).signature
    assert sig_before != sig_after


def test_describe_label_returns_top3_samples(mcp_tool_deps):
    from gah.mcp.models import DescribeLabelRequest
    from gah.mcp.tools import tool_describe_label

    deps = mcp_tool_deps()
    res = tool_describe_label(deps, DescribeLabelRequest(axis="category", label="character"))
    assert res.axis == "category"
    assert res.label == "character"
    assert isinstance(res.sample_assets, list)
    assert len(res.sample_assets) <= 3


def test_write_tools_acquire_store_write_lock(mcp_tool_deps, populated_store):
    """write 도구가 store.write_lock 안에서 동작하는지 spy."""
    from gah.mcp.models import RecordAssetUseRequest
    from gah.mcp.tools import tool_record_asset_use

    store, ids = populated_store
    original_lock = store.write_lock
    acquire_count = 0

    class _SpyLock:
        def __enter__(self_inner):
            nonlocal acquire_count
            acquire_count += 1
            return original_lock.__enter__()

        def __exit__(self_inner, *args):
            return original_lock.__exit__(*args)

        def acquire(self_inner, *args, **kwargs):
            nonlocal acquire_count
            acquire_count += 1
            return original_lock.acquire(*args, **kwargs)

        def release(self_inner):
            return original_lock.release()

    store.write_lock = _SpyLock()  # type: ignore[assignment]
    try:
        deps = mcp_tool_deps(store=store)
        tool_record_asset_use(deps, RecordAssetUseRequest(
            project_id="proj_lock", asset_id=ids["hero"], query_id=None, context=None,
        ))
        assert acquire_count >= 1
    finally:
        store.write_lock = original_lock  # type: ignore[assignment]
