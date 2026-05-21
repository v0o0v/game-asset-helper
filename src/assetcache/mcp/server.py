"""MCP stdio 서버 빌더 + 진입점.

``--mcp`` 플래그가 ``run_stdio()`` 를 호출. 별도 프로세스로 동작하며 GUI
인스턴스와 같은 SQLite DB 를 공유한다. inter-process write 충돌은
WAL + ``busy_timeout=5000`` (M2.1) 이 흡수.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..config import Config, default_app_paths, load_config
from ..core.consistency import ConsistencyScorer
from ..core.embedding import EmbeddingEncoder
from ..core.labels import LabelRegistry
from ..core.ollama_client import OllamaClient
from ..core.search import HybridSearcher
from ..core.store import Store
from ..core.usage_tracker import UsageTracker
from ..logging_setup import setup_logging
from . import models as m
from . import tools as t

log = logging.getLogger(__name__)


INSTRUCTIONS = """\
GAH MCP server — find and adopt 2D sprites, sheets, and sounds for game projects.

Recommended workflow (DESIGN §13.1 + M4 + M5 update):
  1. Session start: call list_labels(with_description=true) once; cache by `signature`.
  2. User request: call suggest_packs(query, project_id, kind). Use the
     `samples[].thumbnail_path` (sprite) and `preview_blurb` to show previews.
  3. Pick: call find_asset(query, project_id, label_query="axis:label AND ...",
     diversity="mmr", force_pack_id=<picked>, count=N).
  4. Adoption: after copying a file to the project, call record_asset_use(asset_id, project_id, query_id).
  5. Rejection: call report_feedback(query_id, asset_id, reason="negative") —
     penalizes the asset/pack in subsequent searches for this project.
  6. Save reusable queries: save_search(project_id, name, ...) + later
     run_saved_search(project_id, name).
  7. User pick (uncertain): if you have ~5 candidates and are unsure which fits best,
     call request_user_pick(candidates=[id1,id2,...], project_id, reason="...").
     The GAH web UI must be running (tray mode). The call blocks up to 5 minutes while
     the user selects in the browser; the picked asset is auto-recorded as used.

label_query grammar (M4): `axis:label`, `AND`/`OR`/`NOT` (uppercase only),
`(...)` grouping; bare labels auto-resolve via the registry. Pure AND or
pure OR only — mixed `(a AND b) OR c` raises 400_invalid_input.

diversity: "none" (default) / "mmr" (λ trade-off, 0.7 recommended) /
"round_robin".

Always pass the same project_id throughout a session — consistency and
feedback penalty both depend on it.  The `signature` of list_labels stays
stable until users edit the vocabulary; refresh on change.

## 시트 + 애니메이션 (M6)
- find_asset 결과 중 kind='spritesheet' 인 자산이 있고 사용자가
  특정 애니메이션(예: walk) 을 요청했다면, suggest_animation_frames(asset_id, animation)
  로 프레임 인덱스 + fps_hint 를 받아 Unity AnimationClip 코드를 직접 만들 수 있다.
- 사용 가능한 animation 이름은 자산의 animations_json 키.
  404_not_found 응답의 메시지에 available 목록이 포함됨.

## Unity Asset Store 통합 (M7)

GAH 는 Unity Asset Store 로컬 캐시(.unitypackage) 도 인덱싱한다. 사용자가
이미 다운받아 둔 패키지 중 어떤 게 라이브러리에 임포트됐는지·아직 안 됐는지
파악하려면:

  scan_unity_asset_store_cache    — 캐시 디렉터리 재스캔.
  list_unity_packages(state="discovered")
                                   — 아직 임포트 안 된 패키지 목록.
                                     각 row 의 import_url 로 사용자에게
                                     "이 패키지 임포트하려면 <URL>" 안내.

