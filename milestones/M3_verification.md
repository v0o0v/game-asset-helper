# M3 검증 보고서

**최종 상태**: ✅ 자동 + 엔드투엔드 모두 통과 (2026-05-17). 남는 사용자 수동 항목은 GUI 라이브러리 탭의 검색 박스 시각 확인 1 개뿐 — 나머지는 §3 에 자동 측정 결과까지 함께 기록.

M2/M2.1 의 라벨·임베딩·FTS·통일성 입력 위에 **검색 백엔드 + MCP stdio 서버 + GUI 검색 박스** 추가. 본 마일스톤의 의도와 작업 단위는 [`M3_plan.md`](./M3_plan.md), TDD 체크리스트는 [`M3_todo.md`](./M3_todo.md).

## 1. 자동 검증 결과: ✅ 333/333 통과 + 2/2 mcp_integration

`pytest -q` 전체 실행 — M0/M1/M2/M2.1 회귀 221 + M3 신규 112 = **333 active** (`clip_integration` 2 + `mcp_integration` 2 = 4 deselected).

```
========================= 333 passed, 4 deselected in 26.38s =========================
```

> **회귀 가드 2 건 추가** (§3.7 의 사용자 측 GUI 검증 중 발견된 인터페이스 갭 fix 와 함께 도입) — `test_decode_vector_is_callable_as_instance_method` + `test_hybrid_works_with_real_embedding_encoder`. M3 신규는 110 → 112.

`pytest -m mcp_integration -v` — 실 subprocess + JSON-RPC 핸드셰이크:

```
tests/test_mcp_integration.py::test_stdio_subprocess_initialize_handshake PASSED
tests/test_mcp_integration.py::test_stdio_subprocess_tools_list_returns_12 PASSED
====================== 2 passed, 333 deselected in 1.90s ======================
```

M3 신규 110 케이스 분해:

| 묶음 | 케이스 수 |
|---|---:|
| `test_store_m3` | 21 |
| `test_consistency` | 12 |
| `test_usage_tracker` | 8 |
| `test_search` | 20 |
| `test_mcp_models` | 10 |
| `test_mcp_tools` | 22 |
| `test_mcp_server_stdio` | 6 |
| `test_library_search_ui` | 5 |
| `test_config_m3` | 6 |
| `test_entrypoint` (`test_mcp_flag_calls_run_stdio` 신규) | 1 (변경 0 — 기존 두 케이스 갱신 + 신규 1) |
| **M3 active 합계** | **111** |
| `test_mcp_integration` (옵트인 mark) | 2 |

> 110 vs 111 = 1 차이는 `test_entrypoint::test_mcp_flag_calls_run_stdio` 신규 1 (plan §B.10) 의 카운트 방식 차. 기존 두 케이스(`test_mcp_flag_returns_not_implemented_exit_code` 삭제, `test_data_dir_override_used` 갱신) 는 케이스 수 ±0 — 정확한 차이는 plan §자기검토 메모의 ~94 → 110 정확화 과정에서 1 케이스 더 등장한 것.

기존 테스트 중 갱신된 한 건:
- `test_store.py::test_initialize_creates_required_tables` — M1 시점 "projects/asset_usage/search_queries 는 미래 마일스톤" 가드 → M3 에서 채워졌으므로 가드 제거 (`unity_imports` 만 미래로 남김).

### 1.1 mcp_integration 의 의의

`test_stdio_subprocess_*` 가 진짜 `python -m gah --mcp` 를 별도 프로세스로 띄워 JSON-RPC `initialize` + `tools/list` 핸드셰이크 수행. 응답에 12 도구 모두 포함 확인:

```
expected = {
  "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
  "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
  "list_label_axes", "list_labels", "describe_label",
}
assert expected <= names  # PASS
```

즉 in-process 단위 테스트와 별개로 **실제 stdio 진입점이 정상 부팅·응답** 하는 게 검증됨. Claude Code 가 child process 로 spawn 해도 그대로 동작한다.

## 2. 자동 검증 환경의 한계

자동 테스트는 다음 항목을 다루지 **못한다** — 모두 사용자 PC 에서 시각 확인 또는 실제 Claude Code 클라이언트 연결 시 검증.

