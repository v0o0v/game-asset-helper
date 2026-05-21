# M3 todo

[M3_plan.md](./M3_plan.md) 에서 도출한 TDD 순서 체크리스트. 작업 단위 번호(§3.x) 는 plan 의 절을 그대로 가리킨다.

체크박스 진행 규칙은 M2 와 동일 — A(스캐폴딩) → B(red, 테스트 먼저 모두 작성·실행) → C(green, 모듈 의존 순서대로 통과) → D(검증) → E(M4 인계).

## A. 스캐폴딩 / 의존성 / SDK 스파이크

`milestones/M3_plan.md` §3.1 의 선행 스파이크 + §2.1 의 의존성·테스트 인프라.

- [ ] **스파이크** — `mcp` 공식 SDK 설치 + 부팅 검증
  - PowerShell: `& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"`
  - PowerShell: `pip install "mcp>=1.0"` (실측 후 정확 버전 핀 결정)
  - PowerShell: `python -c "from mcp.server.fastmcp import FastMCP; s = FastMCP('test'); print(s.name)"`
  - 1줄 응답 (`test` 같은 서버명) 이 출력되면 통과. ImportError / API mismatch 면 `M3_plan.md §6 위험요소` 의 직접 JSON-RPC 폴백으로 분기 결정.
- [ ] `pyproject.toml` — `dependencies` 에 추가
  - `mcp>=1.0,<2.0` (스파이크 결과의 정확 버전으로 lower bound 갱신)
- [ ] `pyproject.toml [tool.pytest.ini_options]` 갱신
  - `markers` 에 `mcp_integration: requires real mcp stdio subprocess` 추가
  - `addopts = "-ra -m 'not clip_integration and not mcp_integration'"` 로 변경
- [ ] `src/gah/mcp/__init__.py` — 빈 패키지 마커
- [ ] `tests/conftest.py` — M3 픽스처 추가
  - `fake_embedder` — sha256 기반 결정적 인코더. `encode_text(text) -> (bytes, dim)` / `decode_vector(blob, dim) -> np.ndarray` (M2 `EmbeddingEncoder` 와 동일 인터페이스)
  - `populated_store` — 2 팩(`pack_a`, `pack_b`) × 3 자산 × 분석 완료(라벨 5축, 임베딩, sprite_meta/sound_meta, FTS 색인) seed 헬퍼
  - `consistency_summary_factory` — `ProjectUsageSummary` 즉석 빌더
  - `mcp_tool_deps` — `ToolDeps(store, search, usage, registry, queue=None, config)` 즉석 빌더 (테스트별 일부 컴포넌트 fake 주입)
- [ ] 의존성 설치 확인 — PowerShell: `pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]` (mcp wheel 자동 따라옴)

## B. 테스트 작성 (red phase)

먼저 모든 테스트 파일을 작성하고 `pytest -q` 한 번 돌려서 **새로 추가된 테스트들이 모두 fail** 하는지 확인. M0/M1/M2/M2.1 의 221 케이스는 그대로 PASS.

### B.1 `tests/test_store_m3.py` (20 케이스)

- [ ] `test_initialize_creates_m3_tables` — projects/asset_usage/search_queries 모두 존재
- [ ] `test_initialize_is_idempotent_with_m1_m2_tables` — 두 번 호출해도 OK
- [ ] `test_upsert_project_returns_row_with_id`
- [ ] `test_upsert_project_updates_last_seen_on_second_call`
- [ ] `test_upsert_project_preserves_display_name_when_arg_none`
- [ ] `test_set_project_pin_persists`
- [ ] `test_set_blocked_packs_json_roundtrip`
- [ ] `test_record_asset_use_increments_usage_count`
- [ ] `test_project_usage_summary_aggregates_pack_and_vendor`
- [ ] `test_project_usage_summary_empty_project_returns_defaults`
- [ ] `test_last_query_top1_returns_none_when_no_query`
- [ ] `test_last_query_top1_returns_recent_only` — `within_seconds` 경과면 None
- [ ] `test_insert_search_query_persists_json`
- [ ] `test_fts_search_matches_label_prefix` — M2 의 `label:bgm` 토큰 인덱싱 확인
- [ ] `test_fts_search_excludes_blocked_packs`
- [ ] `test_fts_search_filters_by_kind`
- [ ] `test_semantic_candidates_load_blob_roundtrip` — float32 LE bytes ↔ numpy 정확
- [ ] `test_asset_labels_for_returns_all_axes_per_asset`
- [ ] `test_pack_aggregate_decodes_json`
- [ ] `test_recent_assets_score_within_zero_one_using_analyzed_at`
- [ ] `test_delete_project_cascades_usage_and_queries`

