# M11.11 — 2D grid sheet detection 강화

- **Spec ID**: `m11-11-2d-grid-sheet-detection-2026-05-23`
- **Trigger**: M11.10 PR #35 LIVE 검증 (142 assets / 7 packs) 에서 같은 팩 안 일부 시트만 sheet 로 promote, 다른 시트는 sprite 로 분류되는 한계 발견
- **Severity**: medium — 분석 / batch path 자체는 정상 동작.  단지 sprite kind 으로 분류된 sheet 들이 sprite analyzer 의 단일 frame label 만 받음 (animation 추정 풍부도 ↓)
- **Branch**: `feat/m11-11-2d-grid-sheet-detection` (v0.2.10 candidate)
- **추정 작업 시간**: 2~4h (red→green + LIVE 검증)

## 1. 배경 (M11.10 LIVE 관측)

대규모 LIVE (142 assets, 7 packs, 2026-05-23) 에서 다음 케이스가 sprite 로 분류됨:

| asset path | size | 실제 layout | M11.10 동작 |
|---|---|---|---|
| `3_direction_npc_characters/Female1.png` | 256×576 | 32×48 frame × 8×12 grid (96 frames) | `kind='sprite'` |
| `3_direction_npc_characters/Female2.png` | 256×576 | 동일 | `kind='sprite'` |
| `3_direction_npc_characters/Male1-3.png` | 256×576 | 동일 | `kind='sprite'` |
| `3_direction_npc_characters/Male4.png` | 256×576 | 동일 | ✅ `kind='spritesheet'` (96 frames) |
| `warrior_free_asset/Warrior_Sheet-Effect.png` | 414×748 | dense character grid | `kind='sprite'` |
| `warrior_free_asset/Warrior_SheetnoEffect.png` | 414×748 | 동일 | `kind='sprite'` |
| `2d_pixel_art_platformer_biome_plains/Sprites.png` | 1280×640 | tileset | ✅ `kind='spritesheet'` (2 frames, 1D fallback) |

핵심:
- **같은 팩 (`3_direction_npc_characters`) 의 동일 사이즈 (256×576) 시트들이 다른 결과** — Male4 만 grid_detect 의 alpha valley 임계 통과, Female1-Male3 미달.
- **파일명 `Sheet` keyword 미활용** — `Warrior_Sheet-Effect.png` 가 명백히 sheet 인데 sprite 분류.
- **2D grid fallback 부재** — M11.10 의 `_ratio_fallback_detect` 는 width/height aspect ratio 정수배수 (≥2) 만 처리.  256×576 의 ratio=0.44 (또는 2.25) 는 비정수.

## 2. Root cause

`src/assetcache/core/sheet/detect.py:27` 의 `detect_sheet` 흐름:

1. JSON 사이드카 (Aseprite atlas)
2. `grid_detect` (alpha valley + color-edge)
3. M11.10 신규 `_ratio_fallback_detect` (1D 정수배수 strip)
4. None

**한계**:
- grid_detect 가 image 의 alpha valley 분포에 민감 — 같은 사이즈 다른 image 에서 다른 결과.
- 1D fallback 은 aspect ratio 가 비정수면 진입 X.
- 파일명 hint 없음.

## 3. 목표 (Acceptance Criteria)

### 3.1 정량 목표

- [ ] AC #1: M11.10 LIVE 환경 재현 시 `3_direction_npc_characters` 의 Female1, Female2, Male1, Male2, Male3 모두 `kind='spritesheet'` + frame_count=96.
- [ ] AC #2: `warrior_free_asset` 의 Warrior_Sheet-Effect / Warrior_SheetnoEffect 모두 `kind='spritesheet'` + frame_count ≥ 1.
- [ ] AC #3: 회귀 — M11.10 의 1D strip fallback 케이스 (Cat-*-Walk 400×50 등) 모두 유지.
- [ ] AC #4: false positive 0 — 단일 sprite 가 우연히 큰 사이즈 (예: 256×256 단일 캐릭터 portrait) 를 sheet 로 잘못 promote 하지 않음.

### 3.2 정성 목표

- [ ] AC #5: 신규 detect_sheet 케이스에 unit test 신설 — 2D GCD grid / 파일명 keyword / false positive 회피 검증.
- [ ] AC #6: 회귀 `pytest -q` PASSED.

### 3.3 비 목표 (Out of Scope)

- Aseprite JSON sidecar 의 다른 path 지원 (현재 동일 stem 만) — 별도 patch
- grid_detect.py 의 색상 분할 (color-edge) 임계 미세 조정 — M11.4 cleanup 으로 충분
- 사용자 manual override UI (라이브러리 페이지에서 sprite ↔ spritesheet 토글) — M12 후보

## 4. 구현 단계

### Phase 0 — Investigation (0.5h)

1. **Female1.png alpha 분포 측정** — `numpy` 로 alpha channel 의 column-wise sum 시각화.  grid_detect 의 valley 임계 미달 정확한 이유 확인.
2. **현재 grid_detect 의 alpha_valley_ratio 결과 dump** — Female1 vs Male4 비교.
3. **결정** — 다음 3 옵션 중 우선순위:
   - 옵션 A: grid_detect alpha 임계 완화 (가장 적은 변경, false positive 위험)
   - 옵션 B: GCD 기반 2D grid fallback (작은 frame size 가정)
   - 옵션 C: 파일명 keyword (`Sheet`/`Strip` 또는 `(WxH)` 표기) hint

권장 — **3 옵션 모두 누적 적용** (각자 다른 케이스 커버, 서로 보완).

### Phase 1 — 파일명 keyword 강제 promote (0.5h)

#### Phase 1-A — Red

