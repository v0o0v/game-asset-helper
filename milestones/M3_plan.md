# M3 — 검색 백엔드 + 통일성 + MCP stdio (구현 계획)

> **에이전트 작업자에게**: 이 plan 은 한국어 마일스톤 표준 형식이다. 본 plan 을 그대로 따라 [`milestones/M3_todo.md`](./M3_todo.md) 의 체크리스트를 만들고, **테스트를 먼저 작성한 뒤** 구현으로 넘어간다. M2 사이클(red → green → verification)을 그대로 답습한다. 본 plan 은 사용자가 승인한 M3 설계안을 풀어쓴 것이며, 결정된 7 개 핵심 항목(가중치 공식·MCP stdio 라이프사이클·라벨 파서 M4 이연·벡터 풀스캔·FTS BM25 정규화·통일성 "굳음" 임계·MCP SDK)을 모듈·SQL·테스트 단위까지 1:1 로 옮긴다.

## 1. 목표

M2/M2.1 이 깔아둔 라벨·임베딩·FTS·통일성 입력(`packs.aggregate_meta`) 위에 **검색·통일성·MCP 서버**를 얹는다. M3 가 끝나면 다음 두 호출이 정상 동작한다.

1. **자연어 + 라벨 부울 필터 검색**

   ```jsonc
   find_asset({
     query: "전투 시 깔릴 빠르고 어두운 오케스트라 BGM, 1분 이내, 루프",
     kind: "sound",
     filters: { max_duration_ms: 60000, loopable: true },
     labels_all: [{axis:"sound_category", label:"bgm"}],
     labels_any: [
       {axis:"sound_mood",       label:"dark"},
       {axis:"sound_use",        label:"combat"},
       {axis:"sound_tempo",      label:"fast"},
       {axis:"sound_genre",      label:"orchestral"}
     ],
     project_id: "D:/Unity/MyGame",
     count: 5
   })
   ```

   → 상위 5개의 `(asset_id, score, score_breakdown, matched_labels, why, path, meta)` 응답. semantic 코사인 + FTS BM25 + 라벨 매칭 + 통일성 가중치가 합산된 단일 점수.

2. **MCP stdio 진입**

   ```powershell
   python -m gah --mcp
   ```

   → Claude Code 가 child process 로 spawn 할 수 있는 JSON-RPC stdio 서버. 12 개 도구를 노출하고, 동시에 떠 있는 `--tray` GUI 인스턴스와 같은 SQLite DB 를 안전하게 공유한다(M2.1 `write_lock` + SQLite `busy_timeout=5000`).

세부:

- **HybridSearcher** — FTS5 키워드 후보 + numpy 풀스캔 코사인 + 라벨 부울 매칭 + ConsistencyScorer 결합. 가중합 공식 `final = 0.40·semantic + 0.15·keyword + 0.20·label_match + 0.20·consistency + 0.05·recency` (합 1.00). `label_match=0` 케이스(라벨 미지정 자유 쿼리)에서도 다른 채널 재정규화 없음 — 의도적으로 max 0.80 으로 약화.
- **ConsistencyScorer** — DESIGN §4.6 표 그대로 코드화. 같은 팩/벤더/스타일/팔레트·굳음 페널티·`pinned_pack_id` 무조건 1.0.
- **UsageTracker** — `record_explicit` 명시 호출 + `record_implicit_top1` 암묵 추정(default off).
- **MCP 서버** — 공식 `mcp` 파이썬 SDK 의 `FastMCP` 데코레이터 스타일. stdio 단독 프로세스. 12 개 도구(검색 7 + 메타 3 + 운영 2). 도구별 입출력은 Pydantic 모델로 1:1 검증.
- **GUI 라이브러리 탭 검색 박스** — 최소 동작(디바운스 250ms, 결과 그리드 단순 정렬). 풍부 UX(필터 칩·가중치 슬라이더·저장된 검색)는 M4.
- **DB 마이그레이션** — `projects`, `asset_usage`, `search_queries` 3 테이블 신설. M0/M1/M2 의 14 객체 + 신규 3 + 인덱스 4 = 21 객체.

M3 가 끝나면 Claude Code 사용자는 GAH MCP 서버에 붙어 "스테이지1 BGM 짧고 경쾌하게 깔아줘" 같은 자연어 요청을 보낼 수 있고, 응답에는 채택 근거(`matched_labels` + `why` + `score_breakdown`) 가 포함된다. 같은 프로젝트에서 한 번 채택한 팩은 다음 검색에서 통일성 가중치로 우선 노출된다.

## 2. 산출물

### 2.1 코드 모듈