### B.2 `tests/test_consistency.py` (12 케이스)

- [ ] `test_first_search_no_history_returns_zero_score`
- [ ] `test_same_pack_used_grants_06`
- [ ] `test_same_vendor_different_pack_grants_03`
- [ ] `test_style_match_adds_02`
- [ ] `test_palette_close_under_threshold_adds_01`
- [ ] `test_palette_far_above_threshold_no_bonus`
- [ ] `test_locked_project_with_foreign_pack_gets_minus_02`
- [ ] `test_pinned_pack_short_circuits_to_one`
- [ ] `test_blocked_pack_short_circuits_to_zero`
- [ ] `test_score_clamps_to_zero_one_range`
- [ ] `test_is_locked_threshold_exactly_at_min_uses`
- [ ] `test_format_why_includes_use_count_korean`

### B.3 `tests/test_usage_tracker.py` (8 케이스)

- [ ] `test_record_explicit_returns_usage_id`
- [ ] `test_record_explicit_with_query_id_sets_source_explicit`
- [ ] `test_implicit_off_returns_none` — `config.implicit_top1_enabled=False` 기본값
- [ ] `test_implicit_on_records_top1_of_last_query`
- [ ] `test_implicit_does_not_duplicate_for_same_query_id`
- [ ] `test_summary_empty_project_has_zero_total`
- [ ] `test_summary_aggregates_correctly_after_two_uses`
- [ ] `test_summary_dominant_style_picks_most_used_packs_style`

### B.4 `tests/test_search.py` (20 케이스)

- [ ] `test_hybrid_returns_topn_sorted`
- [ ] `test_score_breakdown_sums_to_score_within_tolerance` — 오차 ≤ 1e-4
- [ ] `test_empty_candidates_returns_empty_results`
- [ ] `test_labels_all_filters_out_non_matching`
- [ ] `test_labels_any_unions_matches`
- [ ] `test_labels_none_excludes_matches`
- [ ] `test_force_pack_id_restricts_scope`
- [ ] `test_exclude_pack_ids_removes_candidates`
- [ ] `test_prefer_pack_id_adds_bonus`
- [ ] `test_pinned_pack_id_is_first`
- [ ] `test_blocked_pack_excluded_even_if_high_semantic`
- [ ] `test_kind_filter_sprite_only`
- [ ] `test_matched_labels_contain_axis_label_source_score`
- [ ] `test_why_includes_consistency_phrase_when_consistency_positive`
- [ ] `test_why_mentions_first_search_when_history_empty`
- [ ] `test_query_id_persisted_in_search_queries`
- [ ] `test_min_max_normalization_handles_single_candidate` — keyword=0, semantic=1
- [ ] `test_label_match_zero_does_not_renormalize_other_channels`
- [ ] `test_consistency_override_weight_applied`
- [ ] `test_recent_asset_gets_higher_recency_score`

### B.5 `tests/test_mcp_models.py` (10 케이스)

- [ ] `test_find_asset_request_requires_query`
- [ ] `test_find_asset_request_rejects_invalid_kind`
- [ ] `test_label_filter_requires_axis_and_label`
- [ ] `test_filters_accepts_known_optional_fields`
- [ ] `test_suggest_packs_request_default_count_5`
- [ ] `test_set_project_pin_request_accepts_null_pin`
- [ ] `test_request_rescan_accepts_one_of_pack_asset_all`
- [ ] `test_report_feedback_request_required_fields`
- [ ] `test_list_labels_result_signature_is_hex_string`
- [ ] `test_describe_label_result_includes_sample_assets`