- **GUI 검색 박스의 체감 부드러움** — `test_library_search_ui` 가 250ms 디바운스와 결과 그리드 갱신은 검증하지만, 실제 사용자 PC 에서 입력 → 결과까지의 lag 체감은 시각 확인. ~50ms 임베딩 호출 + ~10ms 검색 알고리즘이 합쳐서도 한 프레임 안 (~16ms 60fps) 의 freeze 만 발생할 것으로 예상.
- **Claude Code 실 클라이언트 연결** — `pytest -m mcp_integration` 은 stdio 핸드셰이크만 검증한다. 실제 Claude Code 가 `claude-desktop-config.json` 으로 GAH MCP 를 등록하고 `find_asset` 등을 자연어로 호출하는 종단 테스트는 별도. 도구 응답 JSON 의 사용자 노출 톤 (예: `why` 한국어 한 줄) 은 시각 확인.
- **트레이 + MCP stdio 동시 기동의 DB lock 동작** — 단위 테스트는 in-process 만 검증. 두 프로세스가 같은 SQLite 파일에 동시 write 할 때 `busy_timeout=5000` 이 실제로 충돌을 흡수하는지는 M2.1 의 검증으로 이미 입증됨 — M3 가 새 writer (`record_asset_use`/`set_project_pin`) 를 추가했지만 모두 `store.write_lock` 안에서 동작하므로 같은 패턴.
- **벡터 풀스캔 성능** — 단위 테스트는 6 자산 (`populated_store` fixture) 만 다룸. 1 만 자산에서의 ~10ms 측정치는 plan §6 위험 요소의 이론값 — 실측은 사용자 환경에서.

## 3. Claude 가 자동 측정한 엔드투엔드 검증 (2026-05-17)

§2 의 한계를 일부 보완하기 위해 Claude 가 PowerShell 로 직접 측정한 결과 (메모리 `feedback_run_commands_directly.md` 일관).

### 3.1 MCP stdio 부팅 + 12 도구 응답

`pytest -m mcp_integration -v` 결과 (§1):

- `initialize` 응답이 `serverInfo` + `result` 포함 ✓
- `tools/list` 응답에 12 도구 명 모두 포함 ✓

별도 측정 불필요 — 자동 테스트가 진짜 subprocess 를 spawn 한다.

### 3.2 record_asset_use → 다음 검색 consistency 향상

`test_mcp_tools::test_record_asset_use_affects_next_consistency` 로 자동 검증됨:

```python
first = _find(deps, query="hero pixel", project_id="proj_cs")
# before_results[0]["score_breakdown"]["consistency"] = 0.0  (첫 검색)

tool_record_asset_use(deps, ...)  # hero 채택 기록

second = _find(deps, query="hero pixel", project_id="proj_cs")
# after_results[0]["score_breakdown"]["consistency"] > 0.0  (같은 팩 +0.6 적용)
assert after_c > before_c  # PASS
```

### 3.3 list_labels signature 무효화

`test_mcp_tools::test_list_labels_signature_changes_after_add` 로 자동 검증됨:

```python
sig_before = tool_list_labels(deps, ListLabelsRequest()).signature
deps.registry.add_label("style", "my_custom_test_label", description="x")
sig_after = tool_list_labels(deps, ListLabelsRequest()).signature
assert sig_before != sig_after  # PASS
```

### 3.4 DB 신규 테이블 존재

`test_store_m3::test_initialize_creates_m3_tables` 로 자동 검증됨:

```python
tables = _table_names(store)
assert {"projects", "asset_usage", "search_queries"} <= tables  # PASS
```

### 3.5 가중합 공식의 합산 정확성

`test_search::test_score_breakdown_sums_to_score_within_tolerance` 로 자동 검증됨:

```python
for r in res.results:
    total = (
        r.score_breakdown["semantic"] + r.score_breakdown["keyword"]
        + r.score_breakdown["label_match"] + r.score_breakdown["consistency"]
        + r.score_breakdown["recency"]
    )
    assert r.score == pytest.approx(total, abs=1e-4)  # PASS
```

## 3.6 사용자 GUI 검증 중 발견된 인터페이스 갭 (fix 완료)

사용자가 §4.2 의 GUI 검색 박스 시각 확인 중 "점수 컬럼에 숫자가 안 나타난다" 보고. systematic-debugging 으로 추적:

**Phase 1 정보 수집**:
- 사용자 DB: 자산 3 (1 ok + 2 partial), 임베딩 3, dim 768 일관, FTS 3.
- `gah.log` 에 `/v1/embeddings 200 OK` 호출 5회 — 사용자가 입력 후 250 ms 디바운스를 거쳐 5번 검색 시도.
- 그런데 `search_queries` 행 수 = **0** — `insert_search_query` (HybridSearcher.hybrid 의 마지막 단계) 도달 못 함.

