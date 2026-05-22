# M11.10 Verification — Batch 완성 (text_embed multi-input)

- **Spec**: [`docs/superpowers/specs/2026-05-22-m11-10-batch-completion.md`](../docs/superpowers/specs/2026-05-22-m11-10-batch-completion.md)
- **Plan**: [`milestones/M11_10_plan.md`](./M11_10_plan.md)
- **Branch**: `feat/m11-10-batch-completion`
- **Baseline (post M11.9 + CLIP fix + helper)**: `1560 passed + 1 skipped + 57 deselected` (main `3c56f78`)

## 1. 자동 검증

### 1.1 회귀 (전체)

| 시점 | Command | 결과 |
|---|---|---|
| Phase 1-A red | `pytest tests/test_m11_10_batch_completion.py -v` | **12 failed + 2 passed** (12 red 의도) |
| Phase 1-B green (chain + gemini) | `pytest tests/test_m11_10_batch_completion.py -k "chain or gemini_embed_multi" -v` | **9 passed** |
| Phase 2 green (poller wiring) | `pytest tests/test_m11_10_batch_completion.py tests/test_batch_poller*.py -v` | **66 passed** (M11.10 14 + batch_poller 회귀 52) |
| Phase 3 광역 | `pytest -q` | **`1574 passed, 1 skipped, 57 deselected`** |

**회귀 카운트 변화** — baseline `1560` → final `1574` (+14). plan AC band `1564~1572` 의 상한 약간 초과 — chain 5 + gemini 4 + poller 6 케이스 모두 채택해 +14 (예상 4-5 케이스보다 풍부).

**`1 skipped`** 유지 — 기존 `test_web_routers_sse.py:140` heartbeat skip 그대로.

### 1.2 Red → Green 케이스 추적 (`tests/test_m11_10_batch_completion.py`, 14 케이스)

| # | 케이스 | 1-A (red) | Phase 1-B 후 | Phase 2 후 |
|---|---|:-:|:-:|:-:|
| 1 | `test_backend_chain_batch_embed_uses_primary_embed_multi` | ❌ | ✅ | ✅ |
| 2 | `test_backend_chain_batch_embed_fallback_to_loop_when_no_embed_multi` | ❌ | ✅ | ✅ |
| 3 | `test_backend_chain_batch_embed_only_text_embed_modality` | ❌ | ✅ | ✅ |
| 4 | `test_backend_chain_batch_embed_empty_returns_empty` | ❌ | ✅ | ✅ |
| 5 | `test_backend_chain_batch_embed_empty_chain_raises` | ❌ | ✅ | ✅ |
| 6 | `test_gemini_embed_multi_single_http_call` | ❌ | ✅ | ✅ |
| 7 | `test_gemini_embed_multi_empty_returns_empty` | ❌ | ✅ | ✅ |
| 8 | `test_gemini_embed_multi_transient_error_raises_backend_error` | ❌ | ✅ | ✅ |
| 9 | `test_gemini_embed_multi_hard_error_401` | ❌ | ✅ | ✅ |
| 10 | `test_batch_poller_chat_image_persists_embeddings_via_batch_embed` | ❌ | ❌ | ✅ |
| 11 | `test_batch_poller_chat_spritesheet_persists_embeddings_via_batch_embed` | ❌ | ❌ | ✅ |
| 12 | `test_batch_poller_chat_audio_persists_embeddings_via_batch_embed` | ❌ | ❌ | ✅ |
| 13 | `test_batch_poller_embed_failure_does_not_fail_chat_persist` | ✅ (vacuous) | ✅ | ✅ |
| 14 | `test_batch_poller_text_embed_modality_unchanged_path` | ✅ (vacuous) | ✅ | ✅ |

### 1.3 옵트인 LIVE (`pytest -m llm_integration`)

```powershell
pytest -m llm_integration -v
```
→ Sandbox: **17 skipped** — `GEMINI_API_KEY`/`OPENAI_API_KEY` env 미설정. 사용자 PowerShell 에서 env 설정 + 직접 재실행 필요 — `§4. 수동 검증 항목` 참조.