### B.6 `tests/test_mcp_tools.py` (22 케이스)

- [ ] `test_find_asset_returns_results_with_query_id`
- [ ] `test_find_asset_rejects_invalid_kind`
- [ ] `test_find_asset_propagates_labels_filter_to_searcher`
- [ ] `test_get_asset_by_id`
- [ ] `test_get_asset_by_path`
- [ ] `test_get_asset_404_when_missing` — typed `404_not_found`
- [ ] `test_list_assets_pagination`
- [ ] `test_list_packs_includes_asset_counts`
- [ ] `test_suggest_packs_returns_pack_score_breakdown`
- [ ] `test_suggest_packs_groups_by_pack`
- [ ] `test_record_asset_use_persists`
- [ ] `test_record_asset_use_affects_next_consistency` — 같은 project 의 다음 `find_asset` 의 consistency 가 0 → 양수
- [ ] `test_set_project_pin_persists`
- [ ] `test_set_project_pin_makes_pack_first_in_next_search`
- [ ] `test_request_rescan_pack_enqueues_via_queue`
- [ ] `test_request_rescan_without_queue_returns_warning` — `503_no_worker` 아님, OK + warnings
- [ ] `test_report_feedback_logs_and_returns_ok`
- [ ] `test_list_label_axes_returns_24`
- [ ] `test_list_labels_includes_signature`
- [ ] `test_list_labels_signature_changes_after_add`
- [ ] `test_describe_label_returns_top3_samples`
- [ ] `test_write_tools_acquire_store_write_lock` — `store.write_lock` 의 `acquire/release` 가 호출됨 (spy)

### B.7 `tests/test_mcp_server_stdio.py` (6 케이스, in-process)

- [ ] `test_build_server_returns_fastmcp_instance`
- [ ] `test_instructions_field_is_non_empty_and_mentions_workflow`
- [ ] `test_all_twelve_tools_registered`
- [ ] `test_each_tool_has_description`
- [ ] `test_run_stdio_graceful_on_keyboardinterrupt`
- [ ] `test_get_asset_tool_returns_typed_error_on_missing_id`

### B.8 `tests/test_library_search_ui.py` (5 케이스, offscreen)

- [ ] `test_empty_input_shows_default_library_model`
- [ ] `test_input_debounce_does_not_call_searcher_within_250ms`
- [ ] `test_input_calls_searcher_once_after_250ms`
- [ ] `test_search_result_replaces_grid_model`
- [ ] `test_clearing_input_restores_default_model`

### B.9 `tests/test_config_m3.py` (6 케이스)

- [ ] `test_new_fields_have_documented_defaults`
- [ ] `test_weight_sum_equals_one_within_tolerance` — 합 1.0 (±1e-6)
- [ ] `test_implicit_top1_default_is_false`
- [ ] `test_consistency_locked_fields_are_positive_int`
- [ ] `test_mcp_search_default_count_in_range_1_to_50`
- [ ] `test_toml_roundtrip_preserves_new_fields`

### B.10 `tests/test_entrypoint.py` 확장 (1 신규 케이스)

- [ ] `test_mcp_flag_calls_run_stdio` — `gah.mcp.server.run_stdio` 를 monkeypatch 로 가로채 호출 검증, 기존 stub "not implemented" 가 사라졌는지 확인

### B.11 `tests/test_mcp_integration.py` (2 케이스, `mcp_integration` 마크 — 옵트인)

- [ ] `@pytest.mark.mcp_integration test_stdio_subprocess_initialize_handshake` — `python -m gah --mcp --data-dir <tmp>` subprocess + JSON-RPC `initialize` 응답 라인 1줄 받기
- [ ] `@pytest.mark.mcp_integration test_stdio_subprocess_tools_list_returns_12` — 같은 subprocess 에 `tools/list` 호출 → 응답에 12 도구 명

빠진 회귀 방지 — `tests/test_imports.py` 가 M3 모듈 추가 후 그대로 통과해야 한다. `test_imports.py` 는 새 모듈 목록(`gah.core.search`, `gah.core.consistency`, `gah.core.usage_tracker`, `gah.mcp.server`, `gah.mcp.tools`, `gah.mcp.models`) 추가 후 그대로 PASS.