| 파일/디렉터리 | 책임 | 상태 |
|---|---|---|
| `pyproject.toml` (수정) | `mcp>=1.0` 의존성 추가(공식 Anthropic Python SDK). dev 그룹은 추가 없음 (`pytest-asyncio`/`respx` 재사용). | 수정 |
| `src/gah/config.py` (수정) | `Config` 에 M3 필드 8 개 추가 — 가중치 4(`weight_semantic=0.40`, `weight_keyword=0.15`, `weight_label_match=0.20`, `weight_consistency=0.20`, `weight_recency=0.05` — recency 까지 합 1.0), `consistency_locked_max_packs=2`, `consistency_locked_min_uses=5`, `implicit_top1_enabled=False`, `mcp_search_default_count=5` | 수정 |
| `src/gah/core/store.py` (수정) | `_M3_SCHEMA` 상수 추가 + `initialize()` 가 M1·M2·M3 세 스크립트 순차 실행. 신규 메서드: `upsert_project`, `set_project_pin`, `set_blocked_packs`, `project_usage_summary`, `record_asset_use`, `last_query_top1_for_project`, `insert_search_query`, `fts_search`, `semantic_candidates_load`, `asset_labels_for`, `pack_aggregate`, `recent_assets_score`, `asset_count_by_kind` | 수정 |
| `src/gah/core/consistency.py` | `ConsistencyScorer(store, config)` — `score_asset(project_id, asset_row, pack_aggregate, project_summary) -> ConsistencyResult` / `score_pack(project_id, pack_row, project_summary) -> ConsistencyResult` / `is_locked(project_summary) -> bool` / `format_why(result) -> str`. `ConsistencyResult` = `(score, signals: list[(name, value)], locked: bool)`. | 신규 |
| `src/gah/core/usage_tracker.py` | `UsageTracker(store, config)` — `record_explicit(project_id, asset_id, query_id, context, source='explicit')` / `record_implicit_top1(project_id, query_id)` (config 토글 확인) / `summary(project_id) -> ProjectUsageSummary`. `ProjectUsageSummary` = `(pack_uses: dict[pack_id,int], vendor_uses: dict[str,int], total_uses: int, distinct_packs: int, dominant_style: str|None, dominant_palette: list[str])`. | 신규 |
| `src/gah/core/search.py` | `HybridSearcher(store, embedder, consistency, registry, config)` — `hybrid(SearchRequest) -> SearchResults`. 단계: ① 후보 추출 (FTS MATCH + 라벨 부울 + filters + kind + pack scope) → ② semantic 후보 union (top-K coarse) → ③ per-channel 점수 산출 + min-max 정규화 → ④ 가중합 → ⑤ top-N + `score_breakdown` + `matched_labels` + `why` 빌더 → ⑥ `insert_search_query` 로 `query_id` 발급. `SearchRequest` / `SearchResults` 데이터클래스. | 신규 |
| `src/gah/core/searchable.py` (수정) | M2 의 `SearchableTexts.for_embed` 가 검색 쿼리에도 그대로 쓰이도록 클래스 메서드 `from_query(query: str, kind: str|None) -> str` 추가(파일명·라벨 prefix 가 없는 짧은 텍스트만 임베딩). | 수정 |
| `src/gah/mcp/__init__.py` | 패키지 마커 | 신규 |
| `src/gah/mcp/models.py` | 12 개 도구의 입출력 Pydantic 모델. DESIGN §6 + `docs/MCP_USAGE_GUIDE.md` 와 1:1. `AxisLabel`, `LabelFilter`, `Filters`, `FindAssetRequest`/`FindAssetResult`, `SuggestPacksRequest`/`SuggestPacksResult`, `GetAssetResult`, `ListAssetsRequest/Result`, `ListPacksResult`, `RecordAssetUseRequest/Result`, `SetProjectPinRequest`, `RequestRescanRequest`, `ReportFeedbackRequest`, `ListLabelAxesResult`, `ListLabelsRequest/Result`, `DescribeLabelRequest/Result` 등. | 신규 |
| `src/gah/mcp/tools.py` | 12 개 도구 함수 — 입력 검증 → store/search/usage/registry 호출 → 출력 직렬화. 모든 write 도구는 `store.write_lock` 내부에서 동작(단일 프로세스 자체 보호 + SQLite WAL 가 inter-process 보호). | 신규 |
| `src/gah/mcp/server.py` | `build_server(store, search, usage, registry, config) -> FastMCP` — `instructions` 필드에 표준 워크플로 한 문단(DESIGN §13.1 의 5단계 권장 흐름을 영어 한 문단으로 압축). `register_all_tools(server, deps)`. `run_stdio()` 엔트리. | 신규 |
| `src/gah/__main__.py` (수정) | `--mcp` 플래그가 `gah.mcp.server.run_stdio()` 호출. 현재 "not implemented" 라인 제거. 로깅은 stderr 만(stdio 가 stdout 점유). | 수정 |
| `src/gah/app.py` (수정) | GUI 부트 경로에 `HybridSearcher`/`ConsistencyScorer`/`UsageTracker` 인스턴스 생성 후 `MainWindow` 에 주입. MCP stdio 프로세스와는 무관(별도 프로세스). | 수정 |
| `src/gah/ui/library_view.py` (수정) | 상단 `QLineEdit` 검색 박스 + 250ms 디바운스(M2.1 `_flush_progress` 패턴 답습). 입력이 비면 기본 목록 복귀, 입력이 있으면 `HybridSearcher.hybrid()` 호출 후 결과로 모델 교체. 결과 행 우클릭 메뉴 `"원본 파일 위치 열기"` 1 항목만(나머지는 M4). | 수정 |
| `docs/MCP_USAGE_GUIDE.md` (수정) | stub → 본격 가이드. 12 개 도구 실 응답 JSON, `signature` 캐시 무효화 시나리오, 통일성 가중치 튜닝 노트, 에러 코드(`503_busy`, `404_not_found`, `400_invalid_input`, `403_remote_disabled`), Claude Code 권장 워크플로(§13). | 수정 |
| `milestones/M3_todo.md` | TDD 체크리스트(이 plan 의 §3 작업 단위를 1:1 매핑) | 신규 |
| `milestones/M3_verification.md` | M3 끝에 작성 — 자동 `pytest -v` 결과 + 사용자 수동 검증 항목 + 알려진 한계 | 신규 |

### 2.2 테스트

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_store_m3.py` | ~16 | M3 신규 3 테이블 생성 + idempotent + cascade delete + `upsert_project` 중복 idempotent + `record_asset_use` + `project_usage_summary` 집계 + `set_project_pin` + `set_blocked_packs` JSON 왕복 + `insert_search_query` + `fts_search` 가 라벨 prefix `label:bgm` 매칭 + `semantic_candidates_load` BLOB → numpy 왕복 + `pack_aggregate` JSON 디코드 |
| `tests/test_consistency.py` | ~12 | §4.6 표 모든 행 — 같은 팩 +0.6 / 같은 벤더 +0.3 / 스타일 일치 +0.2 / 팔레트 ΔE 임계 + / 굳음 페널티 -0.2 / 클램프 0..1 / `pinned_pack_id` 무조건 1.0 / `is_locked` 임계(`distinct≤2 AND uses≥5`) / 첫 검색(이력 0) → 0 / blocked pack → 점수 0 강제 / `format_why` 한국어 한 줄 |
| `tests/test_usage_tracker.py` | ~8 | explicit 정상 기록 + implicit 토글 off 시 noop + implicit on 시 직전 query 의 top1 만 마킹 + 같은 query_id 중복 방지 + summary 정확성 + 빈 프로젝트 summary 디폴트 + `pack_uses` 정렬 |
| `tests/test_search.py` | ~20 | 가중합 공식 정확성 + 각 채널 min-max 정규화 + 후보 1개일 때 keyword=0 / semantic=1 / consistency 단독 작동 + 라벨 부울 all/any/none + `force_pack_id` scope + `exclude_pack_ids` 필터 + `prefer_pack_id` 보너스 +0.3 + `kind` 필터 + `matched_labels` 반환 + `why` 한 줄 생성 + 빈 후보 → 빈 응답 + `score_breakdown` 합 = `score` (오차 1e-4 이내) + `query_id` 발급 + `search_queries` insert + label_match=0 일 때 다른 채널 재정규화 없음(설계 §A.1 결정) |
| `tests/test_mcp_models.py` | ~10 | 12 개 도구 모델 — 필수/옵셔널 필드 + 화이트리스트 enum(`kind`, `mode`, `source`) + 누락 시 ValidationError + extra 필드 거부 + `AxisLabel` 파서 |
| `tests/test_mcp_tools.py` | ~22 | 각 도구 정상 호출 1 + 잘못된 입력 reject 1 (= 12*~1.8 ≈ 22). 추가: `record_asset_use` 후 다음 `find_asset` 의 consistency 점수가 양수, `list_labels` 응답에 `signature` 포함, `request_rescan` 이 `AnalysisQueue.enqueue_pack` 호출, `set_project_pin` 후 `find_asset` 1순위가 그 팩 |
| `tests/test_mcp_server_stdio.py` | ~6 | `build_server` 가 `FastMCP` 인스턴스 반환 + `instructions` 비어 있지 않음 + 12 개 도구 모두 등록 + 도구별 description 포함 + `run_stdio` 가 KeyboardInterrupt 에 graceful + 에러 도구 호출이 typed error 반환 |
| `tests/test_library_search_ui.py` | ~5 | 빈 입력 시 기본 라이브러리 모델 / 입력 후 250ms 안에 호출 X (디바운스) / 250ms 경과 후 1회 호출 / 결과 그리드가 응답 갱신 / 입력 다시 비우면 기본 복귀. offscreen Qt |
| `tests/test_config_m3.py` | ~6 | 신규 8 필드 기본값 + TOML 왕복 + 가중치 합 ≈ 1.0 검증 + `implicit_top1_enabled=False` 기본 + `consistency_locked_*` 정수 검증 + `mcp_search_default_count` 1..50 범위 |
| `tests/test_mcp_integration.py` (옵트인 mark `mcp_integration`) | ~2 | 실제 stdio subprocess spawn → JSON-RPC `initialize` 핸드셰이크 → `tools/list` 응답 12 개 + `list_labels` 호출. `clip_integration` 처럼 `addopts = -m "not mcp_integration and not clip_integration"` 로 기본 deselect |

**합계 ~94 신규 케이스 + 옵트인 2.** 기존 M0(18) + M1(49) + M2(134) + M2.1(16) + 회귀 보존(+4) = 221 + M3 ~94 = **목표 ≈ 315 통과**(active) + 4 deselected(`clip_integration` 2 + `mcp_integration` 2).

## 3. 작업 단위와 책임

작업은 순서대로 진행한다(앞 단위가 뒤 단위의 빌딩 블록). 각 단위는 **테스트 먼저 → 구현 → 통과 → 커밋** 사이클을 지킨다.

### 3.1 mcp SDK 의존성 검증 (선행 스파이크, ≤ 0.5일)

본격 작업 전 한 번의 외부 검증:

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
pip install "mcp>=1.0"
python -c "from mcp.server.fastmcp import FastMCP; s = FastMCP('test'); print(s)"
```