`tests/test_m11_11_filename_hint.py` 신설:

1. `test_detect_sheet_promotes_filename_with_sheet_keyword` — `Warrior_Sheet-Effect.png` (414×748) → sheet (default 단일 frame layout 또는 grid).
2. `test_detect_sheet_promotes_filename_with_strip_keyword` — `Hero_Strip.png` → sheet.
3. `test_detect_sheet_extracts_frame_size_from_filename` — `Spike Head Blink (54x52).png` → frame_w=54, frame_h=52, frame_count = (총 width / 54) × (총 height / 52).
4. `test_detect_sheet_no_filename_keyword_no_promote` — `Apple.png` 100×80 (정상 sprite) → None.

#### Phase 1-B — Green

`src/assetcache/core/sheet/detect.py`:
- `_filename_hint_detect(image_path, width, height) -> SheetDetection | None`:
  - `Sheet` / `Strip` / `Sheets` keyword (case-insensitive, "_" / "-" / " " boundary) → 강제 sheet.  layout 추정: width % height == 0 → 1×N grid (M11.10 ratio fallback 와 동일).  실패 시 단일 frame.
  - `(WxH)` regex parse — frame_w / frame_h 명시.  cols=width//W, rows=height//H 정수 분할.
- `detect_sheet` 의 step 3 (M11.10 ratio_fallback) 전에 `_filename_hint_detect` 호출.

### Phase 2 — GCD 기반 2D grid fallback (1h)

#### Phase 2-A — Red

`tests/test_m11_11_2d_grid_fallback.py` 신설:

1. `test_detect_sheet_2d_grid_via_gcd_npc` — 256×576 PNG (alpha uniform opaque) → frame_w=32, frame_h=48 (GCD = 16, 일반 sprite size 후보 중 선택), cols=8, rows=12.  단 후보 frame size 결정 휴리스틱은 implementation 에 위임.
2. `test_detect_sheet_2d_grid_skips_small_total_area` — 100×80 작은 정사각형 → None (false positive 차단).
3. `test_detect_sheet_2d_grid_skips_non_integer_gcd` — 100×72 (GCD=4 너무 작음) → None.

#### Phase 2-B — Green

`_2d_grid_fallback_detect(width, height) -> SheetDetection | None`:

- 조건: width × height ≥ 임계 (예: 10000), GCD(width, height) ≥ 16, width / GCD ≥ 2 AND height / GCD ≥ 2.
- 일반 sprite frame size 후보 list: `[8, 16, 24, 32, 48, 64, 96, 128]` (DESIGN.md §3 참고).  width 와 height 가 둘 다 같은 후보 으로 나뉘면 그 frame size 채택.  여러 후보면 가장 큰 것.
- 또는 단순화: GCD 자체를 frame size 로 사용 (단 ≥ 16 + 256/GCD ≥ 4 같은 조건).

`detect_sheet` 의 step 4 (ratio_fallback 실패 후) 에 `_2d_grid_fallback_detect` 호출.

### Phase 3 — LIVE 검증 (0.5h)

Fresh `--data-dir` + M11.10 의 7 packs 재 import + 진단:

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts\_diag_sheet_missed.py
```

기대값:
- "sprite kind 인데 ratio >= 2.5" 결과 더 줄어듦 (2D GCD 잡힌 케이스)
- Female1-Male3 모두 `kind='spritesheet'` + frame_count ≥ 96
- Warrior_Sheet-* 모두 `kind='spritesheet'`

### Phase 4 — Verification + PR (0.5h)

- `milestones/M11_11_verification.md` 작성
- HANDOFF.md 갱신
- Commit + push + PR draft (`feat/m11-11-2d-grid-sheet-detection`)
- v0.2.10 candidate (publish 보류)

## 5. 테스트 전략

### 5.1 자동 (pytest)

- `tests/test_m11_11_filename_hint.py` — 4 케이스 (Phase 1)
- `tests/test_m11_11_2d_grid_fallback.py` — 3+ 케이스 (Phase 2)
- 회귀: M11.10 의 1D strip fallback test 들 (5 케이스) 모두 PASS

### 5.2 LIVE

- M11.10 의 packs 재 import + sheet detect 결과 비교
- false positive 확인 — 단일 sprite (apple, banana 등) 가 sheet 로 안 promote 되는지

### 5.3 회귀 baseline

main 기준: **`1594 passed + 3 skipped + 57 deselected`** (M11.10 머지 직후).
신규 +7~10 → 1601~1604 예상.

## 6. 위험 / 의존성

- **GCD 기반 2D grid 의 false positive 위험**: 단일 sprite 가 우연히 GCD ≥ 16 + 큰 area + 정수 grid 조건 만족 시 잘못 promote.  대응: frame size 후보 list 휴리스틱 + 임계 area 조건.
- **파일명 keyword 의 i18n 한계**: `Sheet` 영문만 지원.  한글 `시트` 등은 별도.  M11.11 범위는 영문 keyword 만.
- **(WxH) regex 의 false positive**: 우연히 파일명에 (320x240) 같은 게 frame size 가 아닌 resolution 일 수도.  대응: 합리적 frame size 범위 (8~256) 만 채택.

## 7. References

- M11.10 PR [#35](https://github.com/v0o0v/assetcache-mcp/pull/35) — main `e986032`
- M11.10 verification §6.2 / §7 — 본 spec 의 발생 원인
- `src/assetcache/core/sheet/detect.py` — `detect_sheet` 본체 (M11.10 ratio fallback 후속)
- `src/assetcache/core/sheet/grid_detect.py` — alpha valley + color-edge fallback
- `scripts/_diag_sheet_missed.py` — LIVE 진단 helper