**테스트 작성 후 한 번 돌려 확인** — `pytest -q` 결과가 M0/M1/M2/M2.1 **221 PASS** + M3 신규 **~110 FAILED** 가 되어야 한다(`mcp_integration` 2 + `clip_integration` 2 = 4 deselected, 활성 FAILED ~108). 새 테스트가 PASS 라고 표시되면 그건 테스트가 잘못 통과한다는 신호 — fixture 누락이나 import 우회 점검.

> 케이스 합: B.1(20) + B.2(12) + B.3(8) + B.4(20) + B.5(10) + B.6(22) + B.7(6) + B.8(5) + B.9(6) + B.10(1) = **110 신규 active** + B.11(2 opt-in) = 112 신규. plan §자기검토 메모의 ~94 보수 추정에서 ~110 로 정확화.

## C. 구현 (green phase)

의존 순서대로 모듈을 작성하고, 해당 모듈 단위 테스트만 좁혀 돌려 통과 확인 (`pytest tests/test_<x>.py -v`). 한 묶음이 끝나면 인접 묶음 회귀가 없는지 `pytest -q` 한 번.

### C.1 Config + Store 마이그레이션

- [ ] `src/gah/config.py` — M3 필드 8 개 추가
  - `weight_semantic: float = 0.40`
  - `weight_keyword: float = 0.15`
  - `weight_label_match: float = 0.20`
  - `weight_consistency: float = 0.20`
  - `weight_recency: float = 0.05`
  - `consistency_locked_max_packs: int = 2`
  - `consistency_locked_min_uses: int = 5`
  - `palette_delta_e_threshold: float = 30.0`
  - `implicit_top1_enabled: bool = False`
  - `mcp_search_default_count: int = 5`
  - `recency_window_seconds: int = 2_592_000` (30 일)
  - `from_mapping` 에서 `weight_*` 합이 1.0 ±1e-6 아니면 경고 로그 + 기본값 폴백
- [ ] `src/gah/core/store.py` 수정 — `_M3_SCHEMA` 상수 + `initialize()` 가 M1·M2·M3 셋 다 실행
  - 신규 테이블: projects / asset_usage / search_queries + 인덱스 4 개
  - 신규 데이터클래스: `ProjectRow(id, external_id, display_name, first_seen, last_seen, pinned_pack_id, blocked_packs: list[int])`, `ProjectUsageSummary` (`core/usage_tracker.py` 와 공유)
  - write 메서드: `upsert_project` / `set_project_pin` / `set_blocked_packs` / `record_asset_use` / `insert_search_query`
  - read 메서드: `get_project` / `project_usage_summary` / `last_query_top1_for_project(project_id, within_seconds)` / `fts_search` / `semantic_candidates_load` / `asset_labels_for` / `pack_aggregate` / `recent_assets_score` / `asset_count_by_kind`
  - 모든 write 는 `with self.write_lock:` 안에서 SQLite 호출
- [ ] 테스트 좁혀 돌리기 — `pytest tests/test_config_m3.py tests/test_store_m3.py -v`

### C.2 ConsistencyScorer

- [ ] `src/gah/core/consistency.py` 신규
  - `ConsistencyResult(score, signals, locked)` dataclass
  - `ConsistencyScorer(store, config)` 클래스 — `score_asset` / `score_pack` / `is_locked` / `format_why`
  - 점수 산정 표 (M3_plan.md §3.3 참조) 그대로 — 같은 팩 +0.6, 같은 벤더 +0.3, 스타일 +0.2, 팔레트 +0.1, 굳음+이질 -0.2, pinned 1.0 short-circuit, blocked 0.0 short-circuit
  - 팔레트 ΔE 는 hex → LAB 변환 후 평균 LAB 사이 유클리드 (`numpy` 만, colormath 의존 안 함)
  - `format_why(result, pack_name)` — `"이 프로젝트가 <pack_name> 을 N회 채택했음"` / 첫 검색 시 `"이 프로젝트의 첫 검색 — 통일성 가중치는 다음 채택 이후 적용됩니다"`