검증 항목:

- 최신 안정 버전 확인(`pip index versions mcp` 또는 PyPI 페이지).
- `FastMCP` 임포트 성공.
- `@server.tool()` 데코레이터로 단순 함수 등록 가능.
- `server.run(transport="stdio")` (또는 `server.run_stdio()`) 가 hang 없이 부팅 — `echo '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' | python -m ...` 로 라인 1 응답 확인.

결과를 `pyproject.toml` 에 핀(예: `mcp>=1.0,<2.0`). API 가 0.x 와 다르면 plan §2.1 의 `mcp/server.py` 시그니처를 그 결과에 맞춰 한 번 수정.

> **폴백**: 만약 SDK 가 stdio 에서 불안정하거나 의존성 충돌이 있으면 직접 JSON-RPC 핸들러(`asyncio.StreamReader/Writer` + `json` 표준 라이브러리) 로 구현. 추가 비용 ~0.5주. 도구 함수 자체(시그니처 + 입출력 모델) 는 SDK 와 무관하게 동일하게 재사용.

### 3.2 `core/store.py` 마이그레이션 + 신규 메서드

기존 `_SCHEMA`, `_M2_SCHEMA` 는 그대로 두고 `_M3_SCHEMA` 를 추가. `initialize()` 가 셋을 순차 실행. 모두 `IF NOT EXISTS` 라 기존 사용자 DB 에 적용해도 안전.

```sql
-- _M3_SCHEMA
CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER PRIMARY KEY,
  external_id     TEXT NOT NULL UNIQUE,
  display_name    TEXT,
  first_seen      INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  pinned_pack_id  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  blocked_packs   TEXT                     -- JSON array of pack_id (or NULL)
);

CREATE TABLE IF NOT EXISTS asset_usage (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  pack_id     INTEGER NOT NULL,            -- 비정규화 (DESIGN §5.1)
  used_at     INTEGER NOT NULL,
  source      TEXT NOT NULL,               -- 'explicit'|'implicit_top1'|'manual'
  context     TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_project ON asset_usage(project_id, used_at);
CREATE INDEX IF NOT EXISTS idx_usage_pack    ON asset_usage(project_id, pack_id);

CREATE TABLE IF NOT EXISTS search_queries (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  query_text   TEXT NOT NULL,
  results_json TEXT NOT NULL,              -- 상위 N의 (asset_id, score)
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_queries_project ON search_queries(project_id, created_at);
```

`Store` 에 추가하는 메서드(모두 `write_lock` 안에서 동작하는 write 와 lock 무관 read 로 구분):

write:
- `upsert_project(external_id, display_name=None) -> ProjectRow` — `INSERT ... ON CONFLICT(external_id) DO UPDATE SET last_seen=?, display_name=COALESCE(?,display_name)`. 반환은 갱신된 행 전체.
- `set_project_pin(project_id, pinned_pack_id: int | None) -> None`
- `set_blocked_packs(project_id, pack_ids: list[int]) -> None` — JSON 직렬화.
- `record_asset_use(project_id, asset_id, pack_id, source, context=None) -> int` — 누적 INSERT, usage_id 반환.
- `insert_search_query(project_id, query_text, results: list[tuple[int,float]]) -> int` — query_id 반환.

read:
- `get_project(external_id) -> ProjectRow | None`
- `project_usage_summary(project_id) -> ProjectUsageSummary` — `pack_uses` 집계 + 가장 많이 쓴 팩의 `aggregate_meta` 에서 `main_style`/`palette` 추출.
- `last_query_top1_for_project(project_id, within_seconds=3600) -> tuple[int,int] | None` — `(query_id, asset_id)`. implicit top1 추정 입력.
- `fts_search(query: str, *, kind: str|None, pack_id: int|None, exclude_pack_ids: list[int], k: int=200) -> list[tuple[int, float]]` — `(asset_id, raw_bm25)`. BM25 부호 뒤집기는 caller 책임.
- `semantic_candidates_load(asset_ids: list[int] | None = None) -> tuple[list[int], np.ndarray, str]` — `asset_ids` 가 주어지면 그 집합만, 없으면 전체. `(ids, matrix[N×dim] float32, model_id)`. dim/model 모두 첫 행 기준 일관성 검증.
- `asset_labels_for(asset_ids: list[int]) -> dict[int, list[LabelScore]]`
- `pack_aggregate(pack_id) -> dict | None` — `packs.aggregate_meta` JSON 디코드.
- `recent_assets_score(asset_ids: list[int], window_seconds: int=2592000) -> dict[int, float]` — `analyzed_at` 기준 0..1 (지수 감쇠). `analyzed_at` NULL 인 행은 `added_at` 으로 폴백, 그것도 NULL 이면 현재 시간으로 폴백(점수 1.0).
- `asset_count_by_kind(pack_id: int|None=None) -> dict[str,int]` — `list_packs` 응답용.

`AssetRow` 에 추가 필드 없음 (M2 시점 그대로). `ProjectRow` 신규 데이터클래스(같은 store.py 안).

테스트(`tests/test_store_m3.py`):