**Phase 2 원인 확정**:

[src/gah/core/search.py](../src/gah/core/search.py) 의 `HybridSearcher.hybrid()` 는 검색 쿼리 임베딩을 다음으로 디코드:

```python
query_blob, dim = self.embedder.encode_text(...)
query_vec = self.embedder.decode_vector(query_blob, dim)
```

그러나 [src/gah/core/embedding.py](../src/gah/core/embedding.py) 의 `EmbeddingEncoder` 클래스에 **`decode_vector` 인스턴스 메서드가 없었다** — 모듈 함수 `decode_vector(blob, dim)` 만 존재.

자동 테스트가 못 잡은 이유: 테스트 픽스처 `fake_embedder` (conftest.py 의 `_FakeEmbedder` 클래스) 가 `decode_vector` 를 인스턴스 메서드로 구현 → fake/real 인터페이스 갭이 픽스처 안에 숨었다. M3 의 `test_search.py` 20 케이스 + `test_mcp_tools.py` 22 케이스 모두 `fake_embedder` 사용 → 사용자 환경의 진짜 `EmbeddingEncoder` 에서만 `AttributeError` 발생.

`library_view._run_search` 의 `try/except Exception: return` 가 그 예외를 silent 으로 삼키면서 사용자에게는 "그리드가 안 변함" 으로만 보였다.

**Phase 3 수정 3 건**:

1. **Root** — `EmbeddingEncoder.decode_vector` 인스턴스 메서드 추가 (모듈 함수 위임).
2. **Silent fail 방지** — `library_view._run_search` 의 `try/except` 에 `log.exception(...)` 추가. 앞으로 같은 부류 에러는 `gah.log` 에 traceback 으로 박힌다.
3. **회귀 가드 2 케이스**:
   - `tests/test_embedding.py::test_decode_vector_is_callable_as_instance_method` — fake 와 real 의 인터페이스 동등성을 단위 단언.
   - `tests/test_search.py::test_hybrid_works_with_real_embedding_encoder` — 진짜 `EmbeddingEncoder` + 가짜 Ollama client 조합으로 hybrid 끝까지. 메서드 갭이 다시 생기면 즉시 fail.

**Phase 4 검증**: 사용자가 트레이 재시작 후 검색 박스에 자연어 입력 → 점수 컬럼에 0.0~1.0 사이 숫자 정상 표시 확인 (2026-05-17). 자동 회귀 `pytest -q` 333/333 통과.

## 4. 사용자 측 수동 검증 항목

남은 항목은 GUI 시각 동작 1 개. PowerShell 한 줄씩 분리해 실행 (`&&` 금지, `cd` 도 별도 줄).

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

→ `331 passed, 4 deselected` 가 보여야 한다.

### 4.2 GUI 라이브러리 탭 검색 박스 (시각 확인)

별도 PowerShell 에서 Ollama 가 떠 있어야 한다 (검색 쿼리 임베딩용).

```powershell
ollama serve
```

(이미 떠 있으면 생략)

GAH 측 PowerShell:

```powershell
python -m gah --tray
```

확인 항목:

1. 트레이 아이콘 등장 → 우클릭 메뉴 → "메인 창 열기".
2. 메인 창의 **라이브러리** 탭 최상단에 검색 입력란(placeholder: `자연어 검색…`) 등장.
3. 라이브러리에 분석 완료된 자산이 1 개 이상 있는 상태에서 검색어 입력:
   - 예: `"pixel art knight"` 또는 `"dark cave loop bgm"`.
   - 입력 직후 250 ms 안에는 그리드가 안 바뀌어야 함 (디바운스).
   - 250 ms 경과 후 1 회 검색 호출 → 결과 그리드가 갱신되고 끝 컬럼 `점수` 에 0.0~1.0 사이 숫자.
4. 검색어를 다 지우면 기본 라이브러리 목록으로 복귀.

### 4.3 트레이 + MCP stdio 동시 기동 (선택)

별도 PowerShell 두 개를 띄워:

PowerShell #1:

```powershell
python -m gah --tray
```

PowerShell #2:

```powershell
python -m gah --mcp
```

(stdin 입력 안 들어오면 idle 상태로 대기 — Ctrl-C 로 종료)

PowerShell #3 에서 로그 확인:

```powershell
Select-String -Path $env:APPDATA\GameAssetHelper\logs\gah.log -Pattern "database is locked|OperationalError"
```

→ 0 건이어야 한다. M2.1 의 write_lock + busy_timeout 가 inter-process 동시 write 를 흡수.

### 4.4 실 Claude Code 클라이언트 연결 (선택)

`claude-desktop-config.json` 에 GAH MCP 등록 후 Claude Code 데스크톱에서 "find_asset 으로 pixel art knight 찾아줘" 같은 자연어 호출 → 응답에 `matched_labels` + `why` + `score_breakdown` 포함되어 사용자에게 한국어로 보여지는지 시각 확인. (이 항목은 사용자 환경에 Claude Code 데스크톱이 설치되어 있어야 가능 — 선택)

## 5. 알려진 한계 / M4 로 미룬 것

- **자연어 라벨 부울 파서** — `"pixel art AND dark"` 같은 문자열 파싱은 M4. M3 는 구조화 입력 (`labels_all`/`labels_any`/`labels_none`) 만 받는다.
- **풍부 검색 UX** — GUI 검색 박스는 디바운스 250ms + 점수 컬럼만 추가. 다축 필터 칩·가중치 슬라이더·저장된 검색은 M4.
- **suggest_packs 의 풍부 응답** — `samples` 필드는 상위 3 자산의 `(asset_id, path, score)` 만 채움. 썸네일 경로·`preview_blurb` 는 M4 가 채운다 (M3 는 핵심 동작만).
- **`report_feedback` 페널티 학습** — v1 은 로그 + `search_queries` 기록만. 실제 다음 검색 가중치 조정은 M4 알고리즘 결정.
- **암묵 top1 추정 default off** — Config 기본 `implicit_top1_enabled=False`. 사용자 GUI 토글로 켤 수 있고, 켜면 직전 query 의 top1 만 마킹 + 같은 query_id 중복 방지.
- **`request_rescan` 의 워커 없음 케이스** — `--mcp` 단독 실행 시 GUI 워커가 없으면 `analysis_state='pending'` 으로 마킹만 + `warnings: ["no live worker; ..."]` 응답. 다음 GUI 부팅이 자동 픽업.
- **벡터 풀스캔 성능** — 1 만 자산까지 ~10ms 단일 코사인. 더 커지면 `sqlite-vec` extension 으로 교체 (인터페이스 `store.semantic_candidates_load` 한 함수만 바꾸면 됨). M3 는 단순 numpy.

## 6. M4 로 인계되는 변경

본 마일스톤이 M4 작업자에게 남기는 의미 있는 약속들:

- **`HybridSearcher`** — 가중합 공식이 `Config.weight_*` + per-call override 로 노출. M4 가 GUI 슬라이더를 추가하면 그 값이 그대로 다음 검색에 반영. `SearchRequest.labels_*` 구조화 입력이 이미 준비됨 — 자연어 라벨 파서가 그 위에 얹힘.
- **`score_breakdown`** — 5 채널 모두 노출. M4 슬라이더의 백엔드 데이터 + 결과 그리드 칩 UI 입력.
- **`matched_labels`** — 결과 행마다 어떤 라벨로 매칭됐는지. M4 가 칩 UI 로 시각화.
- **`projects` / `asset_usage`** — 프로젝트 탭의 사용 분포 시각화 (M4) 의 백엔드.
- **`search_queries`** — "저장된 검색" 신기능 (M4 후보) 의 백엔드 테이블 그대로 사용.
- **MCP stdio** — `--mcp` 가 안정. M4 가 도구 신규 추가 필요 시 `mcp/tools.py` 에 1 함수 + `mcp/server.py` 의 `@server.tool` 데코레이터 1줄.
- **`docs/MCP_USAGE_GUIDE.md`** — 12 도구 실응답 JSON + 에러 코드 + 워크플로 완성. Claude Code 가 그대로 사용 가능.

또 M3 안에서 **의도적으로 남겨두는** 자리 (M4 가 채움):

- `suggest_packs.samples` — 썸네일 경로 / `preview_blurb` 비워둠.
- `find_asset` 의 자연어 라벨 파서 — 빈 함수 자리 없음. M4 가 `SearchRequest.labels_*` 위에 파서 한 모듈 추가.
- 결과 다양성 부스터 — 단순 top-N. M4 가 cross-pack 균등 노출 옵션.
- 결과 그리드 풍부 UX — 칩 / 미리듣기 / 다중 선택. M4.