- [ ] 테스트 — `pytest tests/test_consistency.py -v`

### C.3 UsageTracker

- [ ] `src/gah/core/usage_tracker.py` 신규
  - `ProjectUsageSummary` dataclass (store 와 공유; 한쪽에 둘지는 구현 시 결정 — 권장은 `store.py` 옆 `models.py` 신규 모듈 안 하고 `usage_tracker.py` 안)
  - `UsageTracker(store, config)` — `record_explicit` / `record_implicit_top1` / `summary`
  - `record_implicit_top1` 은 `config.implicit_top1_enabled=False` 면 None 반환 (noop)
  - 중복 방지: `last_query_top1_for_project` 가 같은 query_id 이고 이미 implicit 행 있으면 noop
- [ ] 테스트 — `pytest tests/test_usage_tracker.py -v`

### C.4 HybridSearcher

가장 큰 단위. 시간 배분 ~ 3~4 일.

- [ ] `src/gah/core/searchable.py` 수정 — `from_query(query: str, kind: str|None) -> str` 클래스 메서드 추가
  - 파일명·라벨 prefix 가 없는 짧은 텍스트만 임베딩용으로 빌드
- [ ] `src/gah/core/search.py` 신규
  - `LabelFilter` / `SearchRequest` / `ResultRow` / `SearchResults` dataclass
  - `HybridSearcher(store, embedder, consistency, registry, config)` 클래스
  - `hybrid(req: SearchRequest) -> SearchResults` 메서드 (M3_plan.md §3.5 의사코드 그대로)
  - 헬퍼 함수: `build_fts_match_expression(query)` (자유 쿼리만 — 라벨 부울은 SQL JOIN 으로 별도 처리), `normalize_minmax(values: np.ndarray) -> np.ndarray`, `label_match_score(asset_labels, labels_all, labels_any, labels_none) -> float`, `build_why(consistency_result, matched_labels, asset_meta) -> str`
  - `query_id` 발급은 `store.insert_search_query` 호출 후 반환된 ID
- [ ] 테스트 — `pytest tests/test_search.py -v`

### C.5 MCP 모델 + 도구 + 서버

- [ ] `src/gah/mcp/models.py` 신규 — 12 개 도구의 입출력 Pydantic 모델 (M3_plan.md §3.6 표 + DESIGN §6 참조)
  - `AxisLabel(axis: str, label: str)`
  - `Filters(tags_any=None, min_duration_ms=None, max_duration_ms=None, loopable=None)`
  - `FindAssetRequest` / `FindAssetResult(query_id, results: list[ResultDict])`
  - `SuggestPacksRequest` / `SuggestPacksResult`
  - `GetAssetRequest(asset_id: int | None = None, path: str | None = None)` (둘 중 하나 필수) / `GetAssetResult`
  - `ListAssetsRequest(pack_id=None, kind=None, page=1, page_size=50)` / `ListAssetsResult`
  - `ListPacksResult`
  - `RecordAssetUseRequest(project_id, asset_id, query_id=None, context=None)` / `RecordAssetUseResult(ok, usage_id)`
  - `SetProjectPinRequest(project_id, pinned_pack_id: int|None, blocked_pack_ids: list[int]=[])`
  - `RequestRescanRequest(pack_id=None, asset_id=None, all=False)` (정확히 하나 필수)
  - `ReportFeedbackRequest(query_id, asset_id, reason)`
  - `ListLabelsRequest(axis=None, enabled_only=True, with_description=True)` / `ListLabelsResult(labels, signature)`
  - `DescribeLabelRequest(axis, label)` / `DescribeLabelResult`
  - `model_config = ConfigDict(extra="forbid")` 일괄 적용
