"""M3 — MCP 12 도구의 Pydantic 모델 입출력 검증."""

from __future__ import annotations

import pytest


def test_find_asset_request_requires_query():
    from pydantic import ValidationError

    from gah.mcp.models import FindAssetRequest

    with pytest.raises(ValidationError):
        FindAssetRequest()  # type: ignore[call-arg]


def test_find_asset_request_rejects_invalid_kind():
    from pydantic import ValidationError

    from gah.mcp.models import FindAssetRequest

    with pytest.raises(ValidationError):
        FindAssetRequest(query="hero", kind="bogus_kind")


def test_label_filter_requires_axis_and_label():
    from pydantic import ValidationError

    from gah.mcp.models import AxisLabel

    with pytest.raises(ValidationError):
        AxisLabel(axis="category")  # type: ignore[call-arg]


def test_filters_accepts_known_optional_fields():
    from gah.mcp.models import Filters

    f = Filters(min_duration_ms=1000, max_duration_ms=5000, loopable=True,
                tags_any=["dark"])
    assert f.min_duration_ms == 1000
    assert f.loopable is True


def test_suggest_packs_request_default_count_5():
    from gah.mcp.models import SuggestPacksRequest

    req = SuggestPacksRequest(query="dark bgm")
    assert req.count == 5


def test_set_project_pin_request_accepts_null_pin():
    from gah.mcp.models import SetProjectPinRequest

    req = SetProjectPinRequest(project_id="D:/Unity/X", pinned_pack_id=None,
                                blocked_pack_ids=[])
    assert req.pinned_pack_id is None


def test_request_rescan_accepts_one_of_pack_asset_all():
    from pydantic import ValidationError

    from gah.mcp.models import RequestRescanRequest

    # Valid: exactly one.
    RequestRescanRequest(pack_id=1)
    RequestRescanRequest(asset_id=42)
    RequestRescanRequest(all=True)
    # Invalid: none / multiple.
    with pytest.raises(ValidationError):
        RequestRescanRequest()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        RequestRescanRequest(pack_id=1, asset_id=42)


def test_report_feedback_request_required_fields():
    from pydantic import ValidationError

    from gah.mcp.models import ReportFeedbackRequest

    with pytest.raises(ValidationError):
        ReportFeedbackRequest()  # type: ignore[call-arg]
    ReportFeedbackRequest(query_id=1, asset_id=2, reason="not_what_i_wanted")


def test_list_labels_result_signature_is_hex_string():
    from gah.mcp.models import ListLabelsResult

    res = ListLabelsResult(labels=[], signature="abcd1234ef567890")
    assert res.signature == "abcd1234ef567890"


def test_describe_label_result_includes_sample_assets():
    from gah.mcp.models import DescribeLabelResult

    res = DescribeLabelResult(
        axis="category", label="character",
        description="A playable or NPC figure.",
        sample_assets=[{"asset_id": 1, "path": "/a.png"}],
    )
    assert res.sample_assets[0]["asset_id"] == 1