- `test_initialize_creates_m3_tables`
- `test_initialize_is_idempotent_with_m1_m2_tables`
- `test_upsert_project_returns_row_with_id`
- `test_upsert_project_updates_last_seen_on_second_call`
- `test_set_project_pin_persists`
- `test_set_blocked_packs_json_roundtrip`
- `test_record_asset_use_increments_usage_count`
- `test_project_usage_summary_aggregates_pack_and_vendor`
- `test_project_usage_summary_empty_project_returns_defaults`
- `test_last_query_top1_returns_none_when_no_query`
- `test_last_query_top1_returns_recent_only`
- `test_insert_search_query_persists_json`
- `test_fts_search_matches_label_prefix` — `label:bgm` 토큰 인덱싱
- `test_fts_search_excludes_blocked_packs`
- `test_semantic_candidates_load_blob_roundtrip` — bytes ↔ numpy 정확
- `test_asset_labels_for_returns_all_axes_per_asset`
- `test_pack_aggregate_decodes_json`
- `test_recent_assets_score_within_zero_one`
- `test_delete_project_cascades_usage_and_queries`

### 3.3 `core/consistency.py`

데이터클래스:

```python
@dataclass(frozen=True)
class ConsistencyResult:
    score: float                       # 0..1 클램프
    signals: list[tuple[str, float]]   # [("same_pack_used", 0.6), ("vendor_same", 0.3), ...]
    locked: bool                       # is_locked(summary) 결과
```

API:

```python
class ConsistencyScorer:
    def __init__(self, store: Store, config: Config) -> None: ...
    def is_locked(self, summary: ProjectUsageSummary) -> bool:
        # config.consistency_locked_max_packs 이하 distinct 이면서
        # config.consistency_locked_min_uses 이상 누적이면 True
        ...
    def score_asset(self, project_id: int, asset: AssetRow,
                    pack_aggregate: dict, summary: ProjectUsageSummary,
                    blocked_packs: set[int], pinned_pack_id: int|None) -> ConsistencyResult: ...
    def score_pack(self, project_id: int, pack: PackRow,
                    summary: ProjectUsageSummary,
                    blocked_packs: set[int], pinned_pack_id: int|None) -> ConsistencyResult: ...
    def format_why(self, result: ConsistencyResult, pack_name: str) -> str:
        # "이 프로젝트가 Kenney Platformer Redux 를 12회 채택했음" 같은 한 줄
        ...
```

점수 산정(§4.6 표 그대로):

| 신호 | 가중 | 조건 |
|---|---:|---|
| 같은 팩 사용 이력 | +0.6 | `summary.pack_uses[pack_id] >= 1` |
| 같은 벤더 사용 이력 | +0.3 | `summary.vendor_uses[vendor] >= 1` AND 같은 팩 아님 |
| 스타일 일치 | +0.2 | `summary.dominant_style == pack_aggregate["main_style"]` |
| 팔레트 근접 | +0.1 | `summary.dominant_palette` 와 `pack_aggregate["palette"]` 의 평균 ΔE ≤ Config.palette_delta_e_threshold(기본 30) |
| 굳음 + 이질 팩 | -0.2 | `is_locked(summary) AND pack_id ∉ summary.pack_uses` |
| `pinned_pack_id == pack_id` | 강제 1.0 | 점수 1.0 으로 short-circuit |
| `pack_id ∈ blocked_packs` | 강제 0.0 | 점수 0.0 으로 short-circuit + `signals=[("blocked", -1)]` |

ΔE 는 hex 컬러 5개를 LAB 공간 평균으로 변환 후 두 평균 LAB 사이의 유클리드. M2 의 `numpy` 만으로 충분(별도 colormath 의존성 안 함).

테스트(`tests/test_consistency.py`):

- `test_first_search_no_history_returns_zero_score`
- `test_same_pack_used_grants_06`
- `test_same_vendor_different_pack_grants_03`
- `test_style_match_adds_02`
- `test_palette_close_under_threshold_adds_01`
- `test_palette_far_above_threshold_no_bonus`
- `test_locked_project_with_foreign_pack_gets_minus_02`
- `test_pinned_pack_short_circuits_to_one`
- `test_blocked_pack_short_circuits_to_zero`
- `test_score_clamps_to_zero_one_range`
- `test_is_locked_threshold_exactly_at_min_uses`
- `test_format_why_includes_use_count`

### 3.4 `core/usage_tracker.py`

```python
@dataclass(frozen=True)
class ProjectUsageSummary:
    pack_uses: dict[int, int]            # {pack_id: count}
    vendor_uses: dict[str, int]
    total_uses: int
    distinct_packs: int
    dominant_style: str | None
    dominant_palette: list[str]          # 가장 많이 쓴 팩의 aggregate_meta.palette 차용

class UsageTracker:
    def __init__(self, store: Store, config: Config) -> None: ...
    def record_explicit(self, project_id: int, asset_id: int,
                        query_id: int|None, context: str|None) -> int: ...
    def record_implicit_top1(self, project_id: int, query_id: int) -> int | None:
        # config.implicit_top1_enabled 가 False 면 None.
        # last_query_top1_for_project 가 같은 query_id 이면 noop (중복 방지).
        ...
    def summary(self, project_id: int) -> ProjectUsageSummary: ...
```

테스트(`tests/test_usage_tracker.py`):

- `test_record_explicit_returns_usage_id`
- `test_record_explicit_with_query_id_sets_source_explicit`
- `test_implicit_off_returns_none`
- `test_implicit_on_records_top1_of_last_query`
- `test_implicit_does_not_duplicate_for_same_query_id`
- `test_summary_empty_project_has_zero_total`
- `test_summary_aggregates_correctly_after_two_uses`
- `test_summary_dominant_style_picks_most_used_packs_style`

### 3.5 `core/search.py` (가장 큰 단위)

데이터클래스:

```python
@dataclass(frozen=True)
class LabelFilter:
    axis: str
    label: str

@dataclass(frozen=True)
class SearchRequest:
    query: str
    kind: str | None = None             # 'sprite'|'spritesheet'|'sound'
    count: int = 5
    project_id: str | None = None       # external_id
    prefer_pack_id: int | None = None
    force_pack_id: int | None = None
    exclude_pack_ids: list[int] = field(default_factory=list)
    consistency_weight_override: float | None = None
    filters: dict = field(default_factory=dict)
    labels_all: list[LabelFilter] = field(default_factory=list)
    labels_any: list[LabelFilter] = field(default_factory=list)
    labels_none: list[LabelFilter] = field(default_factory=list)
    label_match_weight_override: float | None = None

@dataclass(frozen=True)
class ResultRow:
    asset_id: int
    pack_id: int
    pack_name: str
    path: str
    score: float
    score_breakdown: dict[str, float]   # semantic/keyword/label_match/consistency/recency
    matched_labels: list[dict]          # [{axis, label, source, score}]
    why: str
    meta: dict

@dataclass(frozen=True)
class SearchResults:
    query_id: int
    results: list[ResultRow]
```

알고리즘 (`HybridSearcher.hybrid`):

