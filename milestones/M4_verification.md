# M4 검증 보고서

**최종 상태**: ✅ 자동 검증 모두 통과 (2026-05-17). 남는 사용자 수동 항목은 GUI 라이브러리 탭 풍부 UX 4 단계 — §4 에 단계별 체크리스트로 별도 제시.

M3 의 `HybridSearcher` + 12 MCP 도구 + GUI 검색 박스 위에 **자연어 라벨 부울 파서 + 6 채널 가중합 (feedback) + 다양성 (none/mmr/round_robin) + saved_searches 4 MCP + suggest_packs samples 풍부화 + GUI 풍부 UX (칩 + 슬라이더 + 저장된 검색 + 다축 필터)** 추가. 본 마일스톤의 의도와 작업 단위는 [`M4_plan.md`](./M4_plan.md), TDD 체크리스트는 [`M4_todo.md`](./M4_todo.md).

## 1. 자동 검증 결과: ✅ 433/433 + 2/2 mcp_integration

`pytest -q` 전체 실행 — M0/M1/M2/M2.1/M3 회귀 (329 + 회귀 갱신 3) + M4 신규 100 = **433 active** (`clip_integration` 2 + `mcp_integration` 2 = 4 deselected).

```
========================= 433 passed, 4 deselected in 29.99s =========================
```

`pytest -m mcp_integration -v` — 실 subprocess + JSON-RPC 핸드셰이크:

```
tests/test_mcp_integration.py::test_stdio_subprocess_initialize_handshake PASSED
tests/test_mcp_integration.py::test_stdio_subprocess_tools_list_returns_16 PASSED
====================== 2 passed, 435 deselected in 2.19s ======================
```

> M3 의 도구 카운트 12 → M4 16 (saved_searches 4 신규). 실제 stdio subprocess 가 16 개를 반환함을 확인.

M4 신규 100 케이스 분해:

| 묶음 | 케이스 수 |
|---|---:|
| `test_label_query` | 16 |
| `test_store_m4` | 12 |
| `test_search_diversity` | 9 |
| `test_feedback_penalty` | 10 |
| `test_suggest_packs_samples_rich` | 6 |
| `test_library_search_ui_rich` | 14 |
| `test_mcp_tools_m4` | 14 |
| `test_search_m4` | 8 |
| `test_config_m4` | 6 |
| `test_thumbnails` | 5 |
| **M4 active 합계** | **100** |
| `test_mcp_integration` (옵트인 mark, 갱신 1) | 2 |

회귀 갱신 3 건 (M0~M3 의 333 active 중 동일 카운트 유지 — 단언 내용만 갱신):

- `test_config_m3::test_new_fields_have_documented_defaults` — 5채널 → 6채널 단언 (semantic 0.40→0.35, keyword 0.15→0.10, feedback 0.10 신규).
- `test_config_m3::test_weight_sum_equals_one_within_tolerance` — 5채널 합 → 6채널 합.
- `test_mcp_models::test_report_feedback_request_required_fields` + `test_mcp_tools::test_report_feedback_logs_and_returns_ok` — `reason="not_what_i_wanted"` (자유 문자열) → `Literal["negative","positive","irrelevant"]` 화이트리스트로 변경.

### 1.1 mcp_integration 의 의의

`test_stdio_subprocess_tools_list_returns_16` 가 진짜 `python -m gah --mcp` 를 별도 프로세스로 띄워 JSON-RPC `initialize` + `tools/list` 핸드셰이크 수행. 응답에 M3 12 + M4 신규 4 (`save_search`/`list_saved_searches`/`delete_saved_search`/`run_saved_search`) 포함 + 총 16 도구 확인:

```
expected = {
  # M3 12 도구
  "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
  "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
  "list_label_axes", "list_labels", "describe_label",
  # M4 4 신규 도구
  "save_search", "list_saved_searches", "delete_saved_search",
  "run_saved_search",
}
assert expected <= names and len(names) == 16  # PASS
```

## 2. 자동 검증 환경의 한계

자동 테스트는 다음 항목을 다루지 **못한다** — 모두 사용자 PC 에서 시각 확인 (§4) 으로 검증.