임포트(파일 추출) 자체는 사용자가 웹 UI 에서 직접 트리거해야 한다 — MCP
도구로는 임포트할 수 없다(사용자 통제 보존).
"""


def build_server(
    *,
    store: Store,
    search: HybridSearcher,
    usage: UsageTracker,
    registry: LabelRegistry,
    queue: Any | None,
    config: Config,
    paths: Any | None = None,
) -> FastMCP:
    """20 도구를 등록한 FastMCP 인스턴스 반환 (M3 12 + M4 saved_searches 4 + M5 request_user_pick 1 + M6 suggest_animation_frames 1 + M7 scan+list 2)."""
    server = FastMCP("assetcache-mcp", instructions=INSTRUCTIONS)
    deps = t.ToolDeps(
        store=store, search=search, usage=usage,
        registry=registry, queue=queue, config=config, paths=paths,
    )
    register_all_tools(server, deps)
    return server


def register_all_tools(server: FastMCP, deps: t.ToolDeps) -> None:
    @server.tool(description="자연어 + 라벨 부울 필터로 자산을 찾는다. 추천 근거(matched_labels + why) 포함.")
    def find_asset(req: m.FindAssetRequest) -> m.FindAssetResult:
        return t.tool_find_asset(deps, req)

    @server.tool(description="asset_id 또는 path 로 단일 자산 메타를 조회.")
    def get_asset(req: m.GetAssetRequest) -> m.GetAssetResult:
        return t.tool_get_asset(deps, req)

    @server.tool(description="라이브러리 전체 자산을 페이지네이션으로 나열 (디버깅/탐색).")
    def list_assets(req: m.ListAssetsRequest) -> m.ListAssetsResult:
        return t.tool_list_assets(deps, req)

    @server.tool(description="등록된 팩 카탈로그 + 자산 수 + aggregate_meta 나열.")
    def list_packs() -> m.ListPacksResult:
        return t.tool_list_packs(deps)

    @server.tool(description="자연어 쿼리에 어울리는 팩 후보를 정렬한다 (사용자에게 팩 선택권 제공).")
    def suggest_packs(req: m.SuggestPacksRequest) -> m.SuggestPacksResult:
        return t.tool_suggest_packs(deps, req)

    @server.tool(description="자산 채택 이력을 기록한다 (통일성 가중치의 핵심 입력).")
    def record_asset_use(req: m.RecordAssetUseRequest) -> m.RecordAssetUseResult:
        return t.tool_record_asset_use(deps, req)

    @server.tool(description="프로젝트에 특정 팩을 고정/차단한다.")
    def set_project_pin(req: m.SetProjectPinRequest) -> dict:
        return t.tool_set_project_pin(deps, req)

    @server.tool(description="특정 팩/자산 또는 전체의 재분석을 트리거한다.")
    def request_rescan(req: m.RequestRescanRequest) -> dict:
        return t.tool_request_rescan(deps, req)

    @server.tool(description="추천 결과에 대한 사용자 피드백을 기록한다 (페널티 학습 입력).")
    def report_feedback(req: m.ReportFeedbackRequest) -> dict:
        return t.tool_report_feedback(deps, req)

    @server.tool(description="라벨 어휘의 24개 축 목록을 반환한다.")
    def list_label_axes() -> m.ListLabelAxesResult:
        return t.tool_list_label_axes(deps)

    @server.tool(description="라벨 어휘 목록 + 카탈로그 signature 를 반환한다 (signature 가 같으면 캐시 재사용).")
    def list_labels(req: m.ListLabelsRequest) -> m.ListLabelsResult:
        return t.tool_list_labels(deps, req)

    @server.tool(description="단일 라벨의 description + 샘플 자산 3개를 반환한다.")
    def describe_label(req: m.DescribeLabelRequest) -> m.DescribeLabelResult:
        return t.tool_describe_label(deps, req)

    # M4: saved_searches 4 신규 도구
    @server.tool(description="검색 요청을 이름 붙여 저장한다 (project_id 별 unique name).")
    def save_search(req: m.SaveSearchRequest) -> m.SaveSearchResult:
        return t.tool_save_search(deps, req)

    @server.tool(description="저장된 검색 목록 (project_id 별, 최근 사용순).")
    def list_saved_searches(project_id: str | None = None) -> m.ListSavedSearchesResult:
        return t.tool_list_saved_searches(deps, project_id)

    @server.tool(description="저장된 검색을 삭제한다.")
    def delete_saved_search(req: m.DeleteSavedSearchRequest) -> dict:
        return t.tool_delete_saved_search(deps, req)

    @server.tool(description="저장된 검색을 실행해 find_asset 결과를 반환한다 (overrides 로 일부 필드 덮어쓰기 가능).")
    def run_saved_search(req: m.RunSavedSearchRequest) -> m.FindAssetResult:
        return t.tool_run_saved_search(deps, req)

    # M5 Phase 4C: 17번째 도구
    @server.tool(description="후보 자산들 중 사용자가 직접 고르도록 요청한다. 5분 long-poll. GAH 의 웹 UI 가 떠 있어야 동작.")
    def request_user_pick(req: m.RequestUserPickRequest) -> m.RequestUserPickResult:
        return t.tool_request_user_pick(deps, req)

    # M6 Phase 3: 18번째 도구
    @server.tool(description="스프라이트 시트의 애니메이션(walk/idle/...)에 해당하는 frame_indices + fps_hint 를 반환한다 (Unity AnimationClip 직접 사용).")
    def suggest_animation_frames(req: m.SuggestAnimationFramesRequest) -> m.SuggestAnimationFramesResult:
        return t.tool_suggest_animation_frames(deps, req)

    # M7: 19번째 도구
    @server.tool(description="Unity Asset Store 캐시 디렉터리를 스캔해 .unitypackage 목록을 DB 에 동기화한다.")
    def scan_unity_asset_store_cache(req: m.ScanUnityAssetStoreCacheRequest) -> m.ScanUnityAssetStoreCacheResult:
        return t.tool_scan_unity_asset_store_cache(deps, req)

    # M7: 20번째 도구
    @server.tool(description="unity_imports 목록을 반환한다. state/publisher/asset_name 필터, 페이지네이션, 미리보기 카운트 지원.")
    def list_unity_packages(req: m.ListUnityPackagesRequest) -> m.ListUnityPackagesResult:
        return t.tool_list_unity_packages(deps, req)


def run_stdio() -> None:
    """``python -m assetcache --mcp`` 진입점.

    GUI 인스턴스와는 별도 프로세스. 워처는 안 띄움. KeyboardInterrupt 는
    graceful 종료 (예외 다시 던지지 않음).
    """
    paths = default_app_paths()
    paths.ensure_dirs()
    # logging_setup 은 file + stderr 핸들러를 모두 단다. stdio JSON-RPC 는
    # stdout 만 쓰므로 stderr 출력은 클라이언트(Claude Code) 를 방해하지 않는다.
    setup_logging(paths.log_path)
    cfg = load_config(paths.config_path)

    store = Store(paths.db_path)
    store.initialize()
    registry = LabelRegistry(store)
    registry.bootstrap()

    # MCP stdio 진입점은 검색 쿼리 임베딩만 필요 — 분석(이미지/오디오) 은
    # GUI 인스턴스가 별도 프로세스로 담당한다. OllamaClient 는 임베딩 모델로 초기화.
    ollama = OllamaClient(
        base_url=cfg.ollama_url, model=cfg.model_embed,
        timeout_seconds=cfg.analysis_timeout_seconds,
        max_retries=cfg.analysis_max_retries,
        parallel=cfg.ollama_parallel,
    )
    embedder = EmbeddingEncoder(ollama, model=cfg.model_embed)
    consistency = ConsistencyScorer(store, cfg)
    usage = UsageTracker(store, cfg)
    search = HybridSearcher(store, embedder, consistency, registry, cfg)

    server = build_server(
        store=store, search=search, usage=usage,
        registry=registry, queue=None, config=cfg, paths=paths,
    )
    log.info("MCP stdio server starting; tools=20 instructions_len=%d", len(INSTRUCTIONS))
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        log.info("MCP stdio server interrupted; shutting down gracefully")
    finally:
        store.close()