```
1. project_row = store.upsert_project(req.project_id) if req.project_id else None
2. summary = usage.summary(project_row.id) if project_row else empty
3. # ---------- 후보 집합 추출 ----------
   keyword_query = build_fts_match_expression(req.query, req.labels_all/any/none, kind)
   fts_candidates = store.fts_search(keyword_query, kind=req.kind, pack_id=req.force_pack_id,
                                     exclude_pack_ids=blocked_union(req, project_row), k=200)
   query_vec = embedder.encode(searchable.from_query(req.query, req.kind))
   sem_ids, sem_matrix, _ = store.semantic_candidates_load(asset_ids=None)
   sem_scores = cosine(query_vec, sem_matrix)        # numpy 1번 곱
   sem_top_k = top_k(sem_ids, sem_scores, 200)
   candidates = union(fts_candidates_ids, sem_top_k_ids) ∩ scope(req)
4. # ---------- 채널별 점수 ----------
   semantic[i]  = sem_scores[i] if i in sem_top_k else fallback
   keyword[i]   = normalize_minmax(-bm25)            # 부호 뒤집기
   label_match[i] = label_match_score(labels[i], req.labels_*)
   consistency[i] = consistency.score_asset(project, assets[i], pack_aggregates[i], summary, blocked, pinned).score
   recency[i]   = recent_assets_score[i]
5. # ---------- 가중합 ----------
   final[i] = w_sem*sem + w_kw*kw + w_label*label_match + w_cons*cons + w_rec*rec
   (label_match=0 일 때도 다른 항 재정규화 없음 — 라벨 미지정 자유 쿼리는 의도적으로 약함)
6. # ---------- prefer/force/pinned 보정 ----------
   if req.prefer_pack_id: bonus +0.3 in scope
   if pinned_pack_id == pack_id_of(i): bonus +0.5 (consistency 1.0 이 이미 끌어올림)
7. # ---------- top-N + 응답 빌드 ----------
   top = sorted(final, desc)[:req.count]
   for each:
      matched_labels = filter(labels[i], req.labels_*)
      why = build_why(consistency_result, matched_labels, asset_meta)
   query_id = store.insert_search_query(project_row.id if project_row else None,
                                       req.query, [(r.asset_id, r.score) for r in top])
   return SearchResults(query_id, [...])
```

`label_match_score` 정의:

```
required = labels_all (모두 만족 못하면 0)
score = (
   matched_count(labels_all) / max(len(labels_all),1) * 0.5
 + matched_count(labels_any) / max(len(labels_any),1) * 0.4
 + (1 if no labels_none matched else 0) * 0.1
)
# labels_all/any/none 모두 비어 있으면 0.
```

`build_fts_match_expression` 정책:

- 자유 쿼리는 `MATCH ? ` 의 ? 로 그대로 (FTS5 가 알아서 토큰).
- 라벨 필터는 별도 SQL clause 로 풀어 `WHERE asset_id IN (SELECT asset_id FROM asset_labels WHERE ...)` JOIN 으로 처리 — FTS5 의 `label:` prefix 매칭은 M2 검증에서 콜론 토크나이저 이슈가 있을 수 있으므로 보수적으로 JOIN.

테스트(`tests/test_search.py`):

- `test_hybrid_returns_topn_sorted`
- `test_score_breakdown_sums_to_score_within_tolerance`
- `test_empty_candidates_returns_empty_results`
- `test_labels_all_filters_out_non_matching`
- `test_labels_any_unions_matches`
- `test_labels_none_excludes_matches`
- `test_force_pack_id_restricts_scope`
- `test_exclude_pack_ids_removes_candidates`
- `test_prefer_pack_id_adds_bonus`
- `test_pinned_pack_id_is_first`
- `test_blocked_pack_excluded_even_if_high_semantic`
- `test_kind_filter_sprite_only`
- `test_matched_labels_contain_axis_label_source_score`
- `test_why_includes_consistency_phrase_when_consistency_positive`
- `test_query_id_persisted_in_search_queries`
- `test_min_max_normalization_handles_single_candidate`
- `test_label_match_zero_does_not_renormalize_other_channels`
- `test_consistency_override_weight_applied`
- `test_fake_embedder_used_for_unit_tests`
- `test_recent_asset_gets_higher_recency_score`

테스트 인프라:

- `tests/conftest.py` 에 `fake_embedder` 픽스처 — 입력 텍스트의 sha256 → 결정적 fake 768d 벡터. 라벨 description 과 쿼리가 같은 공간에서 비교되도록 동일 인코더 사용.
- `populated_store` 픽스처 — 2 팩 × 3 자산 × (라벨 5 + 임베딩 + 메타) seed 헬퍼.

### 3.6 `mcp/models.py` + `mcp/tools.py` + `mcp/server.py`

도구 12 개 목록과 시그니처:

| 도구 | 입력 모델 | 출력 모델 | 비고 |
|---|---|---|---|
| `find_asset` | `FindAssetRequest` | `FindAssetResult` | DESIGN §6.1 + `labels_*` 확장 |
| `get_asset` | `GetAssetRequest(asset_id|path)` | `GetAssetResult` | 단일 조회 |
| `list_assets` | `ListAssetsRequest(pack_id?, kind?, page, page_size)` | `ListAssetsResult` | 디버깅·탐색 |
| `list_packs` | (none) | `ListPacksResult` | DESIGN §6.4 |
| `suggest_packs` | `SuggestPacksRequest` | `SuggestPacksResult` | DESIGN §6.5 (M3 는 핵심만; samples 단순) |
| `record_asset_use` | `RecordAssetUseRequest` | `RecordAssetUseResult` | DESIGN §6.7 |
| `set_project_pin` | `SetProjectPinRequest` | `{ok:bool}` | DESIGN §6.8 |
| `request_rescan` | `RequestRescanRequest(pack_id|asset_id|all)` | `{enqueued:int}` | DESIGN §6.9, M2.1 `enqueue_pack`/`enqueue_asset` 호출. GUI 인스턴스 없으면 빈 큐만 채워둠(GUI 가 다음에 켜질 때 처리) — `--mcp` 단독 실행 시는 `503_no_worker` 반환할지 결정: **권장은 enqueue 만 하고 OK 반환**(다음 GUI 부팅에서 픽업), `warnings` 필드에 "no live worker" |
| `report_feedback` | `ReportFeedbackRequest` | `{ok:bool}` | DESIGN §6.10, v1 단순 로그 + `search_queries` 갱신 |
| `list_label_axes` | (none) | `{axes: [str]}` | `LabelRegistry.list_axes()` |
| `list_labels` | `ListLabelsRequest(axis?, enabled_only=true, with_description=true)` | `ListLabelsResult(labels: [...], signature: str)` | `LabelRegistry.list_labels()` + `label_catalog_signature()` |
| `describe_label` | `DescribeLabelRequest(axis, label)` | `DescribeLabelResult(axis, label, description, sample_assets:[...])` | sample 은 `asset_labels` JOIN top-3 |

`mcp/server.py`:

```python
INSTRUCTIONS = """\
GAH MCP server. Use this server to find and adopt 2D sprites, sheets, and sounds for game projects.

Recommended workflow:
1. Session start: call list_labels(with_description=true) once; cache by `signature`.
2. User request: call suggest_packs(query, project_id, kind) to let the user pick a pack.
3. Pick: call find_asset(query, project_id, force_pack_id=<picked>, count=N).
4. Adoption: after copying a file to the project, call record_asset_use(asset_id, project_id, query_id).
5. Rejection: call report_feedback(query_id, asset_id, reason).
Always pass the same project_id throughout a session — consistency scoring depends on it.
"""

def build_server(store, search, usage, registry, queue, config) -> FastMCP:
    server = FastMCP("game-asset-helper", instructions=INSTRUCTIONS)
    register_all_tools(server, deps=ToolDeps(store, search, usage, registry, queue, config))
    return server

def run_stdio() -> None:
    # ① logging_setup() with stderr-only handler
    # ② Config 로드
    # ③ Store/LabelRegistry/HybridSearcher/UsageTracker/AnalysisQueue(없으면 None) 인스턴스
    # ④ server = build_server(...); server.run(transport="stdio")
    ...
```