- **GUI 풍부 UX 의 시각 흐름** — `test_library_search_ui_rich` 가 위젯 시그널·메서드 호출까지 검증하지만, QSplitter 가 좌·중·우로 어떻게 자리잡는지, 칩 그리드가 24 axis × ~15 라벨로 답답하지 않은지, 슬라이더 즉시 반응이 시각적으로 자연스러운지 등은 시각 확인.
- **저장된 검색의 사용자 다이얼로그 흐름** — 저장 버튼 → `QInputDialog` → 이름 입력 → 저장된 검색 리스트 추가 → 더블클릭 → 검색 재호출까지의 한 사이클.
- **실 Claude Code 클라이언트 연결** — `pytest -m mcp_integration` 은 stdio 핸드셰이크 + 16 도구 확인까지만. 실제 Claude Code 가 `claude-desktop-config.json` 으로 GAH MCP 를 등록하고 `find_asset(label_query="...")` / `save_search` / `run_saved_search` 를 자연어 호출하는 종단 테스트는 별도.
- **`diversity=mmr` λ=0.7 의 사용자 체감 효과** — 단위 테스트는 두 팩 분포 시드에서 보장. 100+ 팩 실 라이브러리에서 사용자 만족도는 시각/주관 평가.
- **`feedback_records` 누적의 학습 효과** — 단위 테스트는 단일 negative 후 음수 채널 점수만 확인. 실 사용에서 "10번 거부 후 정말 그 자산이 다시 안 나오는지" 는 누적 + 사용자 검증.
- **lazy thumbnail 생성 성능** — 단위 테스트는 단일 PNG. 1000+ sprite 라이브러리에서 첫 `suggest_packs` 호출의 cold start 시간 (Pillow 가 N장 PNG 생성) 은 실측 필요.

## 3. Claude 가 자동 측정한 엔드투엔드 검증 (2026-05-17)

§2 의 한계를 일부 보완하기 위해 Claude 가 PowerShell 로 직접 측정한 결과 (메모리 `feedback_run_commands_directly.md` 일관).

### 3.1 DB 신규 두 테이블 (saved_searches + feedback_records)

`scripts/_m4_verify.py` 일회성 스크립트로 임시 DB 초기화 후 `sqlite_master` 조회:

```
TABLES: asset_embeddings, asset_labels, asset_tags, asset_usage, assets,
        assets_fts, ..., feedback_records, labels, packs, projects,
        saved_searches, search_queries, sound_meta, sprite_meta, tags
  saved_searches: YES
  feedback_records: YES
```

M3 의 21 객체 + M4 신규 2 테이블 = 23 sqlite_master 행 (FTS auxiliary + 인덱스 별도) — 모두 정상 생성.

### 3.2 16 MCP 도구 등록 + stdio subprocess 응답

`pytest -m mcp_integration` 가 `python -m gah --mcp` 를 spawn 해 `tools/list` 응답을 검증 (§1.1). 별도 측정 불필요.

### 3.3 label_query 파서 e2e

`test_label_query.py` 16 케이스 + `test_search_m4.py::test_label_query_free_text_appended_to_semantic_query` 1 케이스 + `test_mcp_tools_m4.py::test_find_asset_label_query_parses_and_injects` 1 케이스로 자동 검증.

```
parse_label_query("sound_mood:dark AND sound_use:combat", registry)
→ ParsedLabelQuery(
    labels_all=[
      LabelFilter(axis="sound_mood", label="dark"),
      LabelFilter(axis="sound_use", label="combat"),
    ],
    labels_any=[], labels_none=[],
    free_text="", original_expr="sound_mood:dark AND sound_use:combat",
  )
```

모호 라벨 (같은 token 이 여러 axis 에 등록) → `AmbiguousLabel(label, candidates=[axis...])` → MCP 레이어가 `400_invalid_input` 으로 매핑.

### 3.4 페널티 학습 — 다음 검색에서 자산이 밀림

`test_feedback_penalty::test_negative_feedback_lowers_next_search_feedback_channel` 로 자동 검증:

```python
store.insert_feedback_record(pid, hero_id, None, "negative", -0.5)
res = searcher.hybrid(SearchRequest(query="hero pixel", project_id="proj_neg", count=10))
fb = next(r.score_breakdown["feedback"] for r in res.results if r.asset_id == hero_id)
assert fb < 0   # PASS — Config.weight_feedback=0.10 적용 후 -0.05 근처
```

pack-level (≥3 negative → 같은 팩 다른 자산도 -0.1) 도 자동 검증됨 (`test_pack_level_penalty_when_three_negatives_in_same_pack`).

### 3.5 saved_searches 라운드트립

`test_mcp_tools_m4::test_run_saved_search_delegates_to_find_asset` 로 자동 검증:

```python
tool_save_search(deps, SaveSearchRequest(
    project_id=pid, name="hero search", query="hero", kind="sprite", count=3,
))
res = tool_run_saved_search(deps, RunSavedSearchRequest(
    project_id=pid, name="hero search",
))
assert hasattr(res, "query_id")    # FindAssetResult 동등 형식
```

중복 name → `400_invalid_input` (`test_save_search_duplicate_name_returns_400`), 미존재 name → `404_not_found` (`test_delete_saved_search_404_when_missing`, `test_run_saved_search_404_when_name_missing`) — 모두 자동.

