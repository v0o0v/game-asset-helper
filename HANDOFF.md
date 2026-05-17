# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-17
**마지막 완료 마일스톤**: M2.1 (분석 큐 병렬화 패치)
**다음 작업**: M3 (검색 백엔드 + 통일성 + MCP 도구)

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤이 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

설계(`DESIGN.md`) 위에 M0(뼈대) → M1(워처 + 팩 매니저 + SQLite 4테이블 + GUI 팩/라이브러리 탭) → M2(분석 파이프라인 + CLIP 라벨러 + 24축 316 시드 + 라벨 관리 다이얼로그 + 분석 큐/ETA 상태바) → **M2.1**(분석 큐 동시성 1 → 3 + Ollama semaphore + CLIP lock + SQLite write_lock + GUI 250ms 디바운스) 까지 자동 221 테스트 통과. 다음은 M3 (FTS5+벡터 코사인 검색 + 통일성 스코어러 + MCP stdio 도구 7~8개) 를 같은 TDD 사이클로 시작한다.

## 2. 검증된 사실 (M2.1 시점)

자동 — `pytest -q` 결과 **221/221 통과** (37s, Windows 10 / Python 3.12, `clip_integration` 2 옵트인 deselected). M2 의 204 + M2.1 의 16 신규 + 회귀 보존 +1.

M2.1 동시성 테스트 5회 반복 실행 결과 0 flake.

수동(M2 시점) — 사용자 PC 에서 GUI 시각 4 항목 (트레이 아이콘 / 우클릭 메뉴 / 메인 윈도우 + 컬럼 + 상태바 / 라벨 관리 다이얼로그) 모두 OK 확인. M2.1 의 수동 검증 항목(분석 부드러움 / DB lock 0건 / throughput 비교) 은 [`milestones/M2.1_verification.md`](./milestones/M2.1_verification.md) §3.

```
M0 회귀:        18 passed  (config 6 + logging 4 + single_instance 4 + entrypoint 3 + imports 1)
M1 회귀:        49 passed  (asset_kind 4 + manifest 8 + store 12 + pack_manager 8 + scanner 5 + watcher 5 + ui_smoke 3 + tray 4)
M2 회귀+신규:  134 passed  (store_m2 17 + labels 19 + labels_admin_ui 7 + ollama_client 16 + embedding 5 + clip_labeler 6 + searchable 9 + analyzer_sprite 11 + analyzer_sound 13 + analysis_queue 8 + analysis_progress 9 + progress_statusbar 4 + config_m2 5 + ui_smoke_m2 3)
M1 추가 회귀:    3 passed  (ui_smoke 의 M2 변경 후 통과 확인)
M2.1 신규:      16 passed  (config_m2_1 5 + ollama_client_concurrency 3 + clip_labeler_concurrency 2 + store_concurrency 3 + progress_debounce 3)
회귀 보존:      +1 passed  (상위 묶음 회귀)
─────────────────────────────────────────────
합계 221 passed (active) + 2 deselected (clip_integration)
```

M2.1 수동 검증 단계는 [`milestones/M2.1_verification.md`](./milestones/M2.1_verification.md) §3 참고. M2 의 수동 검증 단계도 그대로 유효하며 [`milestones/M2_verification.md`](./milestones/M2_verification.md) §3 에 있다.

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

→ `221 passed, 2 deselected` 확인. 그러면 M0+M1+M2+M2.1 기준점이 유지되고 있다는 뜻.

venv 가 없는 새 PC 라면 [`CLAUDE.md §6`](./CLAUDE.md) 의 셋업 절차 그대로.

## 5. M3 시작 절차

M3 범위: **검색 백엔드 (FTS5 + 벡터 코사인 + 라벨 점수 + 통일성 가중치) + MCP stdio 서버 (도구 7~8개) + GUI 라이브러리 탭 최소 동작**. 일정 2주.

다음 세션 진입 시:

1. **새 브랜치 생성** — M2 머지 후 `main` 에서 `feat/m3-search-mcp` (또는 적당한 이름).
2. **MEMORY.md 자동 로드 확인** — 새 세션은 다음 8개 메모리를 자동 컨텍스트로 받는다:
   - 마일스톤 수동 검증 항목 표시 방식 (feedback)
   - PR/커밋 한글 (feedback)
   - M2 분석 클라이언트 백엔드 추상화 (project)
   - Ollama 멀티모달 API 형식 실측 (project)
   - 모델 출력 듀얼 언어 + GUI i18n (project)
   - 라벨 가중치 + CLIP v1 편입 (project, M2 끝 갱신본)
   - 검색 UX 전용 마일스톤 M4 신설 (project)
   - GAH 배포 전략 — torch CUDA/CPU 통합 빌드 (project)