테스트:

- `tests/test_mcp_models.py` — 각 모델 한 케이스로 valid/invalid (총 ~10).
- `tests/test_mcp_tools.py` — 각 도구 함수에 fake deps 주입 후 호출. write 도구는 `store.write_lock` 이 acquire/release 되는지 spy. 핵심 시나리오:
  - `test_find_asset_returns_results_with_query_id`
  - `test_find_asset_rejects_invalid_kind`
  - `test_record_asset_use_persists_and_affects_next_consistency`
  - `test_set_project_pin_persists`
  - `test_request_rescan_enqueues_pack_and_returns_count`
  - `test_request_rescan_without_queue_returns_warning`
  - `test_list_labels_includes_signature`
  - `test_list_labels_signature_changes_after_add`
  - `test_describe_label_returns_top3_samples`
  - `test_suggest_packs_returns_pack_score_breakdown`
  - `test_list_packs_includes_asset_counts`
  - `test_get_asset_by_path_finds_row`
  - `test_get_asset_404_when_missing` (typed error)
- `tests/test_mcp_server_stdio.py` — `build_server` 가 12 도구 등록 + `instructions` 포함 + `run_stdio` Ctrl-C 처리. (실 subprocess 테스트는 `mcp_integration` 마크로 옵트인)

### 3.7 `--mcp` CLI 플래그

`src/gah/__main__.py` 의 기존 "not implemented" 가지를 채움:

```python
if args.mcp:
    from gah.mcp.server import run_stdio
    run_stdio()
    return 0
```

로깅: `logging_setup(stderr_only=True)` 로 stdout 방해 안 함. 데이터 디렉터리는 `--data-dir` 지원 그대로.

테스트(`tests/test_entrypoint.py` 확장):

- `test_mcp_flag_calls_run_stdio` — `run_stdio` 를 monkeypatch 로 가로채 호출 검증.

### 3.8 GUI 라이브러리 탭 검색 박스

`src/gah/ui/library_view.py` 수정:

- 상단에 `QLineEdit(placeholder=tr("자연어 검색…"))` 1 줄.
- `QTimer.singleShot(250, ...)` 으로 디바운스(M2.1 `_flush_progress` 패턴 답습 — 헬퍼 추출은 안 함, 일단 viewport-local).
- `_run_search(query)` — 빈 입력이면 기본 모델 복귀, 아니면 `searcher.hybrid(SearchRequest(query=query))` 호출 후 `ResultsModel` 로 교체.
- 결과 모델은 기존 `LibraryModel` 의 컬럼(`경로`/`종류`/`팩`/`상태`/`라벨`/`설명`) + 끝에 `점수` 컬럼 1 개 추가. `tr()` 래핑.

테스트(`tests/test_library_search_ui.py`):

- offscreen Qt (`pytest-qt` 없이 `QT_QPA_PLATFORM=offscreen` 환경변수). `QApplication` 부트 + 위젯 직접 조작.
- 5 케이스 §2.2 표 참고.

### 3.9 `docs/MCP_USAGE_GUIDE.md` 본격화

stub 의 §1~§5 를 유지하면서 다음을 추가:

- **§1.1** — 도구 12 개의 실 응답 JSON 예시 (find_asset / suggest_packs / record_asset_use / list_labels / describe_label).
- **§3.1** — `signature` 캐시 무효화 시나리오 (사용자가 GUI 라벨 다이얼로그에서 추가/비활/description 변경 → 다음 `list_labels` 응답의 `signature` 가 바뀜 → 캐시 미스로 새로고침).
- **§6** — 에러 코드 표.

  | 코드 | 의미 | 발생 |
  |---|---|---|
  | `400_invalid_input` | Pydantic 검증 실패 | 도구 호출 시 |
  | `404_not_found` | `asset_id`/`path`/`pack_id` 미존재 | get_asset / set_project_pin |
  | `403_remote_disabled` | `mode=cache_and_remote` 인데 비공식 경로 비활성 | sync_unity_asset_store (M6) |
  | `503_busy` | SQLite busy_timeout 초과 | 모든 write 도구 |
  | `503_no_worker` | `request_rescan` 호출 시 enqueue 만 되고 활성 워커 없음 | request_rescan |

- **§7** — 통일성 가중치 튜닝 노트 (Config 슬라이더 / `consistency_weight_override` per-call / `pinned_pack_id` 강제).
- **§8** — Claude Code 권장 워크플로 (DESIGN §13 의 시나리오 5단계 한국어).

## 4. 외부 의존성

| 패키지 | 용도 | 비고 |
|---|---|---|
| `mcp>=1.0,<2.0` | MCP 공식 Python SDK | `FastMCP` 데코레이터 스타일 + stdio transport. 정확한 버전 핀은 §3.1 스파이크 결과로 결정 |

기존 의존성(M2 까지) 은 그대로. dev 그룹 추가 없음 — `pytest-asyncio`/`respx` 모두 재사용. MCP stdio subprocess 테스트도 표준 `subprocess.Popen` 으로 충분.

torch / open_clip / Pillow / librosa 는 M3 가 직접 호출하지 않지만 `gah.core.embedding`/`gah.core.searchable` 이 같은 인코더를 검색 쿼리 임베딩에 사용한다(분석 시 사용한 `nomic-embed-text` 와 동일).

## 5. 테스트 전략

### 5.1 테스트 fixture

새 fixture 추가:

- `populated_store` (`tests/conftest.py`) — 2 팩(`pack_a`, `pack_b`) × 3 자산 × 분석 완료 상태로 seed. 각 자산은 라벨 5개(2축) + 임베딩 + sprite_meta 또는 sound_meta. 통일성 검증을 위해 `pack_a` 의 `aggregate_meta` 에 `main_style=pixel_art` + `palette=["#aabbcc",...]` 미리 박음.
- `fake_embedder` — sha256 기반 결정적 fake 인코더(384d 또는 768d 모두 OK; 테스트 일관성만 확보). M2 의 `EmbeddingEncoder` 인터페이스 만족.
- `consistency_summary_factory` — `ProjectUsageSummary` 즉석 빌더.
- `inline_mcp_server` (`tests/test_mcp_server_stdio.py`) — `build_server(deps)` 결과의 `tools` 디스크립터를 직접 검사. subprocess spawn 안 함 (그건 `mcp_integration` 마크 별도 도구).

기존 fixture(`fixture_dir`, `mock_ollama`, `fake_clip_backend`) 는 M3 단위 테스트에서 거의 사용 안 함.

### 5.2 단위 테스트 목록 (요약 — 상세 §2.2 + §3 의 각 단위)

위 §2.2 표가 단일 출처. 총 ~94 active + 2 opt-in.

### 5.3 테스트 인프라

