# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-17
**마지막 완료 마일스톤**: M3 (검색 백엔드 + 통일성 + MCP stdio)
**다음 작업**: M4 (검색 UX 풍부화)

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤이 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

설계(`DESIGN.md`) 위에 M0(뼈대) → M1(워처 + 팩 매니저 + SQLite 4테이블 + GUI 팩/라이브러리 탭) → M2(분석 파이프라인 + CLIP 라벨러 + 24축 316 시드 + 라벨 관리 다이얼로그 + 분석 큐/ETA 상태바) → M2.1(분석 큐 동시성 1 → 3 + Ollama semaphore + CLIP lock + SQLite write_lock + GUI 250ms 디바운스) → **M3**(HybridSearcher 가중합 0.40·sem + 0.15·kw + 0.20·label + 0.20·cons + 0.05·rec + MCP stdio 12 도구 + ConsistencyScorer + UsageTracker + GUI 검색 박스 + `docs/MCP_USAGE_GUIDE.md` 본격화 + 사용자 GUI 검증 중 발견된 `EmbeddingEncoder.decode_vector` 메서드 갭 fix + 회귀 가드 2건) 까지 자동 333 테스트 + 2 mcp_integration 통과. 다음은 M4 (자연어 라벨 부울 파서 + 다축 필터 칩 + 가중치 슬라이더 + 저장된 검색) 를 같은 TDD 사이클로 시작한다.

## 2. 검증된 사실 (M3 시점)

자동 — `pytest -q` 결과 **333/333 통과** (27s, Windows 10 / Python 3.12, `clip_integration` 2 + `mcp_integration` 2 = 4 옵트인 deselected). M2.1 의 221 + M3 의 112 신규 (110 케이스 + fix 회귀 가드 2).

`pytest -m mcp_integration -v` — 실제 `python -m gah --mcp` subprocess + JSON-RPC `initialize`/`tools/list` 핸드셰이크 **2/2 통과** — 12 도구 모두 정상 응답.

수동 — M3 의 GUI 검증 1 항목 (라이브러리 탭 검색 박스 시각 동작) 은 [`milestones/M3_verification.md`](./milestones/M3_verification.md) §4.2. 트레이+MCP 동시 기동 + 실 Claude Code 클라이언트 연결은 선택 검증으로 §4.3~§4.4.

```
M0 회귀:        18 passed  (config 6 + logging 4 + single_instance 4 + entrypoint 3 + imports 1)
M1 회귀:        49 passed  (asset_kind 4 + manifest 8 + store 12 + pack_manager 8 + scanner 5 + watcher 5 + ui_smoke 3 + tray 4)
M2 회귀+신규:  134 passed  (M2 plan §5.2 표 그대로)
M1 추가 회귀:    3 passed
M2.1 신규:      16 passed
M2.1 회귀 보존:  +1 passed
M3 신규:       112 passed  (store_m3 21 + consistency 12 + usage_tracker 8 + search 20+1 + mcp_models 10 + mcp_tools 22 + mcp_server_stdio 6 + library_search_ui 5 + config_m3 6 + embedding 회귀 가드 +1)
─────────────────────────────────────────────
합계 333 passed (active) + 4 deselected (clip_integration 2 + mcp_integration 2)
```