3. **DESIGN.md 참조 섹션** — §4.3 (임베딩), §4.5 (MCP 서버 stdio/SSE), §4.6 (통일성 스코어러), §4.7 (사용 이력), §5.1 (projects/asset_usage/search_queries 신규 테이블), §6 (MCP 도구 명세 전체), §8.1 (검색 흐름 — 2단계 권장 + 1단계 빠른), §13 (Claude Code 워크플로 가이드).
4. **M3 plan 작성** — [`milestones/M2_plan.md`](./milestones/M2_plan.md) 를 템플릿으로 `M3_plan.md`. 핵심 산출물:
   - `src/gah/core/search.py` — FTS5 BM25 + 벡터 코사인 결합, 가중합 정렬
   - `src/gah/core/consistency.py` — `consistency_score(project, pack/asset)`
   - `src/gah/core/usage_tracker.py` — `record_asset_use` + 암묵 top-1 추정
   - `src/gah/mcp/server.py` — `mcp` 공식 SDK 바인딩, stdio 모드
   - `src/gah/mcp/tools.py` — `find_asset`, `suggest_packs`, `list_packs`, `list_assets`, `get_asset`, `record_asset_use`, `set_project_pin`, `request_rescan`, `report_feedback`
   - **메타 도구 3개** (`docs/MCP_USAGE_GUIDE.md` 권고) — `list_label_axes`, `list_labels(with_description)`, `describe_label`
   - DB 마이그레이션 — `projects`, `asset_usage`, `search_queries` 테이블 신설
   - `Config` 확장 — `consistency_weight` 의 세부 슬라이더(같은 팩/벤더/스타일/팔레트별), MCP 도구 활성화 토글
   - GUI 라이브러리 탭에 검색 박스 + 결과 그리드(최소 동작만; 풍부 UX 는 M4)
   - `--mcp` CLI 플래그 동작 — M2 의 `python -m gah --mcp` 가 "not implemented" 였던 자리 채움
   - `docs/MCP_USAGE_GUIDE.md` stub 을 본격 문서로 풀어쓰기 (실제 응답 JSON 예시 + signature 캐시 시나리오)
5. **M3_todo.md** — TDD 순서 체크리스트.
6. **테스트 먼저** — `tests/test_search.py`, `tests/test_consistency.py`, `tests/test_usage_tracker.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server_stdio.py`, `tests/test_store_m3.py`, `tests/test_library_search_ui.py` 등.
7. **구현 → 통과 → `M3_verification.md`** (사용자 수동 검증 항목은 마일스톤 끝 응답 본문에 단계별 체크리스트로 별도 제시 — 메모리 feedback 참조).

**M3 plan 작성 시 결정해야 할 항목**:

- 검색 가중치 공식 (DESIGN §4.6) 의 기본값 — `0.50 semantic + 0.20 keyword + 0.20 consistency + 0.10 recency` 그대로 갈지, M2 라벨 도입으로 `label_match` 항 추가할지
- MCP stdio 서버의 라이프사이클 — `--mcp` 모드는 트레이 GUI 없이 단독 프로세스 (passive) vs GUI 인스턴스가 동시에 stdio 만 추가로 노출 vs HTTP/SSE 별도 포트(`9874`)
- 라벨 부울 쿼리 파서를 M3 가 가질지 (M4 책임으로 미룰지) — 메모리 `project_search_ux_milestone.md` 는 M4 로 미루는 게 결정사항. M3 의 `find_asset` 은 `labels_any` / `labels_all` / `labels_none` 구조화 입력만 받게.

## 6. M2 에서 의도적으로 남겨둔 자리

- 라이브러리 탭의 `설명` 컬럼 — 현재 빈 문자열이다. Gemma 가 만든 자연어 description 을 별도 저장/조회하는 작업은 M3 의 `find_asset` 응답 확장 + (필요시) `asset_descriptions` 테이블 추가와 함께 다룬다. 라벨 컬럼은 정상 표시.
- `assets_fts.searchable_text` 에 라벨 description 이 인용부호 안에 박혀 있다 — M3 검색이 자연어 쿼리를 라벨 의미와 직접 매칭 가능. M2 자체에서 검색은 구현 안 함.
- `gah.core.analysis_queue.AnalysisQueue.enqueue_pack` / `enqueue_asset` 은 M3 의 `request_rescan` MCP 도구 백엔드로 그대로 사용 가능.
- `gah.core.labels.LabelRegistry.label_catalog_signature()` 는 MCP `list_labels` 응답의 `signature` 필드로 그대로 노출.
- `packs.aggregate_meta` JSON 의 `main_style` / `category_dist` / `palette` 가 M3 의 `consistency_score` 계산 입력.
- `gah.core.searchable.SearchableTexts.for_embed` 가 짧은 의미 압축 텍스트 — M3 가 같은 인코더 (`EmbeddingEncoder`) 로 검색 쿼리도 임베딩해 코사인 계산.
- `docs/MCP_USAGE_GUIDE.md` 는 stub. M3 끝에 실제 응답 JSON / 에러 케이스 / 캐시 무효화 시나리오로 풀어쓴다.

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