- `pyproject.toml` 의 `addopts` 를 `-ra -m 'not clip_integration and not mcp_integration'` 로 확장. `markers` 에 `mcp_integration` 추가.
- subprocess 테스트는 `python -m gah --mcp --data-dir <tmp>` 로 격리 데이터 디렉터리. JSON-RPC 1 라인 핸드셰이크 후 `tools/list` 1 회 호출 + 종료. 타임아웃 10초.
- 임시 SQLite 는 기존 `store` 픽스처 재사용. M3 마이그레이션은 같은 `initialize()` 가 흡수.

### 5.4 검증 기준 (Definition of Done)

1. `pytest -q` 전체 통과 — M0(18) + M1(49) + M2(134) + M2.1(16) + 회귀 보존(+4) + M3 신규 **~94** = 합계 **약 315 active**. `clip_integration` 2 + `mcp_integration` 2 = 4 deselected.
2. M0/M1/M2/M2.1 회귀 0 건.
3. PowerShell 수동 검증 (§5.5):
   - `python -m gah --mcp` 가 stdio 부팅 → JSON-RPC `initialize` 응답 → `tools/list` 가 12개.
   - 같은 PC 에서 `python -m gah --tray` 와 `python -m gah --mcp` 가 동시에 떠도 SQLite lock 에러 0 건.
   - GUI 라이브러리 탭의 검색 박스에 `"pixel art knight"` 입력 → 250ms 후 결과 그리드 갱신 + 첫 행에 점수 표시.
   - `find_asset` 호출 후 `record_asset_use` 호출 → 다음 `find_asset` 의 `score_breakdown.consistency` 가 0 → 양수로 전이.
4. `docs/MCP_USAGE_GUIDE.md` 가 stub 표시 없이 12 도구 실응답 JSON 예시 + 에러 코드 표 + 캐시 무효화 시나리오 포함.

### 5.5 수동 검증 시나리오 (요약)

`milestones/M3_verification.md` 가 끝에 자세히 작성하지만 plan 차원에선 다음 단계만 둔다(상세 명령은 verification 단계에서 풀어 씀):

1. **자동 — `pytest -q` 약 315 통과**.
2. **MCP stdio 부팅** — `python -m gah --mcp` 후 `initialize`/`tools/list` JSON-RPC 핸드셰이크. (verification 단계에서 Claude 가 직접 PowerShell 로 측정)
3. **트레이 + MCP 동시 기동** — `python -m gah --tray` 와 별도 PowerShell 의 `python -m gah --mcp` 동시 띄움 → `gah.log` 에 `database is locked` 0 건.
4. **검색 박스 e2e** — 트레이의 메인 윈도우 라이브러리 탭에서 `"dark cave loop bgm"` 입력 → 250ms 후 결과 1개 이상.
5. **통일성 가중치 누적** — 임의 프로젝트 ID 로 `find_asset` 2회 호출 사이 `record_asset_use` 1회 → 두 응답의 `score_breakdown.consistency` 비교(첫 0 → 두 번째 양수).
6. **`signature` 무효화** — `list_labels` 1회 호출 → GUI 라벨 다이얼로그에서 라벨 1개 추가 → `list_labels` 재호출 → `signature` 달라짐.
7. **DB 신규 테이블** — `sqlite3 ...\metadata.db ".tables"` 가 `projects`/`asset_usage`/`search_queries` 포함. 행 수가 §5 시나리오대로 누적.

## 6. 위험 요소와 완화

- **`mcp` SDK 버전 호환** — 0.x → 1.0 사이 API 변동 가능. §3.1 의 스파이크에서 한 번 검증 후 `pyproject.toml` 핀. SDK 가 stdio 에서 불안정하거나 의존성 충돌이 있으면 직접 JSON-RPC 핸들러로 폴백(asyncio StreamReader/Writer + `json` 표준 라이브러리). 도구 함수 자체(시그니처 + 로직)는 SDK 와 무관하게 그대로 재사용 가능.
- **stdio 와 GUI 동시 write 충돌** — `--mcp` 와 `--tray` 가 같은 SQLite. M2.1 `write_lock` 은 한 프로세스 안에서만 유효. inter-process 보호는 WAL + `busy_timeout=5000` 에 위임. busy timeout 초과 시는 도구가 `503_busy` 반환 — 도구 함수 단위에서 `sqlite3.OperationalError` 캐치.
- **벡터 풀스캔 성능** — 1만 자산 ≈ 10ms 단일 코사인. 5만 넘어가면 ~50ms. 더 커지면 `sqlite-vec` extension 으로 교체 (인터페이스 `store.semantic_candidates_load` 한 함수만 바꿈). M3 범위에서는 풀스캔으로 충분.
- **암묵 top1 추정의 오탐** — Default off 결정. 사용자가 결과 보고 안 채택해도 implicit 마킹 안 됨. MCP `instructions` 에 `record_asset_use` 명시 호출 권장. 사용자가 Config 로 켤 수도 있고, 그 경우 같은 `query_id` 중복 INSERT 방지 (M2.1 의 `write_lock` 보호).
- **첫 프로젝트 / 첫 검색의 통일성 = 0** — 이력 0 이라 consistency 항이 0. UX 측면에서 "왜 추천 점수가 낮지" 의문 방지를 위해 `why` 필드에 `"이 프로젝트의 첫 검색 — 통일성 가중치는 다음 채택 이후 적용됩니다"` 한 줄. 첫 채택 후엔 같은 팩 +0.6 이 즉시 반영.
- **`pack_id` 비정규화 의존** — `asset_usage.pack_id` 가 비정규화 컬럼이라 자산 삭제 후에도 팩 선호가 남는다. 단 팩이 통째로 삭제되면 `pack_uses` 의 key 가 dangling. `project_usage_summary` 가 `packs` JOIN 시 `LEFT JOIN` + NULL 처리. dangling pack_id 는 통일성 점수에서 무시.
- **`label_match_score` 가 0 일 때 단일 채널 dominance** — labels_* 안 보낸 호출에서는 label_match=0. 그 결과 semantic + consistency 가 final score 의 대부분을 결정. 이건 의도(라벨 필터 명시 안 한 자유 쿼리). 단 자유 쿼리에서 라벨 의미가 임베딩으로 흘러들기는 한다(`searchable.for_embed` 에 라벨 description 포함).
- **`build_fts_match_expression` 토큰 충돌** — 자유 쿼리의 한국어가 FTS5 `porter unicode61` 에서 어떻게 토큰되는지 의존. M2 시점 검증으로 한국어 토큰화는 unicode61 이 잘 다룸을 확인. 라벨 prefix(`label:...`) 는 §3.5 의 결정대로 SQL JOIN 으로 풀어 FTS5 콜론 처리에 의존 안 함.
- **`recent_assets_score` 의 시간 기준** — `added_at` 기준이면 라이브러리에 처음 등록된 시점. `analyzed_at` 기준이면 분석 완료 시점. **권장은 `analyzed_at`** — 분석 안 끝난 자산은 어차피 검색 후보에서 빠짐. 둘 다 NULL 인 경우는 (현재 시간) 으로 폴백.
- **`request_rescan` 의 워커 없음 케이스** — `--mcp` 단독 프로세스에선 `AnalysisQueue` 가 안 떠 있을 수 있다. 두 선택지: (a) `503_no_worker` 반환 + 사용자에게 트레이 켜라 안내 / (b) `analysis_state='pending'` 으로 마킹만 하고 OK + `warnings` 필드. **권장 (b)** — 다음 GUI 부팅이 자동 픽업. 응답에 `warnings: ["no live worker; will be processed on next GUI startup"]`.
- **GUI 검색 박스 디바운스 + 검색 호출 동기성** — `HybridSearcher.hybrid` 가 동기 함수(numpy + sqlite + Pydantic). 큰 라이브러리(1만+)에서 ~50ms. GUI 메인 스레드에서 직접 호출해도 체감 freeze 없음. 만약 100ms 넘어가는 환경이 생기면 M4 가 `QtConcurrent.run` 으로 워커 스레드로 옮긴다.
- **검색 쿼리 임베딩 = 자산 임베딩과 같은 인코더** — Ollama `nomic-embed-text` 호출이 매 검색마다 일어난다. 평균 ~50ms (warm). cold start 1~2초. cold 케이스는 GUI 부팅 직후 한 번 warmup(검색박스 placeholder 텍스트 임베딩 1회) — 비용 무시 가능. MCP 모드는 첫 `find_asset` 호출이 cold 일 수 있고, 응답은 그래도 정상.
- **`mcp` SDK 의 비동기 모델과의 충돌** — `FastMCP` 가 내부적으로 asyncio 라면, 우리 동기 store/search 함수는 `asyncio.to_thread` 로 감싸야 할 수 있다. §3.1 스파이크에서 검증.
- **수동 검증의 사용자 부담** — M2/M2.1 수동 검증은 분석 큐 시각 확인이 있어 GUI 필수였지만, M3 는 대부분 JSON-RPC + SQLite 검증이라 Claude 가 직접 PowerShell 로 측정 가능. GUI 시각 확인은 검색 박스 1 가지만 사용자에게 남김(메모리 `feedback_run_commands_directly.md` 일관).

