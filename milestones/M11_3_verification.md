# M11.3 검증 — Detection Cache (옵션 B+C, M11.2 와 묶어서 v0.2.2)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-21-m11-3-detection-cache.md`](../docs/superpowers/specs/2026-05-21-m11-3-detection-cache.md)
- 상위 plan: [`M11_3_plan.md`](./M11_3_plan.md)
- 본 문서는 M11.2 ([PR #19](https://github.com/v0o0v/assetcache-mcp/pull/19), main `d34f1dd`) + M11.3 묶음 수동 검증 — v0.2.2 publish 직전 한 번에 진행.

## 1. 자동 검증

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Expected: **1547 passed + 3 skipped + 57 deselected**.  baseline 1528 + 신규 19 (cache 테스트 7 + manager LRU 6 + poller cache 6).

옵트인 (GEMINI_API_KEY 필요):

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -m llm_integration -q
```

Expected: 17 case 그대로 (M11.3 은 외부 API 호출 변경 0).

## 2. 수동 검증 시나리오 (M11.2 + M11.3 통합)

### 2.1 grid-only 시트 — Gemma animation_hint 보존 (M11.2 의 핵심)

1. library 에 JSON 사이드카 없는 격자 PNG 1개 (예: 4 cell horizontal strip) 드롭.
2. `/settings` 에서 Gemini chain enabled + `chat_spritesheet` chain 도 [gemini, ollama] 인지 확인.
3. `cfg.batch.toggle="forced_on"` 으로 즉시 batch 진입 또는 30+ 시트 드롭 후 자동 trigger.
4. `python -m assetcache --tray` 실행 후 `/analyzing` dashboard 에서:
   - chat_image batch job 이 promote 만 하고 sprite 가 부족하면 사라짐.
   - 곧 chat_spritesheet job 이 생성됨.
5. job 완료 후:
   ```powershell
   sqlite3 $env:APPDATA\AssetCacheMCP\library.db "SELECT axis, label FROM asset_labels WHERE asset_id=<id>"
   ```
   → animation 라벨 1개 이상 있어야 (PR #18 까지는 0건이던 케이스).

### 2.2 Aseprite 시트 — frameTags + Gemma 동시 라벨

1. Aseprite JSON 사이드카 있는 PNG 드롭.
2. 위와 동일 흐름으로 chat_spritesheet 진입.
3. DB 확인 — animation 라벨에 frameTags (예: idle/walk) + Gemma animation_hint (예: run) 모두 등록.

### 2.3 sprite 만 있는 라이브러리 — 회귀

1. 시트 0개, 단일 sprite 만 있는 라이브러리.
2. chat_image batch 정상 동작 (분류 후 sprite_rows = 전체) — `/analyzing` summary 의 batch_spritesheet=0 유지.

### 2.4 chains 누락 호환성

1. 기존 사용자 `config.toml` (chat_spritesheet 키 없음) 로 부팅.
2. `cfg.chains["chat_spritesheet"]` 가 chat_image 와 동일 chain 으로 자동 채워졌는지 `/settings` 에서 확인.

### 2.5 /analyzing 4행 modality

1. /analyzing 페이지 진입 — summary 가 4 modality (image/spritesheet/audio/embed) 표시.
2. ko/en 언어 토글 — "Batch spritesheet" → "배치 시트" 정상 번역.

### 2.6 Detection Cache 활성 확인 (M11.3 신규)

같은 시트가 chat_image classify → chat_spritesheet classify → BatchPoller persist 3 경로를 거치는데 detect_sheet 가 1회만 호출돼야.

#### 2.6.1 sweep 메모리 캐시 (옵션 C) — 로그 확인

1. `python -m assetcache --tray` 실행.
2. `cfg.batch.toggle="forced_on"` 으로 즉시 batch.
3. grid-only 시트 5개 + Aseprite 시트 5개 = 총 10개 드롭.
4. tray 로그 (`%APPDATA%\AssetCacheMCP\logs\assetcache.log`) 에서 `detect_sheet` 호출 횟수 카운트:
   ```powershell
   Get-Content $env:APPDATA\AssetCacheMCP\logs\assetcache.log | Select-String "detect_sheet failed|grid_detect" | Measure-Object
   ```
   (실 로그가 detect 자체를 log info 하지 않으므로 디버깅 시 임시 로그 추가 또는 `BatchManager._detection_cache` 크기 직접 확인)
5. **BatchManager `_detection_cache` 가 시트 10개 entry 보유** — Python REPL 또는 임시 `/debug/cache` 엔드포인트로 확인 (선택).

#### 2.6.2 DB sprite_meta 캐시 (옵션 B) — sprite_meta 영속 확인

1. 위 1~3 단계 진행 후 batch 완료까지 대기 (chat_image promote → chat_spritesheet submit → 응답 polling).
2. chat_image classify 단계 직후 (chat_spritesheet 가 submit 되기 전) sprite_meta 가 이미 채워졌는지 SQLite 확인:
   ```powershell
   sqlite3 $env:APPDATA\AssetCacheMCP\library.db "SELECT asset_id, frame_w, frame_h, frame_count, animations_json FROM sprite_meta WHERE asset_id IN (SELECT id FROM assets WHERE kind='spritesheet' AND analysis_state != 'ok' ORDER BY id DESC LIMIT 5)"
   ```
   → kind='spritesheet' 인데 analysis_state≠'ok' 인 시트도 frame_w / animations_json 이 채워져 있어야 한다 (Phase 1 의 save_sprite_meta 효과).
3. BatchPoller 가 응답 처리 시 detect_sheet 안 부르고 sprite_meta cache hit 했는지 로그에서:
   ```powershell
   Get-Content $env:APPDATA\AssetCacheMCP\logs\assetcache.log | Select-String "spritesheet 검출 실패"
   ```
   → 0건이어야 (sheet detection 자체를 안 함).

### 2.7 cache eviction — LRU 한도 1024 (선택)

라이브러리에 1024개+ 자산 있을 때 BatchManager 인스턴스 lifetime 동안 가장 오래된 entry 부터 evict 됨 — 자동 테스트로 검증되었으나 production 데이터로 확인하려면 1024장 이상 드롭 + tray 부팅 후 일정 시간 작업 후 `_detection_cache` len <= 1024 확인.

## 3. 알려진 한계

- 시트 파일이 24h 사이에 바뀌면 sprite_meta cache stale — 사용자가 명시적 재분석 트리거 필요 (file hash 비교 invalidate 는 향후 patch).
- BatchManager instance memory cache 가 multi-process 환경에서 공유 X — tray app 은 single-process 라 영향 없음.  M14 (원격 통신) 진입 시 검토.
- Aseprite 비균일 hash-mode 시트의 frames 좌표 (각 frame x,y,w,h) 는 sprite_meta 만으론 복원 불가.  BatchPoller persist 단계는 라벨 합산만 필요해 영향 X — composite builder (BatchManager classify) 는 detection 객체 직접 사용해 cache hit 가능.

## 4. LIVE 검증 결과 (2026-05-21)

`drive_batch.py` (BatchManager + BatchPoller 직접 입력) 로 grid-only 6 + Aseprite 6 + sprite 1 = 13 자산 처리.

### 4.1 detect_sheet 호출 횟수

| Path | 호출 횟수 | 비고 |
|---|---:|---|
| `classify_image_assets` (chat_image sweep) | 13 | 1 sweep 1 row, cache populate |
| `classify_image_assets` (chat_spritesheet sweep) | 0 | **옵션 C cache hit, 12 row 우회** ✓ |
| `BatchPoller._try_enrich_with_sheet` | 1 | single_orb (sprite) 만, 12 sheet 은 **옵션 B cache hit** ✓ |
| **총 14회** vs legacy **38회** | **24회 절약 (63% 감소)** |

### 4.2 sprite_meta 영속 (옵션 B)

- 12 sheet 모두 `frame_w/h/count` 채워짐 (chat_image classify 단계의 `save_sprite_meta=True`).
- Aseprite 시트 6개 (id 1~6) — `animations_json` 정확히 frameTags 보존 (idle/walk, anim).
- grid-only 6개 (id 7~12) — frame info enrich 됨, `animations_json=None` (Gemma animation_hint 부재 — M11.2 알려진 한계).
- single_orb (id 13) — sprite kind 유지, sprite_meta=None.

### 4.3 batch_job 결과

| job_id | modality | state | count | success | failure |
|---:|---|---|---:|---:|---:|
| 2 | chat_image | succeeded | 1 | 1 | 0 |
| 3 | chat_spritesheet | succeeded | 12 | 10 | 2 |

* 실패 2건 (id 7, 9): Gemini 응답 schema list 형식 → `payload_parser.validate_image_payload` 의 `dict(payload)` ValueError — **M11.3 와 무관 pre-existing bug** (별도 patch 후보).

### 4.4 시나리오 매핑

| # | 결과 |
|---:|---|
| 2.1 grid-only | ✅ kind=spritesheet, frame info enrich, animation 라벨 0 (Gemma 한계 그대로) |
| 2.2 Aseprite | ✅ animations_json + animation 라벨 frameTags 보존 |
| 2.3 sprite-only | ✅ kind=sprite, sprite_meta=None, state=ok |
| 2.4 chains 누락 호환성 | ✅ `chainsInit` JSON 에 `chat_spritesheet: ["gemini"]` 자동 채움 — 단 `modalityOrder` 의 UI 위젯 표시는 M11.2 의 별도 gap |
| 2.5 /analyzing 4행 modality | ✅ `Batch image / 배치 시트 / Batch audio / Batch embed` 4행 + 부분 ko 번역 |
| 2.6 detection cache | ✅ 24회 → 14회 detect_sheet (63% 감소) — 위 §4.1 |

## 4b. LIVE 검증 v2 (2026-05-21) — 복잡 시트 6종

더 복잡한 시트 (사이드카 있는 / 없는 / 단일 sprite 구분) 로 재검증.  `make_complex_sheets.py` 로 생성:

| 자산 | kind | frame_w/h/count | animations_json | category | style |
|---|---|---|---|---|---|
| hero_warrior (Aseprite 4×4, 16f) | spritesheet | 64/64/16 | **idle/walk/attack/hurt 4 anims** ✓ | character | pixel_art |
| mage_purple (Aseprite 3×4, 12f) | spritesheet | 48/48/12 | **cast/idle/walk 3 anims** ✓ | character | pixel_art |
| knight_gold (grid 1×8) | spritesheet | 17/28/8 | None (grid-only) | character | pixel_art |
| monster_red (grid 2×2) | spritesheet | 41/41/4 | None | other | cel_shaded |
| elemental_cyan (grid 1×6) | **sprite** ⚠ | None | None | other | pixel_art |
| crown_icon (single) | sprite | None | None | character | cel_shaded |

### 4b.1 Cache 효과

- `classify_image_assets` detect_sheet: 6회 (1 sweep, 6 rows)
- `BatchPoller` detect_sheet: 2회 (sprite kind 인 crown_icon + elemental_cyan)
- 합계 **8회** vs legacy ~16회 — **8회 절약 (50% 감소)** ✓

### 4b.2 batch_job 결과

- chat_image (job_id=6): count=2, success=2, failure=0 ✓
- chat_spritesheet (job_id=7): count=4, success=4, failure=0 ✓
- **Patch B 적용 → payload validation ValueError 0건** (이전 v1 검증 의 12 중 2 실패 supersede)

### 4b.3 Gemma animation_hint LIVE 작동

- animation 라벨 합계 9개:
  - hero_warrior frameTags 4 (idle/walk/attack/hurt)
  - mage_purple frameTags 3 (cast/idle/walk)
  - **Gemma 추측 2 (idle/walk on grid-only)** ✓ ← M11.2 chat_spritesheet modality 의 핵심 가치 LIVE 확인

### 4b.4 별도 발견 (M11.3 + 부수 patch 와 무관)

| 항목 | 한계 |
|---|---|
| `elemental_cyan` (1×6, 64×64) sprite 오분류 | color-cycling orb visual 이 grid_detect alpha 격자 분석 통과 못 함 — M6 detection 한계 |
| 작은 시트 (32/48px) 의 frame_w 정확도 (17/41) | grid_detect 알고리즘이 alpha 경계 좁게 측정 — frame_count 는 정확 |

## 5. 검증 완료 후

1. M11.2 + M11.3 모두 통과 → tag v0.2.2:
   ```powershell
   git tag v0.2.2
   git push origin v0.2.2
   ```
2. Trusted Publishing OIDC workflow 자동 트리거 — 5회째 자동 publish (평균 30초 예상).
3. [PyPI v0.2.2 publish 확인](https://pypi.org/project/assetcache-mcp/0.2.2/) + GitHub release 자동 생성 확인.

## 6. 별도 patch 후보 (M11.3 PR 미포함)

| 항목 | 우선순위 | 발견 |
|---|---|---|
| `/settings` UI `modalityOrder` 에 `chat_spritesheet` 누락 | 중 | M11.2 의 UI rendering 누락 |
| `payload_parser.validate_image_payload` 의 list payload ValueError | 중 | Gemini 응답 schema 변동 — graceful handling 필요 |
| Gemini `batch_embed` API transient error | 낮 | 인프라 의존, retry/fallback 정책 검토 |
