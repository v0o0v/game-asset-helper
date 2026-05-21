# 2026-05-21 — Detection Cache Design Spec (M11.3 / v0.2.2 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md) — M11.2 의 후속 patch
- 전제: [`2026-05-21-m11-2-batch-spritesheet-modality.md`](./2026-05-21-m11-2-batch-spritesheet-modality.md) (M11.2, [PR #19](https://github.com/v0o0v/assetcache-mcp/pull/19) main 머지 `d34f1dd`)
- 본 spec 다음: `milestones/M11_3_plan.md` (starter) → `M11_3_todo.md` → TDD cycle
- Version 후보: **v0.2.2 patch** (M11.2 와 묶어 publish — 수동 검증 한 번에)

## 1. 한 줄 요약

M11.2 가 도입한 `detect_sheet` 의 같은 자산 **3중 호출** (chat_image classify / chat_spritesheet classify / BatchPoller persist) 을 2-층 캐시로 1회 호출로 압축. grid-only 시트가 다수인 라이브러리에서 가장 큰 효과 — `grid_detect` (Pillow + numpy alpha 격자 분석) 가 시트당 ~5~50ms 의 무거운 path 라 시트 100장 sweep 당 ~6초 절약.

## 2. Context — 현재 코드 표면 (main `d34f1dd`, 회귀 1528)

### 2.1 detect_sheet 호출 위치 (M11.2 머지 후)

| 호출 위치 | 빈도 | 비용 |
|---|---|---|
| `BatchManager._do_submit("chat_image")` → `classify_image_assets` | 시트 식별 + kind promote 시점 | 시트당 1회 |
| `BatchManager._do_submit("chat_spritesheet")` → `classify_image_assets` | 다음 sweep, kind='spritesheet' rows 의 builder 입력 detection 확보용 | 시트당 1회 |
| `BatchPoller._persist_spritesheet_payload` → `_try_enrich_with_sheet` → `detect_sheet` | batch 응답 처리 시 (~수분 ~ 24h 후) | 시트당 1회 |

→ **시트당 3회 호출**. grid-only 시트가 다수면 누적 비용 큼.

### 2.2 회귀 baseline

`pytest -q` → **1528 passed + 3 skipped + 56 deselected** (main `d34f1dd`).

## 3. 결정 매트릭스 — 옵션 분석 (사용자 결정 완료)

| 옵션 | 작업량 | 효과 범위 | 마이그 | 채택 |
|---|---:|---|---|---|
| A. `batch_request_detections` 별도 테이블 (per-asset detection JSON) | ~1일 | submit ↔ persist 24h 시간차까지 유효. 균일/비균일 모두 | 1 | ❌ |
| **B. `sprite_meta.animations_json` 활용 (DB cross-sweep)** | ~0.5일 | 균일 격자 + JSON 사이드카 모두. frames 재구성 가능 | 0 | ✅ |
| **C. BatchManager instance dict (메모리 sweep cache)** | ~2시간 | 같은 sweep 의 chat_image classify ↔ chat_spritesheet classify 만 | 0 | ✅ |

**채택: B + C 결합** (~0.7일).

이유: grid-only 시트가 다수인 일반 게임 라이브러리에서 `grid_detect` 가 가장 무거운 path. 균일 격자라 `frame_w/h/count` 만 알면 frames 좌표 deterministic 재구성. JSON 사이드카 시트의 `parse_json` 은 가벼우니 캐시 미스해도 비용 미미.

## 4. Architecture

```
sweep N (chat_image)                  sweep N (chat_spritesheet)         sweep N+M (poll)
                                                                          
fetch rows                            fetch rows                          fetch job
  │                                     │                                   │
  ▼                                     ▼                                   ▼
classify_image_assets                 classify_image_assets               _persist_spritesheet_payload
  cache=mgr._detection_cache  ──►       cache=mgr._detection_cache         (no cache arg)
  │ for row:                            │ for row:                          │
  │   if cache[row.id] exists ──┐       │   if cache[row.id] exists ──┐    │
  │     skip detect_sheet      │       │     skip detect_sheet      │    │
  │   else:                    │       │   else:                    │    │
  │     detect_sheet           │       │     detect_sheet           │    │
  │     cache[row.id] = ...    │       │     cache[row.id] = ...    │    │
  │                            │       │                            │    │
  │ if hit:                    │       │ if hit:                    │    │
  │   enrich sprite_meta       │       │   already enriched         │    │
  │   save_sprite_meta ────────┼───────┼──────────────────┐         │    │
  │   update_asset_kind        │       │   update_asset_kind        │    │
  │                            │       │                            │    │
  ▼                            ▼       ▼                            ▼    ▼
                                                                       _try_enrich_with_sheet
                                                                          │
                                                                          ▼
                                                                       store.get_sprite_meta(asset_id)
                                                                          │ if sprite_meta.animations_json
                                                                          │   재구성 (no detect_sheet)
                                                                          │ else
                                                                          │   detect_sheet (legacy path)
```

- **C (메모리 dict)**: same-sweep 중복 제거 (chat_image classify 가 채운 결과를 chat_spritesheet classify 가 재사용). BatchManager 라이프타임 동안 유지. process 재시작 시 사라짐.
- **B (DB sprite_meta)**: cross-sweep + persist 단계 우회. sprite_meta 가 이미 enrich 돼 있으면 detect 자체를 안 함.

## 5. Module breakdown

### 5.1 신규 / 변경 파일

| 파일 | 변경 |
|---|---|
| `src/assetcache/core/batch/sheet_classifier.py` | `classify_image_assets(...)` 시그니처에 `cache: dict[int, SheetDetection | None] | None = None` 추가. 시트 hit 시 `enrich_sprite_meta_with_sheet + save_sprite_meta` (옵션 B) 도 함께 수행. `compute_sprite_meta` 가 필요 — `tech_meta.compute_sprite_meta` 호출 |
| `src/assetcache/core/batch/manager.py` | `self._detection_cache: dict[int, SheetDetection | None]` 초기화. `_do_submit("chat_image")` 와 `("chat_spritesheet")` 가 `cache=self._detection_cache` 전달. 무한 성장 방지를 위해 cache 크기 상한 (e.g., 1024 entries — 사용자 라이브러리 보통 1000장 이내) 또는 sweep 종료 시 clear |
| `src/assetcache/core/batch/poller.py` | `_try_enrich_with_sheet` 가 `store.get_sprite_meta(asset_id)` 먼저 확인. `sprite_meta.animations_json is not None` 이거나 `sprite_meta.frame_w` 채워져 있으면 detect 우회 + 캐시된 sprite_meta + 재구성된 AnimationSpec 리스트로 `detection_to_animation_labels` 호출 |
| `src/assetcache/core/store.py` | `get_sprite_meta(asset_id)` 가 이미 존재하는지 확인 — M2 이후 어디서든 사용했을 듯. 없으면 신설 (단순 SELECT) |
| `tests/test_batch_sheet_classifier_cache.py` (신규) | cache 인자 동작, hit/miss, sprite_meta 자동 save 검증 |
| `tests/test_batch_manager_detection_cache.py` (신규) | sweep cache 가 chat_image → chat_spritesheet 사이 재사용 검증 |
| `tests/test_batch_poller_sprite_meta_cache.py` (신규) | sprite_meta 가 이미 enrich 돼 있으면 detect_sheet 우회 검증 |

### 5.2 classify_image_assets 시그니처 확장

```python
def classify_image_assets(
    rows: list[AssetRow],
    *,
    library_dir: Path | None,
    store: Store,
    cache: dict[int, "SheetDetection | None"] | None = None,
    save_sprite_meta: bool = True,   # M11.3 — 시트 hit 시 sprite_meta 자동 enrich+save
) -> tuple[list[tuple[AssetRow, SheetDetection]], list[AssetRow]]:
```

- `cache=None` → 기존 동작 (메모리 캐시 미사용).
- `save_sprite_meta=True` → 시트 hit 시 `compute_sprite_meta + enrich_sprite_meta_with_sheet + store.save_sprite_meta`. detect 결과를 sprite_meta 에 영속 저장 (옵션 B).
- 호환성: 둘 다 default 활성화. 기존 호출 (sheet_classifier 만의 직접 테스트) 는 cache 인자 없어도 OK, save_sprite_meta=True 가 의도된 새 동작.

### 5.3 BatchManager `_detection_cache` 정책

- **수명**: BatchManager instance lifetime. process 재시작 시 사라짐.
- **상한**: 1024 entries (라이브러리 보통 ≤ 1000장 시트). 초과 시 가장 오래된 entry 제거 (LRU `collections.OrderedDict`).
- **invalidate**: 명시적 호출 없음. 시트 파일 변경 시 stale 가능성 — sprite_meta cache (옵션 B) 의 stale 이슈와 동일. 향후 patch 후보.

### 5.4 BatchPoller `_try_enrich_with_sheet` 캐시 활용

```python
def _try_enrich_with_sheet(self, asset, base_meta):
    if self._library_dir is None:
        return None
    # M11.3 — 옵션 B: sprite_meta cache 확인
    existing = self._store.get_sprite_meta(asset.id)
    if existing is not None and (existing.animations_json or existing.frame_w):
        # 이미 enrich 됨 — frameTags 재구성 + detect_sheet 우회.
        anim_specs = _animations_json_to_specs(existing.animations_json or {})
        det = SheetDetection(frames=[], tags=anim_specs, source="cached")
        # frame 좌표가 필요한 다른 path (composite builder) 는 BatchPoller persist 단계엔 없음 —
        # 라벨 합산만 필요. detection_to_animation_labels 는 tags 만 보면 됨.
        return existing, detection_to_animation_labels(det)
    # 기존 path — detect_sheet 호출
    try:
        ...
```

## 6. Test strategy

### 6.1 신규 단위 테스트 (~15건 예상)

| 파일 | 범위 | 케이스 |
|---|---|---:|
| `tests/test_batch_sheet_classifier_cache.py` | cache hit/miss / save_sprite_meta=True 자동 enrich / library_dir=None graceful | 5 |
| `tests/test_batch_manager_detection_cache.py` | same-sweep chat_image → chat_spritesheet 시 detect_sheet 1회만 / cache size 상한 LRU eviction / process 재시작 시 사라짐 | 5 |
| `tests/test_batch_poller_sprite_meta_cache.py` | sprite_meta enrich 됐으면 detect_sheet 0회 / 재구성된 anim_labels = 원본과 동일 / animations_json 비어 있으면 fallback | 5 |

### 6.2 회귀

- M11.2 의 7 테스트 파일 모두 통과 유지
- 회귀 baseline 1528 → ~1543 (+15 신규)

### 6.3 옵트인

없음 — 외부 API 호출 변경 0.

## 7. Data shape

### 7.1 DB 변경 — 없음

`sprite_meta` 테이블의 `animations_json` / `frame_w/h/count` 컬럼은 M6 부터 존재. 별도 마이그 0.

### 7.2 Config 변경 — 없음

옵션 켜고 끄는 toggle 도 일단 미적용 (옵션 켜진 채 ship). 향후 문제 발견 시 `cfg.batch.detection_cache_enabled = True/False` 추가 가능.

## 8. UI 변경

- /analyzing, /settings 변경 0.
- 내부 동작 최적화만이므로 UI 노출 X.

## 9. 알려진 한계 / 향후

| 항목 | 우선순위 | 후속 |
|---|---|---|
| 시트 파일이 24h 사이에 바뀌면 sprite_meta cache stale | 낮 | 파일 hash 비교 후 invalidate — 별도 patch (옵션 D) |
| BatchManager instance memory cache 가 multi-process 환경에서 공유 X | 낮 | tray app 은 single-process 라 영향 없음. M14 (원격 통신) 진입 시 검토 |
| Aseprite 비균일 hash-mode 시트의 frames 재구성 — sprite_meta 만으론 좌표 정확히 복원 불가 | 낮 (parse_json 자체가 가벼움) | 옵션 A 별도 테이블 추가 (~1일) 시 해소 |
| sprite_meta cache hit 시 frame 좌표 (각 frame 의 x,y,w,h) 가 필요한 코드 path 가 있다면 사용 못 함 — BatchPoller persist 는 라벨 합산만 필요해서 영향 X | 낮 | composite builder (BatchManager classify) 는 이미 detect 결과의 detection 객체 직접 사용 — cache hit 가능 |

## 10. 다음 단계

1. 이 spec 사용자 검토
2. `milestones/M11_3_plan.md` 작성 (Phase 분할, TDD step 별 코드)
3. `M11_3_todo.md` 체크리스트
4. Phase 별 TDD cycle
5. `M11_3_verification.md` — M11.2 + M11.3 묶어서 수동 검증
6. PR → main → tag v0.2.2 → Trusted Publishing 자동 publish (5회째)

작업 단위 추정: **~0.7일** (옵션 B + C 결합, 신규 의존성 0, ~15 신규 테스트).
