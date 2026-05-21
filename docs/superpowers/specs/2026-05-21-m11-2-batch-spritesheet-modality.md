# 2026-05-21 — Batch Spritesheet Modality Design Spec (M11.2 / v0.2.2 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md) — M11 / M11.1 / M12 사이의 minor patch
- 전제: [`2026-05-20-gemini-batch-api-design.md`](./2026-05-20-gemini-batch-api-design.md) (M11.1, v0.2.1 publish 완료) + [PR #18](https://github.com/v0o0v/assetcache-mcp/pull/18) v0.2.x patch A/B/C (batch persist 보강, main `12ebc42`)
- 본 spec 다음: `milestones/M11_2_plan.md` (이미 starter 존재) → `M11_2_todo.md` → TDD cycle
- Version 후보: **v0.2.2 patch** (옵트인 동작, 기존 사용자 영향 0). M11.1 의 자식.

## 1. 한 줄 요약

Spritesheet (sprite 의 시트 변형 — Aseprite/TexturePacker export 또는 grid PNG) 도 batch 50% 비용 절감을 받도록 신규 modality `chat_spritesheet` 신설. BatchManager 가 fetch 단계에서 `detect_sheet` 호출 → 시트로 식별된 자산은 별 batch job 으로 묶고, **시트 전용 prompt + 8칸 composite preview** 를 Gemini 에 전송. BatchPoller 는 시트 응답을 sync `SpritesheetAnalyzer` 와 **동등한** 라벨 (frameTags + Gemma `animation_hint` 추측) + sprite_meta (frame_w/h/count + animations_json) 로 변환. PR #18 의 한계 (grid-only 시트가 animation 라벨 비어 있음) 완전 해소.

## 2. Context — 현재 코드 표면 (main `12ebc42`, 회귀 1490)

### 2.1 핵심 모듈 (PR #18 머지 후)

`src/assetcache/core/batch/manager.py` (M11.1):
- `_MODALITY_KIND_FILTER["chat_image"] = ("sprite", "spritesheet")` — 현재 sprite + spritesheet 를 단일 modality 로 묶음
- `_build_chat_requests(modality, rows)` → `analyzer.messages.build_image_chat_messages(abs_path, BATCH_IMAGE_PROMPT)` 호출
- `BATCH_IMAGE_PROMPT` (analyzer/messages.py): category/style/mood/palette/subject/description/confidence 만 — **animation 정보 없음**

`src/assetcache/core/batch/poller.py` (PR #18 patch C):
- `_persist_image_payload(asset, payload)` 가 detect_sheet 후 시트면 frame_w/h/count + frameTags 라벨 + kind promote
- 단 batch payload 에 `animation_hint` 가 없으므로 Gemma 추측 라벨은 부재 (sync 의 `_call_gemma` 가 시트 합성 strip 을 별도로 보내는 게 핵심)

`src/assetcache/core/analyzer/spritesheet.py` (M6):
- `_call_gemma(img_b64, language)` — 8칸 합성 strip + 시트 전용 system prompt
  ```
  Input is a horizontal strip of sprite frames.
  - animation_hint: array (1..4) from [{anim_enum}]
  ```
- `make_preview_composite(src, frames, max_size=768)` — 8칸 추출 + 가로 strip 합성

`src/assetcache/core/analyzer/spritesheet_meta.py` (PR #18 patch C):
- `enrich_sprite_meta_with_sheet(base, detection)` — frame 박스/count + animations_json
- `detection_to_animation_labels(detection, source="gemma", score=1.0)` — frameTags → LabelScore

### 2.2 회귀 baseline

`pytest -q` → **1490 passed + 3 skipped + 56 deselected** (main `12ebc42`).

### 2.3 Config 키 (현재)

```toml
[chains]
chat_image = ["gemini", "ollama"]
chat_audio = ["gemini", "ollama"]
text_embed = ["gemini", "ollama"]
```

본 spec 추가 (§5 참조):

```toml
[chains]
chat_spritesheet = ["gemini", "ollama"]   # optional — 없으면 chat_image 로 fallback
```

배치 임계값/poll/toggle 은 그대로 (`[batch]`).

## 3. 결정 매트릭스 — 옵션 분석

### 3.1 spritesheet → batch 통합 방안 (사용자 결정: 옵션 ④)

| 옵션 | 설명 | 채택 |
|---|---|---|
| ① 현 상태 수용 | grid-only 시트는 animation 라벨 없이 운용 | ❌ |
| ② `BATCH_IMAGE_PROMPT` 에 conditional `animation_hint` 추가 | 단일 PNG 로는 시트 인식률 낮음, false-positive risk | ❌ |
| ③ 시트는 batch 우회 + sync 처리 | batch 비용 절감 효과 감소 | ❌ |
| **④ `chat_spritesheet` modality 신설 + 합성 strip + 시트 전용 prompt** | sync 와 동등 정확도, 50% 비용 유지 | **✅** |

### 3.2 modality 분리 시점

| 옵션 | 채택 |
|---|---|
| AnalysisQueue 등록 시점 (자산 추가 시) detect_sheet | ❌ (워처 처리 부담 + 큰 시트는 I/O 비용) |
| BatchManager fetch 시점 detect_sheet — kind='sprite' 후보를 시트 vs 단일로 분리 | ✅ (이미 batch 임계값 충족 시점에만 작업) |

### 3.3 kind promote 시점

- BatchManager 가 fetch 후 시트 감지하면 즉시 `update_asset_kind("spritesheet")` 호출 → `chat_spritesheet` 큐로 묶음
- 또는 BatchPoller 가 결과 받은 후 promote (현재 PR #18 동작)
- 채택: **BatchManager fetch 시점에 promote** — modality 결정이 즉시 일관됨

### 3.4 신규 자산의 첫 분석

신규 시트는 kind='sprite' 로 등록됨. BatchManager fetch 가 detect_sheet → kind='spritesheet' promote + chat_spritesheet 큐로 분류. 따라서 **첫 batch 진입에서 promote** — sync 와 동일하게 첫 분석에서 인식.

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ AnalysisQueue (interactive)                                       │
│   pending_by_modality("chat_image") → count                       │
└────────────────────────┬─────────────────────────────────────────┘
                         │ count >= threshold + chain[0]=gemini
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ BatchManager.try_submit("chat_image")                             │
│   1. fetch_pending_by_modality("chat_image") → raw_rows           │
│   2. NEW: classify_sheet_vs_sprite(raw_rows, library_dir)         │
│      → (sheet_rows, sprite_rows) + promote sheet rows kind        │
│   3. if len(sheet_rows) >= threshold: spawn chat_spritesheet job  │
│   4. if len(sprite_rows) >= threshold: spawn chat_image job       │
│      (otherwise wait for next sweep)                              │
└────────────────────────┬─────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                          ▼
   chat_image job             chat_spritesheet job
   (단일 PNG + IMAGE prompt)   (composite strip + SPRITESHEET prompt)
            │                          │
            ▼                          ▼
   BatchPoller._persist_image_   BatchPoller._persist_spritesheet_
   payload (sprite + grid-only   payload (sync 와 동등 frame +
   시트 — 현재 PR #18 동작)        animation_hint)
```

## 5. Module breakdown

### 5.1 신규 / 변경 파일

| 파일 | 변경 |
|---|---|
| `src/assetcache/core/store.py` | `_MODALITY_KIND_FILTER` 갱신: `chat_image=("sprite",)` + `chat_spritesheet=("spritesheet",)` (sprite/spritesheet 분리) |
| `src/assetcache/core/llm/registry.py` 또는 `chain.py` | `BackendChain.get_chain("chat_spritesheet")` — chains 에 키 없으면 자동 `chat_image` fallback |
| `src/assetcache/core/analyzer/messages.py` | 신규 상수 `BATCH_SPRITESHEET_PROMPT` (animation_hint enum 동적 주입) + 신규 함수 `build_spritesheet_chat_messages(abs_path, detection, prompt, max_long_edge=768)` — make_preview_composite 호출 + base64 |
| `src/assetcache/core/batch/manager.py` | `_MODALITIES` 에 `chat_spritesheet` 추가. `try_submit` 분기: chat_image 시 sheet/sprite 분류 후 각각 try (또는 fetch 단계에서 promote 먼저). `_build_chat_requests` 가 modality 별 builder 선택 — chat_spritesheet 는 detect_sheet 호출 + build_spritesheet_chat_messages 사용 |
| `src/assetcache/core/batch/poller.py` | `_handle_succeeded` 의 modality switch 에 `chat_spritesheet` 추가 → `_persist_spritesheet_payload(asset, payload)`. 새 메서드는 detect_sheet 한 번 더 + enrich_sprite_meta_with_sheet + detection_to_animation_labels + payload `animation_hint` → 추가 라벨 (sync `_call_gemma` 의 추측 라벨 부분) + kind promote 확인 |
| `src/assetcache/web/routers/analyzing.py` | dashboard partial template — `chat_spritesheet` modality 카운트 추가 |
| `src/assetcache/web/templates/_analyzing_partial.html` | modality 라벨 (i18n) 추가 |
| `src/assetcache/locale/{ko,en}/LC_MESSAGES/assetcache.po` | 신규 msgid: "Spritesheet batch", "spritesheet" + spec 진행 중 추가 |
| `src/assetcache/config.py` | 변경 없음 (chains 에 chat_spritesheet 는 optional, fallback 처리는 chain 쪽) |
| `milestones/M11_2_*.md` | plan / todo / verification |

### 5.2 신규 시트 분류 helper

`src/assetcache/core/batch/sheet_classifier.py` (신규):

```python
def classify_image_assets(
    rows: list[AssetRow],
    *,
    library_dir: Path,
    store: Store,
) -> tuple[list[AssetRow], list[AssetRow]]:
    """detect_sheet 실행 후 (sheet_rows, sprite_rows) 분리 + kind promote.
    
    sheet_rows: detect_sheet hit + kind='spritesheet' 으로 promote 됨
    sprite_rows: detect_sheet miss 또는 file I/O 오류 — 일반 sprite
    """
```

이 helper 는 `BatchManager.try_submit("chat_image")` 안에서 호출.

### 5.3 SpritesheetAnalyzer 재사용

sync 의 `SpritesheetAnalyzer._call_gemma` 와 같은 prompt 사용. enum 주입 / payload schema 동일 → `validate_image_payload` 가 그대로 검증 가능 (animation_hint 만 추가 처리).

## 6. Test strategy

### 6.1 신규 단위 테스트

| 파일 | 범위 |
|---|---|
| `tests/test_batch_sheet_classifier.py` | classify_image_assets — JSON 사이드카 fixture / grid PNG / 비-시트 fixture, promote 검증 |
| `tests/test_analyzer_messages_spritesheet.py` | BATCH_SPRITESHEET_PROMPT enum 주입 + build_spritesheet_chat_messages composite strip 생성 |
| `tests/test_batch_manager_spritesheet.py` | try_submit 분기 — sheet/sprite 분리 후 두 modality 각각 try / 임계값 분리 카운트 |
| `tests/test_batch_poller_spritesheet_modality.py` | _persist_spritesheet_payload — animation_hint payload + frameTags 합산 + kind 보존 |

### 6.2 통합 / e2e

- `tests/test_batch_end_to_end.py` 확장 — 시트 + 단일 sprite 혼합 30+ asset → 두 modality job 각각 제출 검증

### 6.3 옵트인 integration (실 Gemini API)

- `tests/test_llm_backend_gemini_batch_integration.py` 확장 — `test_batch_chat_spritesheet_submit_and_cancel` (3 → 4 case)

### 6.4 회귀 baseline

main `12ebc42` 기준 **1490** → M11.2 완료 시 약 +30 ~ +50 신규 테스트 예상.

## 7. Data shape

### 7.1 DB 변경 — 없음

`assets.kind` 컬럼이 이미 `spritesheet` 값을 가짐. `batch_jobs.modality` 컬럼이 자유 문자열이므로 `chat_spritesheet` 도 그대로 저장 가능. **마이그레이션 0**.

### 7.2 Config 변경

`[chains]` 에 `chat_spritesheet` 키 optional 추가. 없으면 자동 fallback (chain.py 갱신). 기존 사용자 영향 0.

### 7.3 i18n 추가 msgid (예상 6~10개)

- "Spritesheet batch"
- "spritesheet" (modality 라벨)
- 시트 검출 실패 안내 (있다면)

## 8. UI 변경

### 8.1 /settings batch 카드

- chain 카드의 modality 표에 `chat_spritesheet` 행 추가 (현재 image/audio/embed 3행 → 4행)
- 기본값: chat_image 와 동일 (fallback 사용)

### 8.2 /analyzing dashboard

- Summary 섹션 카운트: image / audio / spritesheet / embed (4 modality)
- Batch jobs 섹션 — modality 컬럼이 spritesheet job 도 자연 표시

## 9. 알려진 한계

| 항목 | 우선순위 | 후속 |
|---|---|---|
| `make_preview_composite` 가 batch 에서 매번 호출 — 큰 시트는 file I/O 약간 부담 (fetch 시 + persist 시 detect_sheet 2회) | 낮 | preview 캐시 또는 fetch 시 detection 결과를 batch_jobs row 에 직렬화 보관 가능 |
| Grid-detect-only 시트는 frameTags 가 없으므로 Gemma 추측 라벨만 의존 | 낮 (현재 sync 동일) | — |
| spritesheet batch 결과의 multimodal payload size — composite strip base64 ≈ sprite 1장 (max_long_edge=768 동일) | 낮 | 일반 sprite 와 비슷한 부담 |
| 첫 batch 진입 전 detect_sheet 가 매번 발생 — repeated drop 시 매번 재계산 | 낮 | 캐시 가능 (assets 컬럼 또는 별도 cache) |

## 10. 다음 단계

1. 이 spec 사용자 검토
2. `milestones/M11_2_plan.md` 확장 (Phase 분할, 각 Phase 별 산출물, 신규 테스트 list)
3. `M11_2_todo.md` 체크리스트 (TDD red → green 순서)
4. Phase 별 TDD cycle
5. `M11_2_verification.md` 수동 검증 시나리오
6. PR → main → tag v0.2.2 → Trusted Publishing 자동 publish

작업 단위 추정: **~2~3일** (modality 1개 추가 + composite 통합 + 약 30~50 신규 테스트). M11.2 의 patch 성격에 부합.
