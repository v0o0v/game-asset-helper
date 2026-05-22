<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# core

## Purpose
도메인 로직 — 외부 의존성(GUI / MCP / Web) 과 분리된 순수 비즈니스 코드. M1 의 SQLite store + Pack Manager + Scanner + Watcher 가 토대고, M2~M11.7 의 분석/배치/LLM/시트/Unity import/updater 가 그 위에 얹힌다.

## Key Files
| File | Description |
|------|-------------|
| `store.py` | SQLite WAL 메타데이터 store — assets / packs / labels / asset_usage / projects / unity_imports / saved_searches / batch_jobs. `write_lock` 으로 GUI ↔ MCP stdio 동시 write 직렬화 |
| `pack_manager.py` | 팩 디렉터리 인테이크 — `pack.json` 매니페스트 + 벤더 휴리스틱 + 파일 인덱싱 + 팩 집계 메타 산출 |
| `scanner.py` | `reconcile_library()` — 부팅 직후 라이브러리 풀스캔, DB 와 diff |
| `watcher.py` | `LibraryWatcher` — watchdog 재귀 감시 + 팩 단위 디바운스 (2초 윈도우) + `asyncio.Queue` 태스크 발행 |
| `analysis_queue.py` | `AnalysisQueue` — `asyncio.PriorityQueue[PackIntakeTask\|AssetTask]` + ThreadPoolExecutor 워커 (M2.1 동시성 1→3) |
| `asset_kind.py` | 확장자 + 시그니처로 sprite / spritesheet / sound 분류 |
| `manifest.py` | `pack.json` / `pack.toml` 스키마 (Pydantic) + 파서 |
| `labels.py` | `LabelRegistry` + 시드 라벨 (24 axis: category / mood / palette / animation / vibe ...) |
| `label_query.py` | label_query 미니 문법 파서 — `axis:label AND/OR/NOT (...)`. 순수 AND or 순수 OR 만 허용 |
| `embedding.py` | `EmbeddingEncoder` — `sentence-transformers` 기반 텍스트 임베딩 |
| `clip_labeler.py` | `ClipLabeler` + `OpenClipBackend` — 이미지 의미 라벨링 (open_clip_torch) |
| `consistency.py` | `ConsistencyScorer` — 프로젝트별 사용 이력 + 같은 팩/벤더 가중치 |
| `search.py` | `HybridSearcher` — 6채널 (FTS5 + 임베딩 + 라벨 + 통일성 + 인기도 + 피드백 페널티) 하이브리드 검색 |
| `searchable.py` | `Searchable` 인덱스 빌더 — FTS5 + 임베딩 동기화 |
| `suggest_packs.py` | `suggest_packs` MCP 도구 본체 + 썸네일 enrich |
| `pack_aggregate.py` | 팩 단위 집계 메타 (주 스타일 / 도미넌트 팔레트 / 픽셀아트 비율 / 카테고리 분포 / 평균 해상도·길이) |
| `usage_tracker.py` | `UsageTracker` — `record_asset_use` / `report_feedback` 이력 누적 |
| `thumbnails.py` | 썸네일 캐시 (Pillow resize → PNG) |
| `ollama_client.py` | Ollama `/api/chat` 얇은 HTTP 래퍼 (모든 backend 의 1차 추상화) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `analyzer/` | sprite / sound / spritesheet 분석기 + 메시지 + tech_meta + spritesheet_meta + payload parser (see `analyzer/AGENTS.md`) |
| `batch/` | Gemini Batch API 제출/폴링 (M11.1) + 시트 classifier + detection cache (M11.3) (see `batch/AGENTS.md`) |
| `llm/` | Multi-backend LLM 추상화 (M11) + 6 backend wrapper (see `llm/AGENTS.md`) |
| `sheet/` | 스프라이트 시트 검출 / 격자 추정 / JSON 사이드카 파서 / 미리보기 합성 (M6) (see `sheet/AGENTS.md`) |
| `unity_import/` | Unity Asset Store `.unitypackage` 임포트 (M7) (see `unity_import/AGENTS.md`) |
| `updater/` | PyPI 신버전 알림 (M10 Phase 2) — semver + checker + pip command 분기 (see `updater/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **store.py 는 모든 DB 쓰기의 공통 경로** — 새 컬럼 추가 시 `migration` schema 갱신 + 새 store helper + 회귀 테스트 (`tests/test_store_m*.py`) 까지 한 묶음.
- **WAL + busy_timeout=5000** — 동시 write 충돌 흡수. `store.write_lock` 안에서 트랜잭션을 묶지 않으면 race 발생 가능.
- **LabelRegistry 시드 수정 시** — `tests/test_label_registry_seed.py` 의 axis 인벤토리 갱신 필요.
- **M11.8 작업 시 핵심 주의** — `palette.neutral` 절대 비활성화 X (M11.6 tone group enum 핵심). `mood.neutral` + `mood.minimalist` 만 `is_enabled=0` 마이그.
- **batch 시드 / migration 마커** — `meta.disabled_by_default_signature` 같은 한 번만 적용하는 마이그는 시그니처로 멱등성 보장.
- **sync ↔ batch parity** — `analyzer/sprite.py` 의 `_build_system_prompt` 가 `analyzer/messages.py` 의 BATCH_* 프롬프트와 같은 라벨 enum / hex 금지 / palette 가이드를 따라야 함 (M11.4 parity 회귀).

### Testing Requirements
- 모듈별 회귀: `tests/test_{모듈}.py` + M{N} 별 마일스톤 회귀 `tests/test_{모듈}_m{N}.py`.
- store 동시성: `tests/test_store_concurrency.py` + `test_ollama_client_concurrency.py`.
- 배치 end-to-end: `tests/test_batch_end_to_end.py` (concurrency=0 + BatchManager/Poller 직접 instantiate 패턴, project memory `project_batch_path_drive_pattern`).

### Common Patterns
- 모듈 간 의존 단방향: store/manifest/labels (저수준) → scanner/watcher/queue → analyzer/batch → search/suggest_packs/usage_tracker (고수준).
- `ConsistencyScorer` + `feedback_penalty` 모두 `project_id` 필수.
- WAL 검증용 fresh `--data-dir` 격리 패턴 — 사용자 실 DB 안 건드리고 `$TEMP/{scenario}_data` 사용 (project memory `project_verification_fresh_data_dir`).

## Dependencies

### Internal
- 위로 `mcp/` `web/` `app.py` 가 모두 이 패키지에 의존.

### External
- watchdog, Pillow, librosa, soundfile, numpy, httpx, pydantic, open_clip_torch, torch, sentence-transformers (간접), platformdirs.

<!-- MANUAL: M11.8 implement 시 palette.neutral 절대 유지. mood.neutral + mood.minimalist 만 `is_enabled=0`. -->