### 1.4 행동 변화 측면 (자동 확인)

`BackendChain.batch_embed` + `GeminiBackend.embed_multi` 신설로 **multi-input sync embed 경로** 추가.  기존 sync `BackendChain.embed(text)` 는 그대로 유지 (sync analyzer fallback path).

`BatchPoller._handle_succeeded` 흐름:
- chat_image/chat_spritesheet/chat_audio modality 성공 시: 기존 persist 후 `_persist_*_payload` 가 `searchable.for_embed` 텍스트 반환 → `chat_embed_targets` 누적 → 루프 종료 후 `_embed_chat_results` 가 1회 multi-input embed batch 호출 + 각 asset 별 `save_embedding`.
- text_embed modality 자체 경로: 변경 없음 (응답에서 직접 embedding 추출 + save).

`_embed_chat_results` 실패는 swallow (`log.exception`) — chat persist 자체는 정상 `'ok'` 마킹 보장.

## 2. 산출물 요약 (3 표면)

| 표면 | 변경 |
|---|---|
| 1. `core/llm/backends/gemini.py` | `GeminiBackend.embed_multi(texts: list[str]) -> list[list[float]]` 신설 — `client.models.embed_content(contents=list)` 1회 HTTP. transient/hard 에러 분류 `embed` stage 와 동일 |
| 2. `core/llm/chain.py` | `BackendChain.batch_embed(texts) -> (vectors, name)` 신설 — `text_embed` modality 전용. primary.embed_multi 우선 + fallback loop. 빈 input/non-text_embed/empty chain 가드 |
| 3. `core/batch/poller.py` | `_persist_image_payload` / `_persist_spritesheet_payload` / `_persist_audio_payload` 가 `searchable.for_embed` 반환 (return type `None` → `str`). `_handle_succeeded` 가 chat 결과 persist 후 `_embed_chat_results` 1회 호출. `_get_gemini_embed_model` 재사용 |

## 3. AC 달성 (spec §3)

| AC | 목표 | 자동 검증 결과 |
|---|---|---|
| AC #1 | 26 sprite 재분석 시 Gemini API ≤ 5 호출 | ⚠️ LIVE 필요 — code path 상으로는 1 chat_image batch + 1 multi-input embed + (leftover 분기 sync chat + sync embed) = **최대 4** 안에 도달 가능 (§4.1 수동 검증) |
| AC #2 | embedding 비용/품질 sync 와 동등 | ✅ `embed_multi` 가 SDK 의 list 인자 사용 — server-side 처리 후 input 순서대로 결과 반환. Gemini API spec 보장 |
| AC #3 | 1000 sprite latency 3× 단축 | ⚠️ 옵트인 LIVE 필요 |
| AC #4 | text_embed batch 진입 경로 명확 | ✅ `BatchPoller._embed_chat_results` — chat 모달 결과의 description 모아 `chain.batch_embed` 1회. `BackendChain.batch_embed` 가 single API |
| AC #5 | chat_spritesheet sync 분기 → batch 통합 | ✅ 단일 sprite (sheet 아님) 의 sprite_meta 는 batch path 후 추가 embed 까지 동일 모드로 처리 — 기존 PR #18/M11.2 의 `_persist_image_payload` → `_try_enrich_with_sheet` (시트 promote) 흐름 유지 + embedding 도 batch 로 합류 |
| AC #6 | `pytest -q` PASSED + 신규 red→green | ✅ `1574 passed + 1 skipped + 57 deselected` (M11.9 1560 + M11.10 14) |

## 4. 수동 검증 항목

CLAUDE.md §4.2 의 마일스톤 사이클: 자동 회귀는 ✅, 사용자가 한 번 더 확인할 것 두 가지.

### 4.1 LIVE Gemini API 호출 카운트 (≤5 검증)

1. **Fresh data-dir + helper script 부팅**:

   ```powershell
   .\scripts\launch-tray-test.ps1 m11-10-live
   ```