- [ ] `src/gah/mcp/tools.py` 신규 — 12 개 도구 함수
  - `ToolDeps(store, search, usage, registry, queue, config)` dataclass (모든 함수에 한 인자로 주입)
  - `tool_find_asset(deps, req)` / `tool_get_asset` / `tool_list_assets` / `tool_list_packs` / `tool_suggest_packs` / `tool_record_asset_use` / `tool_set_project_pin` / `tool_request_rescan` / `tool_report_feedback` / `tool_list_label_axes` / `tool_list_labels` / `tool_describe_label`
  - 모든 write 도구는 `with deps.store.write_lock:` 안에서 호출
  - 에러는 plan §3.9 의 에러 코드 표 그대로 (`{"error":{"code":"404_not_found","message":"..."}}`)
  - `request_rescan` 의 워커 없음 케이스: `deps.queue` 가 None 이면 `mark_asset_pending` 만 호출하고 `warnings=["no live worker; will be processed on next GUI startup"]` 반환
- [ ] `src/gah/mcp/server.py` 신규
  - `INSTRUCTIONS` 상수 — DESIGN §13.1 5단계 권장 흐름을 영어 한 문단으로 압축
  - `build_server(store, search, usage, registry, queue, config) -> FastMCP`
  - `register_all_tools(server, deps)` — 12 개 도구에 `@server.tool(...)` 데코레이터로 등록, 도구 description 은 한국어 한 줄
  - `run_stdio()` — logging stderr-only 셋업 + Config 로드 + Store/Registry/HybridSearcher/UsageTracker/AnalysisQueue(`None` 가능) 인스턴스 + `build_server` + `server.run(transport="stdio")`
  - KeyboardInterrupt 처리 — graceful shutdown (store.close)
- [ ] 테스트 — `pytest tests/test_mcp_models.py tests/test_mcp_tools.py tests/test_mcp_server_stdio.py -v`

### C.6 `--mcp` CLI 플래그

- [ ] `src/gah/__main__.py` 수정 — `args.mcp` 분기 채움
  ```python
  if args.mcp:
      from gah.mcp.server import run_stdio
      run_stdio()
      return 0
  ```
- [ ] 기존 "not implemented" / `print` 한 줄 제거
- [ ] 테스트 — `pytest tests/test_entrypoint.py::test_mcp_flag_calls_run_stdio -v`

### C.7 GUI 라이브러리 탭 검색 박스

- [ ] `src/gah/ui/library_view.py` 수정
  - 상단 `QLineEdit(placeholder=tr("자연어 검색…"))` 1 줄 + 결과 `점수` 컬럼 추가
  - `QTimer.singleShot(250, self._run_search)` 디바운스 (M2.1 `_flush_progress` 패턴)
  - `_run_search(query)`:
    - 빈 입력 → 기본 `LibraryModel` 복귀
    - 입력 → `self._searcher.hybrid(SearchRequest(query=query, count=20))` 호출 후 결과로 `SearchResultsModel` 교체
  - `set_searcher(searcher)` setter (app.py 가 주입)
  - 결과 행 우클릭 메뉴 `"원본 파일 위치 열기"` 1 액션 (Qt `QDesktopServices.openUrl`)
- [ ] `src/gah/app.py` 수정 — GUI 부트 흐름에 인스턴스 생성·주입 추가
  - `searcher = HybridSearcher(store, embedder, consistency=ConsistencyScorer(store, config), registry, config)`
  - `usage = UsageTracker(store, config)`
  - `main_window.library_view.set_searcher(searcher)` (또는 동등 주입 경로)
  - (MCP stdio 프로세스와는 무관 — 별도 프로세스가 자체적으로 위 인스턴스를 만든다)
- [ ] 테스트 — `pytest tests/test_library_search_ui.py -v`

### C.8 `docs/MCP_USAGE_GUIDE.md` 본격화

- [ ] `docs/MCP_USAGE_GUIDE.md` — stub 의 §1~§5 유지하면서 다음 추가
  - **§1.1** 도구 12 개 실응답 JSON 예시 (find_asset / suggest_packs / record_asset_use / list_labels / describe_label)
  - **§3.1** `signature` 캐시 무효화 시나리오 (사용자가 GUI 라벨 다이얼로그에서 추가/비활/description 변경 → 다음 `list_labels` 응답의 `signature` 가 바뀜 → 캐시 미스로 새로고침)
  - **§6** 에러 코드 표 (`400_invalid_input` / `404_not_found` / `403_remote_disabled` / `503_busy` / `503_no_worker`)
  - **§7** 통일성 가중치 튜닝 노트 (Config 슬라이더 / `consistency_weight_override` per-call / `pinned_pack_id` 강제)
  - **§8** Claude Code 권장 워크플로 (DESIGN §13.1 5단계 한국어 풀이)

