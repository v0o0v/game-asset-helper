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
    # M4 신규 — 자연어 라벨 부울 / 다양성 / 피드백 가중 override
    label_query: str | None = None
    diversity: Literal["none", "mmr", "round_robin"] = "none"
    diversity_lambda: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_feedback_override: float | None = None


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
    source: str = "manual"  # "manual" | "mcp" | "claude_pick" | "implicit_top1"


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
    # M4: reason 화이트리스트 — Config 의 signed weight 와 1:1 매핑.
    reason: Literal["negative", "positive", "irrelevant"]


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


# ── M4: saved_searches 4 도구 ────────────────────────────────────────


class SaveSearchRequest(_BaseModel):
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    query: str = ""
    label_query: str | None = None
    kind: _AssetKind | None = None
    labels_all: list[AxisLabel] = Field(default_factory=list)
    labels_any: list[AxisLabel] = Field(default_factory=list)
    labels_none: list[AxisLabel] = Field(default_factory=list)
    filters: Filters | dict[str, Any] = Field(default_factory=dict)
    diversity: Literal["none", "mmr", "round_robin"] = "none"
    diversity_lambda: float | None = None
    count: int = 5


class SaveSearchResult(_BaseModel):
    ok: bool
    saved_search_id: int


class ListSavedSearchesResult(_BaseModel):
    saved_searches: list[dict[str, Any]]


class DeleteSavedSearchRequest(_BaseModel):
    project_id: str | None = None
    name: str


class RunSavedSearchRequest(_BaseModel):
    project_id: str | None = None
    name: str
    overrides: dict[str, Any] = Field(default_factory=dict)


# ── M5 Phase 4C: request_user_pick ───────────────────────────────────


class RequestUserPickRequest(_BaseModel):
    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=1800)


class RequestUserPickResult(_BaseModel):
    picked_asset_id: int
    picked_at: int
    user_note: str | None = None


# ── M6 — Sheet animation frames ──────────────────────────────────────


class SuggestAnimationFramesRequest(_BaseModel):
    asset_id: int = Field(ge=1)
    animation: str = Field(min_length=1, max_length=64)


class SuggestAnimationFramesResult(_BaseModel):
    frame_indices: list[int]
    fps_hint: int


# ── M7 — Unity Asset Store 임포트 ────────────────────────────────────


class ScanFilter(_BaseModel):
    publisher_glob: str | None = None
    asset_name_glob: str | None = None


class ScanUnityAssetStoreCacheRequest(_BaseModel):
    force: bool = False
    filter: ScanFilter | None = None


class ScanUnityAssetStoreCacheResult(_BaseModel):
    scanned: int
    new: int
    updated: int
    unchanged: int
    removed: int
    cache_path: str
    warnings: list[str] = []


class ListUnityPackagesRequest(_BaseModel):
    state: Literal[
        "discovered", "previewed", "import_pending",
        "imported", "skipped", "failed",
    ] | None = None
    filter: ScanFilter | None = None
    include_preview: bool = False
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


class UnityPackageItem(_BaseModel):
    id: int
    package_path: str
    publisher: str | None
    category: str | None
    asset_name: str
    package_size: int
    package_mtime: int
    import_state: str
    preview_asset_count: int | None
    preview_image_count: int | None
    preview_sound_count: int | None
    pack_id: int | None
    imported_at: int | None
    import_url: str


class ListUnityPackagesResult(_BaseModel):
    total: int
    items: list[UnityPackageItem]