### 3.6 6채널 가중합의 정확성

`test_search_m4::test_six_channel_score_breakdown_sums_to_score_within_tolerance` 로 자동 검증:

```python
for r in res.results:
    total = sum(r.score_breakdown.get(k, 0.0)
                for k in ("semantic", "keyword", "label_match",
                          "consistency", "recency", "feedback"))
    # prefer_bonus 등 추가 키도 합산
    for extra_k in r.score_breakdown:
        if extra_k not in (...):
            total += r.score_breakdown[extra_k]
    assert r.score == pytest.approx(total, abs=1e-4)   # PASS
```

### 3.7 diversity (mmr / round_robin) 동작

`test_search_diversity` 9 케이스로 자동:

- `diversity="none"` → M3 동작 그대로
- `mmr λ=1.0` → score 순서 (다양성 0)
- `mmr λ=0.0` → 다른 팩 강제 (다양성만)
- `mmr λ=0.7` → 두 팩 모두 등장 (균형)
- `round_robin` → 팩 교대 패턴 (a, b, a, b)
- `round_robin` 단일 팩 → score 폴백
- 후보 ≤ count → diversity 무관 모두 반환
- mmr 가 `score_breakdown` 채널 값 변경 안 함

## 4. 사용자 측 수동 검증 항목 (GUI 풍부 UX 4 단계)

남은 항목은 GUI 시각 동작 4 단계. PowerShell 한 줄씩 분리해 실행 (`&&` 금지, `cd` 도 별도 줄). 메모리 `feedback_milestone_manual_verification_format.md` — 마일스톤 끝 응답 본문에 단계별 체크리스트로 별도 제시.

### 4.1 사전 준비

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `433 passed, 4 deselected` 가 보여야 한다.

별도 PowerShell 에서 Ollama 가 떠 있어야 한다 (검색 쿼리 임베딩용):

```powershell
ollama serve
```

(이미 떠 있으면 생략)

GAH 측 PowerShell:

```powershell
python -m gah --tray
```

### 4.2 GUI 풍부 UX — 단계별 시각 확인

다음 4 단계를 차례로 확인:

#### 단계 1 — 좌측 라벨 칩 패널 (`LabelChipPanel`) 노출

- 트레이 아이콘 우클릭 → "메인 창 열기".
- 메인 창의 **라이브러리** 탭이 3 분할 (좌·중·우) QSplitter 로 구성됐다면 OK.
- 좌측 패널 최상단에 **매칭 모드** 그룹박스 (`AND` / `OR` / `NOT` 라디오 3개).
- 그 아래 axis 별 QGroupBox (24 axis × 라벨 체크박스) — 스크롤 가능.
- 칩 체크박스 1개 클릭 → 검색 모드 전환 (그리드가 검색 결과로 바뀌어야 한다).

#### 단계 2 — 우측 가중치/저장 패널 (`SearchSidePanel`) 노출

- 우측 패널 상단에 **가중치** 그룹박스 — 6 슬라이더 (의미/키워드/라벨/통일성/최신/피드백). 기본값은 35/10/20/20/5/10.
- 그 아래 **프리셋** 그룹박스 — 3 버튼 (`균형` / `통일성 우선` / `참신성 우선`). 버튼 클릭 → 슬라이더 6개 동시 갱신.
- 그 아래 **저장된 검색** 리스트 (빈 상태 — 4 단계에서 채워짐).
- 맨 아래 **"현재 검색 저장…"** 버튼.

#### 단계 3 — 상단 검색 박스 + label_query 입력 + matched_labels 칩

- 검색 박스 (placeholder `자연어 검색…`) 에 다음 입력 (분석된 자산이 있어야):
  - 예: `"hero pixel_art"` (bare label 자동 매칭 — `category=character` + `style=pixel_art` 가정)
  - 또는: `"sound_mood:dark AND sound_use:combat"` (axis:label 명시 + AND)
- 250 ms 후 결과 그리드가 갱신되어야.
- 결과 행에 `matched_labels` 가 `category=hero · style=pixel_art` 같은 텍스트로 노출.

#### 단계 4 — "현재 검색 저장" → 저장된 검색 리스트 → 더블클릭 재호출

- 우측 패널 "현재 검색 저장…" 클릭 → `QInputDialog` 가 떠야.
- 이름 입력 (예: `"내 첫 저장된 검색"`) → 확인.
- 저장된 검색 리스트에 추가되어야.
- 리스트 항목 더블클릭 → 같은 검색이 재호출되어 그리드 갱신.

### 4.3 트레이 + MCP stdio 동시 기동 (선택)

