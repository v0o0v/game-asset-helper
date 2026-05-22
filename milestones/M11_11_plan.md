# M11.11 Plan — 2D grid sheet detection 강화

- **Spec**: [`docs/superpowers/specs/2026-05-23-m11-11-2d-grid-sheet-detection.md`](../docs/superpowers/specs/2026-05-23-m11-11-2d-grid-sheet-detection.md)
- **Branch**: `feat/m11-11-2d-grid-sheet-detection` (v0.2.10 candidate)
- **추정 작업 시간**: 2~4h

## 목표

M11.10 LIVE 에서 발견된 한계:
- `3_direction_npc_characters/Female1-Male3.png` (256×576) — 동일 사이즈 Male4 만 우연 검출, 나머지 미검출
- `warrior_free_asset/Warrior_Sheet-*.png` (414×748) — 명백히 sheet (파일명 명시) 인데 sprite 분류

이 케이스들이 모두 `kind='spritesheet'` 로 promote 되어 chat_spritesheet batch path + animation 라벨 풍부도 정상 진입하도록.

## Phase 분할

### Phase 0 — Investigation (0.5h)

- [ ] Female1.png alpha channel 분포 측정 — column-wise sum 시각화
- [ ] grid_detect 의 alpha_valley_ratio Female1 vs Male4 비교 dump
- [ ] 3 옵션 (alpha 임계 완화 / GCD 2D fallback / 파일명 hint) 중 누적 적용 확정

### Phase 1 — 파일명 keyword 강제 promote (0.5h)

#### Phase 1-A — Red

`tests/test_m11_11_filename_hint.py` 신설:

- [ ] `test_detect_sheet_promotes_filename_with_sheet_keyword` — `Warrior_Sheet-Effect.png` → sheet
- [ ] `test_detect_sheet_promotes_filename_with_strip_keyword` — `Hero_Strip.png` → sheet
- [ ] `test_detect_sheet_extracts_frame_size_from_filename` — `Spike Head Blink (54x52).png` → frame_w=54
- [ ] `test_detect_sheet_no_filename_keyword_no_promote` — `Apple.png` 100×80 → None

→ 4 red

#### Phase 1-B — Green

- [ ] `core/sheet/detect.py` 에 `_filename_hint_detect(image_path, width, height) -> SheetDetection | None` 신설
- [ ] `Sheet` / `Strip` / `Sheets` keyword (case-insensitive, boundary char) → 강제 sheet
- [ ] `(WxH)` regex parse — frame_w / frame_h 명시
- [ ] `detect_sheet` 의 step 3 (M11.10 ratio_fallback) 전에 `_filename_hint_detect` 호출
- [ ] 4 red → green

### Phase 2 — GCD 기반 2D grid fallback (1h)

#### Phase 2-A — Red

`tests/test_m11_11_2d_grid_fallback.py` 신설:

- [ ] `test_detect_sheet_2d_grid_via_gcd_npc` — 256×576 → frame_w=32, frame_h=48
- [ ] `test_detect_sheet_2d_grid_skips_small_total_area` — 100×80 → None
- [ ] `test_detect_sheet_2d_grid_skips_non_integer_gcd` — 100×72 → None

→ 3 red

#### Phase 2-B — Green

- [ ] `_2d_grid_fallback_detect(width, height) -> SheetDetection | None` 신설
- [ ] 조건: area ≥ 10000, GCD ≥ 16, width/GCD ≥ 2 AND height/GCD ≥ 2
- [ ] frame size 후보 list `[8, 16, 24, 32, 48, 64, 96, 128]` 사용
- [ ] `detect_sheet` 의 step 4 (ratio_fallback 실패 후) 에 호출
- [ ] 3 red → green

### Phase 3 — LIVE 검증 (0.5h)

- [ ] Fresh data-dir + M11.10 packs 재 import
- [ ] `scripts/_diag_sheet_missed.py` 실행 — Female1-Male3 / Warrior_Sheet-* 모두 `kind='spritesheet'` 확인
- [ ] false positive 확인 — 단일 sprite (apple, banana) 가 잘못 sheet 안 됨

### Phase 4 — Verification + PR (0.5h)

- [ ] `milestones/M11_11_verification.md` 작성
- [ ] HANDOFF.md 갱신
- [ ] Commit + push + PR draft

## 회귀 기준

main 기준 (M11.10 머지 후): **`1594 passed + 3 skipped + 57 deselected`**.
신규 +7~10 → 1601~1604 예상.

## 의존성

- ✅ M11.10 PR #35 main 머지 완료 (`e986032`)
- ✅ `scripts/_diag_sheet_missed.py` (M11.10 commit `c5a4c8e` 에 포함)
- ✅ M11.10 의 `_ratio_fallback_detect` (1D strip) — M11.11 가 step 4 로 누적

## 비 목표

본 spec 의 §3.3 그대로:
- Aseprite JSON sidecar 다른 path 지원
- grid_detect.py 의 color-edge 임계 미세 조정
- 사용자 manual override UI (sprite ↔ spritesheet 토글)