## 7. M4 인계점

M3 가 끝나면 M4 가 검색 UX 를 풍부하게 만들 때 다음을 그대로 받는다.

- **`HybridSearcher`** — 가중합 공식이 Config 슬라이더로 노출 가능. M4 가 GUI 가중치 슬라이더를 추가하면 그 값이 `Config.weight_*` 를 갱신 → 다음 검색에 즉시 반영. `consistency_weight_override` / `label_match_weight_override` per-call 도 이미 지원.
- **`SearchRequest`** — 라벨 부울 구조화 입력(`labels_all/any/none`) 이 이미 준비됨. M4 가 추가할 자연어 라벨 쿼리 파서(`"pixel art AND dark"`)는 같은 구조로 풀어 SearchRequest 에 주입.
- **`score_breakdown`** — 5 채널 모두 노출. M4 슬라이더의 백엔드 데이터.
- **`matched_labels`** — 결과 행마다 어떤 라벨로 매칭됐는지. M4 가 결과 그리드의 라벨 칩 UI 로 시각화.
- **`projects` / `asset_usage`** — 프로젝트 탭의 사용 분포 시각화에 그대로 사용.
- **`search_queries`** — 저장된 검색(M4 신기능 후보)의 백엔드 테이블 그대로 사용.
- **MCP stdio** — `--mcp` 가 안정. M4 가 GUI 검색 박스 외에 MCP 도구 신규 추가가 필요하면 `mcp/tools.py` 에 1 함수 추가.

또 M3 안에서 **의도적으로 남겨두는** 자리:

- `suggest_packs` 의 `samples` 필드 — 썸네일 경로 / `preview_blurb` 정도만 채움. 상세 미리듣기/썸네일 그리드는 M4.
- `find_asset` 의 `cross_pack_filter` (한 쿼리에서 여러 팩 결과 균등 노출) — v1 은 단순 top-N 그대로. M4 가 다양성 부스터 추가.
- `report_feedback` 의 페널티 학습 — v1 은 로그 + `search_queries` 갱신만. 실제 다음 검색 가중치 조정은 M4 가 알고리즘 결정.
- 사용자 검색어 자동완성 — M4.
- 결과 다중 선택 / 배치 채택 — M4 또는 M7.
- `list_assets` 의 풍부 필터 — M4 가 GUI 사이드패널에 노출.

---

## 자기 검토 메모

- §1 가중치 공식 합 = `0.40 + 0.15 + 0.20 + 0.20 + 0.05 = 1.00`. label_match=0 케이스에서 합은 0.80 max — 의도(라벨 필터 명시 안 한 자유 쿼리는 약한 매칭). ✓
- §2.1 의 모듈 14 개 ↔ §3 의 작업 단위 9 묶음 — 매핑 일관. mcp/server.py 가 §3.6 에서 mcp/tools.py/models.py 와 한 묶음. ✓
- §2.2 표 합 ~94 ↔ §3 단위별 케이스 합 `16 + 12 + 8 + 20 + 10 + 22 + 6 + 5 + 6 = 105`. 차이 11 은 (a) `test_mcp_tools` 의 시나리오 추가 검증(`record_asset_use` → 다음 `find_asset` consistency 영향 등) 가 표의 "각 도구 1~2" 카운트를 초과, (b) `test_search.py` 의 가중합/정규화 케이스가 표의 20 과 정확 일치. **M3_todo.md 작성 시점에 케이스 ID 를 1:1 박아 정확 합으로 확정**(verification.md 가 그 합을 그대로 단언).

- 의존성 추가가 `mcp>=1.0` 1개로 끝 — torch/open_clip/librosa 등 무거운 의존성 신규 없음. wheel 사이즈 영향 미미. ✓
- 위험 요소 §6 — SDK 폴백 경로 명시 + busy_timeout 흡수 명시. M2.1 의 동시성 패턴 그대로 활용. ✓
- M4 인계점 §7 — `score_breakdown` / `matched_labels` / `SearchRequest` 구조가 M4 의 슬라이더·칩 UI 기반. ✓
- 한국어 작성 / 영어 파일·폴더명 — 본 plan + 신규 모듈 경로 모두 준수. ✓
- 메모리 `feedback_run_commands_directly.md` — 수동 검증 항목은 GUI 검색 박스 시각 확인 1 개만 사용자, 나머지 (MCP 핸드셰이크 / 동시 기동 / DB 검증) 는 Claude 가 PowerShell 로 직접 측정 예정. ✓
- 메모리 `feedback_milestone_manual_verification_format.md` — M3 끝 응답 본문에 단계별 체크리스트로 사용자 수동 항목 별도 제시 예정. ✓
- 메모리 `project_search_ux_milestone.md` — 라벨 부울 파서·풍부 UX 는 M4 로 미룬 결정 본 plan §1 "라벨 부울 파서 미포함" + §3.5 의 `SearchRequest.labels_*` 구조화 입력만 받는 설계로 반영. ✓
- 메모리 `project_label_scoring_clip_inclusion.md` — 라벨 점수가 `label_match` 별도 채널로 노출 (§1 가중치 공식). ✓

검증 끝.