각 묶음 마지막에 `pytest -q` 로 회귀 점검. 전체 묶음이 다 끝나면 합계 ≈ **331 passed** (M0/M1/M2/M2.1 221 + M3 신규 110) + 4 deselected (`clip_integration` 2 + `mcp_integration` 2).

## D. 검증

자동:

- [ ] `pytest -q` 전체 통과 (M0/M1/M2/M2.1 회귀 없음 + M3 신규 모두 PASS) — 약 331 passed, 4 deselected
- [ ] `pytest -m mcp_integration -v` (옵트인) — 2 케이스 통과 (실제 stdio subprocess)
- [ ] `pytest -m clip_integration -v` (옵트인, M2 회귀 보존) — 2 케이스 통과

수동 (메모리 `feedback_run_commands_directly.md` — 자동화 가능한 것은 Claude 가 PowerShell 로 직접 측정, GUI 시각 확인만 사용자):

- [ ] `python -m gah --mcp` 가 stdio 부팅 → JSON-RPC `initialize` 응답 1 라인 — *Claude 가 직접*
- [ ] `python -m gah --tray` + 별도 PowerShell 의 `python -m gah --mcp` 동시 기동 → `gah.log` 의 `database is locked` 0 건 — *Claude 가 직접*
- [ ] `record_asset_use` → 다음 `find_asset` 의 `score_breakdown.consistency` 가 0 → 양수 — *Claude 가 직접*
- [ ] `list_labels` 1회 → 라벨 1개 추가 → `list_labels` 재호출 → `signature` 달라짐 — *Claude 가 직접*
- [ ] `sqlite3 ...\metadata.db ".tables"` 가 `projects`/`asset_usage`/`search_queries` 포함 — *Claude 가 직접*
- [ ] **GUI 검색 박스** — 트레이의 메인 윈도우 라이브러리 탭에서 `"pixel art knight"` 입력 → 250ms 후 결과 그리드 갱신 + 첫 행에 점수 표시 — *사용자 수동 시각 확인*

수동 검증 절차 전체는 [`M3_verification.md`](./M3_verification.md) 에 PowerShell 한 줄씩 풀어 작성한다.

## E. M4 인계

- [ ] `milestones/M3_verification.md` 작성 — `pytest -v` 출력, 환경 한계, Claude 가 직접 측정한 자동 검증 결과 + 사용자 수동 검증 1 항목 결과
- [ ] `HANDOFF.md` 갱신
  - §1 한 줄 요약 — M3 완료 + 다음 M4 (검색 UX 풍부화)
  - §2 검증된 사실 — 331 passed 표
  - §3 환경 — `mcp` SDK 의존성 1줄 추가
  - §5 M4 시작 절차 — M3 plan/todo 를 템플릿 삼아 M4 작성 가이드 (라벨 부울 파서 / 다축 필터 UI / 가중치 슬라이더 / 저장된 검색)
  - §6 의도적으로 남겨둔 자리 — `suggest_packs.samples` / `cross_pack_filter` / `report_feedback` 페널티 학습 / 자동완성 / 다중 선택 등 (M3_plan §7 그대로)
- [ ] `CLAUDE.md` §2 진행 현황 표의 M3 상태 ✅ + §8 을 M4 안내로 교체
- [ ] `milestones/README.md` 의 마일스톤 표 갱신
- [ ] `docs/MCP_USAGE_GUIDE.md` 본격 가이드 확인 — stub 표시 없음, 5개 신규 섹션(§1.1/§3.1/§6/§7/§8) 모두 채워짐
- [ ] PR 머지 후 `feat/m3-search-mcp` 브랜치 삭제 (또는 사용자 결정 대기)