M3 와 동일 — `python -m gah --tray` 와 별도 PowerShell 의 `python -m gah --mcp` 동시 기동 후 `gah.log` 에 `database is locked` 0 건 확인. M4 가 같은 write_lock + busy_timeout 패턴 그대로 사용하므로 회귀 없음 예상.

### 4.4 실 Claude Code 클라이언트 연결 (선택)

`claude-desktop-config.json` 에 GAH MCP 등록 후 Claude Code 데스크톱에서:

- `find_asset({ "query": "BGM", "label_query": "sound_mood:dark AND sound_use:combat", "project_id": "test", "diversity": "mmr", "count": 5 })` 호출 → 응답에 `matched_labels` + `score_breakdown.feedback` 포함.
- `save_search` → `list_saved_searches` → `run_saved_search` 라운드트립.
- `report_feedback({ "query_id": ..., "asset_id": ..., "reason": "negative" })` 호출 후 같은 검색 재호출 → `score_breakdown.feedback` 가 음수.

## 5. 알려진 한계 / M5+ 또는 M7 로 미룬 것

- **`label_query` 한국어 키워드** — v1 영어 `AND`/`OR`/`NOT` 만. 사용자 피드백 기반으로 M5+ 가 `그리고`/`또는`/`제외` 추가 결정.
- **`label_query` 혼합 AND/OR (OR-of-AND DNF)** — v1 은 순수 AND 또는 순수 OR 만 정확 매핑. `(a AND b) OR c` 같은 혼합은 `UnsupportedExpression` 예외. 사용 빈도 분석은 사용자 시각 검증.
- **`preview_blurb` 의 Gemma description 통합** — v1 은 top-2 라벨만. `assets.description` 컬럼 추가 후 M5+ 가 첫 한 줄 (80자 컷) 통합.
- **그리드 ↔ 리스트 뷰 토글** — v1 은 표 형태만. M7 GUI 마감.
- **hover 미리보기 / 사운드 인라인 재생** — M7 (PySide6 `QMediaPlayer`).
- **결과 비교 보기 / 키보드 단축키** — M7.
- **`cleanup_feedback_records` 잡** — v1 은 검색 시 윈도우 필터만 (윈도우 밖 행은 DB 에 남음). 주기적 정리는 M5+.
- **MMR 의 binary same-pack similarity** — v1 은 단순 0/1 indicator. 더 정교한 vector cosine similarity 는 사용자 피드백 기반 결정.
- **pack-level penalty 임계 (`feedback_pack_threshold=3`) 의 사용자 노출** — v1 은 Config TOML 만. M7 GUI 설정 슬라이더 추가.

## 6. M5 로 인계되는 변경

본 마일스톤이 M5 (시트 분석 + 애니메이션) 작업자에게 남기는 약속:

- **`LabelRegistry` + `label_query` 파서** — M5 가 추가하는 새 axis (`sheet_animation`, `sheet_grid` 등) 도 같은 파서로 검색 가능. axis 자동 매칭 + AND/OR/NOT 그대로.
- **`HybridSearcher` 6 채널 + 다양성** — M5 의 새 자산 (시트 frame splitting 결과) 도 같은 검색 알고리즘으로 즉시 노출.
- **`saved_searches`** — M5 가 시트 관련 검색 패턴 ("walk 애니메이션 시트") 을 저장된 검색으로 노출 가능. `_schema_version: 1` 이 박혀 있어 SearchRequest 구조 진화 시 마이그레이션 신호.
- **`feedback_records`** — M5 의 frame 추정 결과에 대한 사용자 피드백도 같은 메커니즘으로 누적.
- **GUI 풍부 UX 컨테이너** — `LabelChipPanel` / `SearchSidePanel` / `FilterBar` 가 그대로 살아 있음. M5 의 시트 frame 미리보기 패널이 같은 라이브러리 탭에 추가될 때 컨테이너 역할.
- **MCP 16 도구** — `--mcp` 가 안정. M5 가 `suggest_animation_frames` 도구를 추가 시 `mcp/tools.py` 에 1 함수 + `mcp/server.py` 의 `@server.tool` 데코레이터 1줄.
- **`docs/MCP_USAGE_GUIDE.md`** — 16 도구 + `label_query` 문법 + diversity + 페널티 학습 모두 문서화 완료. M5 는 §6.7 위 형식 그대로 새 도구 추가.

또 M4 안에서 **의도적으로 남겨두는** 자리 (§5 의 한계 목록 참조):

- 그리드↔리스트 토글 / hover preview / 사운드 인라인 재생 / 결과 비교 보기 / 키보드 단축키 → M7
- `cleanup_feedback_records` 잡 → M5+
- `label_query` 한국어 키워드 / 혼합 AND/OR → M5+
- Gemma description 통합한 `preview_blurb` → M5+ (`assets.description` 컬럼 선행)