2. **`pixel_food_items_fruits` 팩 (26 sprite) drop** — `%TEMP%\m11-10-live_data\library\` 에 복사.

3. **분석 완료 대기** — 트레이 메뉴 `/analyzing` 페이지에서 진행률 100% 확인.

4. **Gemini API 호출 카운트 확인** — 로그 파일에서:

   ```powershell
   $logPath = "$env:TEMP\m11-10-live_data\logs\assetcache.log"
   Select-String -Path $logPath -Pattern "httpx.*POST.*google" | Measure-Object | Select-Object -ExpandProperty Count
   ```

   **기대값**: **≤ 5** (1 batchGenerateContent + 1 batchEmbedContents-multi + leftover sync 2~3). 현재 baseline 53.

5. **DB 검증**:

   ```powershell
   $db = "$env:TEMP\m11-10-live_data\metadata.db"
   sqlite3 $db "SELECT COUNT(*) FROM assets WHERE analysis_state='ok'"
   sqlite3 $db "SELECT COUNT(*) FROM asset_embeddings WHERE dim > 0"
   sqlite3 $db "SELECT COUNT(*) FROM sprite_meta"
   sqlite3 $db "SELECT COUNT(*) FROM asset_labels"
   ```

   **기대값**:
   - `assets WHERE analysis_state='ok'` = **26**
   - `asset_embeddings WHERE dim > 0` = **26** ⚠️ (이전엔 batch 경로 embedding 0개 누락 — 본 마일스톤 핵심 fix)
   - `sprite_meta` ≥ 26
   - `asset_labels` ≥ 4500 (CLIP label rows 포함)

### 4.2 옵트인 회귀 (Gemini 키 보유 시)

```powershell
$env:GEMINI_API_KEY = "..."
pytest -m llm_integration -v
```

**기대값**: 6 PASSED (M11.7 옵트인 baseline 유지 — Gemini batch chat/embed + inventory_item 분류).

## 5. 알려진 한계

- **AC #1 자동 검증 불가**: API 호출 카운트는 sandbox 에서 mock 만 가능. 실제 5 이하 도달 여부는 §4.1 LIVE 만 답할 수 있다.
- **`_embed_chat_results` 실패 시 embedding 누락**: chat 결과는 `'ok'` 상태로 남고 embedding 만 0. 사용자 검색 시 FTS BM25 만 가능 (cosine 누락) — 이는 의도된 graceful degradation (chat 결과를 다시 잃지 않기 위함). 다음 마일스톤 후보: embed 실패 시 batch_state `'pending_embed'` 별도 상태로 재시도 큐잉.
- **OpenAI / Ollama backend 의 multi-input embed**: 본 마일스톤 범위 외. `BackendChain.batch_embed` 가 `embed_multi` 미지원 backend 일 때 loop fallback 으로 graceful — 호출 수는 줄지 않지만 동작은 정상.
- **순서 매칭**: Gemini API spec 상 `embed_content(contents=list)` 의 결과 순서 = 입력 순서 (보장). 외부 SDK 가 응답 객체에 input id 를 동봉하지 않아 순서로만 매칭 — `zip(asset_ids, vectors)` 의 short-circuit (배열 길이 불일치) 도 graceful 처리됨.

## 6. LIVE 검증 결과 (2026-05-22 ~ 2026-05-23)

### 6.1 26 sprite `pixel_food_items_fruits` 팩 (AC #1 1차 검증)

| 시점 | Total | batchGenerateContent | batchEmbedContents | Sync generateContent |
|---|:-:|:-:|:-:|:-:|
| 1차 (race 잔존) | 8 | 1 | 4 | 3 |
| 2차 (race fix 후) | 10 | 1 | 4 | 0 |
| 최종 (race + cache) | **2** | 1 | 1 | **0** |

**AC #1 ≤5 호출 달성** — 26 sprite 재분석에 chat_image batch 1회 + multi-input embed batch 1회 = **2 호출** (목표 5, baseline 53).  **26× 감소** ✅.

### 6.2 142 assets 7 packs 대규모 LIVE (sheet detection)

| 항목 | 결과 |
|---|---|
| Total assets | 142 → 32 (re-import 케이스) → 33 |
| kind='spritesheet' | 26 (1D strip fallback 후) |
| kind='sprite' | 7 (모두 비정수배수 2D grid — known limit) |
| Sync `generateContent` | **0** |
| 라벨 풍부도 | 185-189 (모두 균일, CLIP 14 axes + Gemma) |

### 6.3 검증된 fix 누적

| Commit | Fix |
|---|---|
| `1b18bd7` | text_embed multi-input batch + chat 결과 embedding 채움 (PR 본문) |
| `fb5b3cb` | 트레이 "라이브러리 폴더 열기" UX |
| `84fb124` | next_pending_asset SQL 의 batch_state='none' 필터 |
| `4842bf0` | batch-only 정책 — toggle/threshold/polling 사용자 설정 제거 |
| `19854d4` | settings UI 정리 (batch 입력 form 제거) |
| `814ac54` | atomic try_mark_asset_analyzing (worker race guard) |
| `2e29fd0` | drain_pending 순서 + chat_image classify sheet 'queued' 마킹 |
| `48ec1e8` | text_embed modality 비활성 + stuck recover |
| `d82df2b` | fetch_pending_by_modality default 'queued' 포함 |
| `c5a4c8e` | detect_sheet ratio fallback (1D strip 정수배수) |
| `3fd2fdb` | thumbnail cache key 에 file_hash 포함 |
| `0215d2c` | tray library_dir 명시 인자 |
| `4304c35` | thumbnail Cache-Control: no-cache |

## 7. 알려진 한계

- **AC #1 자동 검증 불가**: API 호출 카운트는 sandbox 에서 mock 만 가능. 실제 5 이하 도달 여부는 §4.1 LIVE 만 답할 수 있다.  LIVE 결과 2 호출 (목표 5 초과 달성).
- **2D grid sheet detection 한계** — Female1/Male1-3 (256×576) 및 Warrior_Sheet-* (414×748) 같은 NxM grid 시트는 비정수 aspect ratio → 1D strip fallback 진입 X.  같은 팩 안 Male4 (32×48 frame × 96 grid) 는 grid_detect 의 alpha valley 임계가 우연히 통과해 인식.  **M11.11 별도 마일스톤**: `grid_detect.py` 임계 완화 + 파일명 `Sheet`/`Strip` keyword + GCD 기반 2D fallback.
- **`_embed_chat_results` 실패 시 embedding 누락**: chat 결과는 `'ok'` 상태로 남고 embedding 만 0. 사용자 검색 시 FTS BM25 만 가능 (cosine 누락) — 의도된 graceful degradation.
- **OpenAI / Ollama backend 의 multi-input embed**: 본 마일스톤 범위 외. `BackendChain.batch_embed` 가 `embed_multi` 미지원 backend 일 때 loop fallback 으로 graceful — 호출 수는 줄지 않지만 동작은 정상.
- **순서 매칭**: Gemini API spec 상 `embed_content(contents=list)` 의 결과 순서 = 입력 순서 (보장).  `zip(asset_ids, vectors)` 의 short-circuit 도 graceful.
- **stuck browser cache** — 이전 prod LIVE 의 `max-age=86400` 응답이 browser disk cache 에 24h 유지.  본 PR 의 `Cache-Control: no-cache` 는 새 응답에만 적용 → 사용자가 한 번 cache 청소하면 그 후 안 생김.

## 8. 다음 작업 (별도 트리거)

- **M11.11 후보** — 2D grid sheet detection 정확도 강화 (grid_detect alpha 임계 완화 + 파일명 keyword + GCD 기반 2D fallback)
- **v0.2.9 publish** — M11.9 + CLIP fix + M11.10 batch 완성 동시 deliver.  `pyproject.toml` + `__init__.py` 0.2.7 → 0.2.9 bump + tag (사용자 명시 시)
- **M11.x patches backlog item D** — OpenAI Batch API embed (`OpenAIBackend.embed_multi` 추가 시 chain 자동 활용)
- **AC #3 1000 sprite wall-clock 측정** — 옵트인 perf 테스트로 정착 후보