M3 수동 검증 단계는 [`milestones/M3_verification.md`](./milestones/M3_verification.md) §4. M2.1 의 수동 검증 단계도 그대로 유효 ([`milestones/M2.1_verification.md`](./milestones/M2.1_verification.md) §3).

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL 모드, 14 객체) |
| CLIP 캐시 | `%APPDATA%\GameAssetHelper\cache\clip\` (첫 분석 시 ~600 MB 다운로드) |
| 스펙트로그램 캐시 | `%APPDATA%\GameAssetHelper\cache\spectrograms\` (사운드 2차 폴백) |

**금기**: Microsoft Store Python(`%APPDATA%` 가상화), Cowork 작업 폴더 내부 venv(권한 충돌).

M2 에서 새로 추가된 의존성 (`pyproject.toml`):

- `Pillow>=10`, `numpy>=1.26`, `librosa>=0.10`, `soundfile>=0.12`
- `httpx>=0.27`, `pydantic>=2.6`
- `open_clip_torch>=2.24`, `torch>=2.2` (단일 wheel — GPU/CPU 통합, 런타임 자동 감지)
- `matplotlib>=3.8` (사운드 2차 폴백의 스펙트로그램 PNG 렌더)
- dev: `pytest-asyncio>=0.23`, `respx>=0.20`

M3 에서 새로 추가된 의존성:

- `mcp>=1.27,<2` (Anthropic 공식 Python SDK — FastMCP 데코레이터 + stdio transport). starlette/uvicorn/pydantic-settings/sse-starlette 등이 자동 따라옴.

기존 venv 를 그대로 쓰는 경우 다음 한 줄로 추가 설치:

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

(편집 가능 설치라 `pyproject.toml` 의 새 의존성이 자동 따라온다. torch wheel ≈ 800 MB + librosa numba 약 200 MB.)

## 4. 새 세션에서 바로 이어가는 방법

이미 venv 가 설치된 PC 라면:

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `333 passed, 4 deselected` 확인. 그러면 M0~M3 기준점이 유지되고 있다는 뜻.

venv 가 없는 새 PC 라면 [`CLAUDE.md §6`](./CLAUDE.md) 의 셋업 절차 그대로.

## 5. M4 시작 절차

M4 범위: **검색 UX 풍부화** — 자연어 라벨 부울 파서, 다축 필터 칩, 가중치 슬라이더, 저장된 검색, 결과 그리드 라벨 칩 UI, suggest_packs samples 풍부화 (썸네일/미리듣기). 일정 1.5주 (메모리 `project_search_ux_milestone.md`).

다음 세션 진입 시:

1. **새 브랜치 생성** — M3 머지 후 `main` 에서 `feat/m4-search-ux` (또는 적당한 이름).
2. **MEMORY.md 자동 로드 확인** — 새 세션은 다음 8개 메모리를 자동 컨텍스트로 받는다:
   - 마일스톤 수동 검증 항목 표시 방식 (feedback)
   - PR/커밋 한글 (feedback)
   - 가능한 한 직접 실행 (feedback)
   - M2 분석 클라이언트 백엔드 추상화 (project)
   - Ollama 멀티모달 API 형식 실측 (project)
   - 모델 출력 듀얼 언어 + GUI i18n (project)
   - 라벨 가중치 + CLIP v1 편입 (project)
   - 검색 UX 전용 마일스톤 M4 신설 (project)
   - GAH 배포 전략 — torch CUDA/CPU 통합 빌드 (project)
3. **DESIGN.md 참조 섹션** — §4.8 (GUI 탭 구성), §6.5 (suggest_packs samples 풍부 UX), §11 (마일스톤 로드맵).
4. **M4 plan 작성** — [`milestones/M3_plan.md`](./milestones/M3_plan.md) 를 템플릿으로 `M4_plan.md`. 핵심 산출물:
   - `src/gah/core/label_query.py` — 자연어 라벨 부울 파서 (`"pixel art AND dark"` → `LabelFilter[]` 변환). M3 의 `SearchRequest.labels_*` 구조화 입력 위에 얹힌다.
   - GUI 라이브러리 탭 풍부 UX — 사이드 패널 라벨 칩 다중 선택, 가중치 슬라이더 (5 채널), 결과 행에 `matched_labels` 칩 + 점수 시각화, "저장된 검색" 사이드바.
   - `suggest_packs` 응답의 `samples` 필드 풍부화 — 썸네일 경로 + `preview_blurb` + 사운드 미리듣기 메타.
   - 결과 다양성 부스터 — `find_asset` 에 `cross_pack_filter` 옵션 (한 쿼리에서 여러 팩 결과 균등 노출).
   - `report_feedback` 페널티 학습 — `search_queries` + `asset_usage` 의 negative 신호를 다음 검색 가중치에 반영하는 알고리즘.
5. **M4_todo.md** — TDD 순서 체크리스트.
6. **테스트 먼저** — `tests/test_label_query.py`, `tests/test_library_search_ui_rich.py`, `tests/test_search_diversity.py`, `tests/test_feedback_penalty.py` 등.
7. **구현 → 통과 → `M4_verification.md`** (사용자 수동 검증 항목은 마일스톤 끝 응답 본문에 단계별 체크리스트로 별도 제시 — 메모리 feedback 참조).

**M4 plan 작성 시 결정해야 할 항목**:

- 라벨 부울 파서 문법 — `AND`/`OR`/`NOT` 명시 vs SQL 스타일 vs 자연어 보조 (예: "AND" → "그리고", "NOT" → "제외"). 사용자 친화 vs 정확성.
- 가중치 슬라이더의 사용자 노출 형식 — 5 채널 슬라이더 풀 노출 vs "프리셋" (예: "통일성 강조", "참신성 강조") + 고급 모드.
- "저장된 검색" 의 backing store — 기존 `search_queries` 위에 `is_saved` 컬럼 추가 vs 새 `saved_searches` 테이블.
- `cross_pack_filter` 의 algorithm — MMR (Maximum Marginal Relevance) vs round-robin per pack vs softmax 다양성.

## 6. M3 에서 의도적으로 남겨둔 자리

- `suggest_packs` 의 `samples` 필드 — `(asset_id, path, score)` 만 채움. 썸네일 경로 / `preview_blurb` / 사운드 미리듣기 메타는 M4.
- `find_asset` 의 자연어 라벨 부울 파서 — 진입 없음. M4 가 `SearchRequest.labels_*` 위에 파서 한 모듈 추가.
- 결과 다양성 부스터 (`cross_pack_filter`) — M3 는 단순 top-N. M4.
- 결과 그리드 풍부 UX (칩 / 미리듣기 / 다중 선택 / 가중치 슬라이더 / 저장된 검색) — M4.
- `report_feedback` 의 페널티 학습 — M3 는 로그 + `search_queries` 기록만. 실제 다음 검색 가중치 조정 알고리즘은 M4.
- 암묵 top1 추정 (`implicit_top1_enabled`) — Config 기본 OFF. 사용자 GUI 토글로 켤 수 있고, 켜면 직전 query 의 top1 만 마킹.
- `request_rescan` 의 워커 없음 케이스 — `--mcp` 단독 실행 시 `mark_pending` 만 + warnings 반환. 다음 GUI 부팅이 자동 픽업.

## 7. 문서 맵

- [`README.md`](./README.md) — 사용자용 시작 안내
- [`CLAUDE.md`](./CLAUDE.md) — Claude(코드 에이전트)용 작업 가이드
- [`HANDOFF.md`](./HANDOFF.md) — 이 파일, 마일스톤 경계의 인계 스냅샷
- [`DESIGN.md`](./DESIGN.md) — 전체 아키텍처·스키마·MCP 명세
- [`milestones/`](./milestones/) — 마일스톤별 plan/todo/verification
- [`docs/MCP_USAGE_GUIDE.md`](./docs/MCP_USAGE_GUIDE.md) — Claude Code 가 MCP 도구를 어떻게 활용하는지 가이드 (M3 가 본격화)

## 8. 갱신 규칙

이 문서는 다음 시점에 반드시 업데이트한다.

1. 마일스톤이 완료될 때 (§2 검증 결과, §1 한 줄 요약, "다음 작업").
2. 환경 결정이 바뀔 때 (§3).
3. 새 금기·주의사항이 발견될 때 (§3 또는 별도 섹션).

내용을 누적하기보다 **현재 시점의 진실만** 적는다. 과거 이력은 git log 에 맡긴다.
