"""MCP 도구 12개의 입출력 Pydantic 모델.

규약:
- 모든 모델에 ``extra="forbid"`` — 알려지지 않은 필드는 ValidationError.
- enum 필드(`kind`, `source`) 는 `Literal[...]` 화이트리스트.
- 응답 필드는 가능한 한 dict/list 로 평탄화 — MCP JSON-RPC 직렬화 단순.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_AssetKind = Literal["sprite", "spritesheet", "sound"]


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 공용 ─────────────────────────────────────────────────────────────


class AxisLabel(_BaseModel):
    axis: str
    label: str


class Filters(_BaseModel):
    tags_any: list[str] | None = None
    min_duration_ms: int | None = None
    max_duration_ms: int | None = None
    loopable: bool | None = None


# ── find_asset ───────────────────────────────────────────────────────


class FindAssetRequest(_BaseModel):
    query: str
    kind: _AssetKind | None = None
    count: int = 5
    project_id: str | None = None
    prefer_pack_id: int | None = None
    force_pack_id: int | None = None
    exclude_pack_ids: list[int] = Field(default_factory=list)
    consistency_weight_override: float | None = None
    label_match_weight_override: float | None = None
    filters: Filters | dict[str, Any] = Field(default_factory=dict)
    labels_all: list[AxisLabel] = Field(default_factory=list)
    labels_any: list[AxisLabel] = Field(default_factory=list)
    labels_none: list[AxisLabel] = Field(default_factory=list)


class FindAssetResult(_BaseModel):
    query_id: int
    results: list[dict[str, Any]]


# ── get_asset ────────────────────────────────────────────────────────


class GetAssetRequest(_BaseModel):
    asset_id: int | None = None
    path: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "GetAssetRequest":
        if (self.asset_id is None) == (self.path is None):
            raise ValueError("exactly one of asset_id or path must be provided")
        return self


class GetAssetResult(_BaseModel):
    asset_id: int
    pack_id: int
    pack_name: str
    path: str
    kind: str
    analysis_state: str
    meta: dict[str, Any] = Field(default_factory=dict)
    labels: list[dict[str, Any]] = Field(default_factory=list)


# ── list_assets ──────────────────────────────────────────────────────


class ListAssetsRequest(_BaseModel):
    pack_id: int | None = None
    kind: _AssetKind | None = None
    page: int = 1
    page_size: int = 50


class ListAssetsResult(_BaseModel):
    assets: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


# ── list_packs ───────────────────────────────────────────────────────


class ListPacksResult(_BaseModel):
    packs: list[dict[str, Any]]


# ── suggest_packs ────────────────────────────────────────────────────


class SuggestPacksRequest(_BaseModel):
    query: str | None = None
    project_id: str | None = None
    kind: _AssetKind | None = None
    count: int = 5
    include_samples: bool = True
    include_thumbnails: bool = True
    min_matching_assets: int = 1


class SuggestPacksResult(_BaseModel):
    query_id: int
    project_context: dict[str, Any] = Field(default_factory=dict)
    packs: list[dict[str, Any]]


# ── record_asset_use ─────────────────────────────────────────────────


class RecordAssetUseRequest(_BaseModel):
    project_id: str
    asset_id: int
    query_id: int | None = None
    context: str | None = None


class RecordAssetUseResult(_BaseModel):
    ok: bool
    usage_id: int


# ── set_project_pin ──────────────────────────────────────────────────


class SetProjectPinRequest(_BaseModel):
    project_id: str
    pinned_pack_id: int | None = None
    blocked_pack_ids: list[int] = Field(default_factory=list)


# ── request_rescan ───────────────────────────────────────────────────


class RequestRescanRequest(_BaseModel):
    pack_id: int | None = None
    asset_id: int | None = None
    all: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> "RequestRescanRequest":
        present = sum(
            x is not None and x is not False
            for x in (self.pack_id, self.asset_id, self.all if self.all else None)
        )
        if present != 1:
            raise ValueError("exactly one of pack_id, asset_id, all must be provided")
        return self


# ── report_feedback ──────────────────────────────────────────────────


class ReportFeedbackRequest(_BaseModel):
    query_id: int
    asset_id: int
    reason: str


# ── label vocabulary 메타 ────────────────────────────────────────────


class ListLabelAxesResult(_BaseModel):
    axes: list[str]


class ListLabelsRequest(_BaseModel):
    axis: str | None = None
    enabled_only: bool = True
    with_description: bool = True


class ListLabelsResult(_BaseModel):
    labels: list[dict[str, Any]]
    signature: str


class DescribeLabelRequest(_BaseModel):
    axis: str
    label: str


class DescribeLabelResult(_BaseModel):
    axis: str
    label: str
    description: str | None = None
    sample_assets: list[dict[str, Any]] = Field(default_factory=list)
