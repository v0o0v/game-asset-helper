# M11.5 검증 — LIVE validation + tuning patches (v0.2.4 candidate)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-21-m11-5-live-validation-and-tuning.md`](../docs/superpowers/specs/2026-05-21-m11-5-live-validation-and-tuning.md)
- 상위 plan: [`M11_5_plan.md`](./M11_5_plan.md)
- 전제: [PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21) M11.4 main 머지 (`7794d48`) + (선택) v0.2.3 PyPI publish
- 본 문서는 **Phase 1 LIVE 검증 (gate) → Phase 2/4 분기 → 조건부 Phase 3/5/6 → Phase 7 wrap-up** 흐름의 결과를 누적한다.

## 1. 자동 baseline

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Expected (Phase 1 진입 시점): **1592 passed + 1 skipped + 59 deselected** (M11.4 main `7794d48` baseline 그대로).

상태: ✅ 2026-05-22 재현 — `1592 passed, 1 skipped, 59 deselected in 81.94s`.  Phase 진행에 따라 신규 테스트 합산.

## 2. LIVE 검증 셋업 (Phase 1 gate)

### 2.1 합성 자산 생성

`scripts/make_complex_sheets.py` 가 M11.3 LIVE v2 의 6 자산을 재현한다 (Aseprite/TexturePacker 외부 라이선스 자산 없이도 검증 가능).

```powershell
$libDir = "$env:TEMP\m11_5_verify_data\library\m113_complex"
```

```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_5_verify_data" -ErrorAction SilentlyContinue
```

```powershell
New-Item -ItemType Directory -Path $libDir -Force | Out-Null
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py $libDir
```

→ 8 파일 생성 (6 PNG + 2 Aseprite JSON sidecar).

### 2.2 detect_sheet smoke 결과 (LLM 호출 전)

`scripts/make_complex_sheets.py` 검증 시 detect_sheet 결과:

| 자산 | source | frames | frame_w/h | tags |
|---|---|---:|---|---|
| hero_warrior | json | 16 | 64/64 | idle/walk/attack/hurt |
| mage_purple | json | 12 | 48/48 | cast/idle/walk |
| knight_gold | grid | 8 | 32/32 (stride) | — |
| monster_red | grid | 4 | 48/48 (stride) | — |
| **elemental_cyan** | **grid** | **6** | **64/64** | — ← **M11.4 D-1 color-edge fallback 작동 확인** |
| crown_icon | None | — | — | (single sprite) |

→ M11.3 LIVE v2 에서 sprite 로 떨어졌던 elemental_cyan 이 detect 단계에서 spritesheet 로 promote 됨. Phase 2 (#2 AXIS_SPAN_RATIO 튜닝) 의 트리거 여부는 batch chat_image 분류 단계까지 가야 최종 확정.

### 2.3 tray 부팅 + LIVE Gemini 배치

사용자가 직접 실행 (GEMINI_API_KEY 보유):

```powershell
$env:GEMINI_API_KEY = "AIza..."
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m assetcache --tray --data-dir "$env:TEMP\m11_5_verify_data"
```

`/settings` 에서:
- `chains.chat_image = ["gemini"]`, `chains.chat_spritesheet = ["gemini"]`
- `batch.toggle = "forced_on"`

자동 sweep 종료 후 SQL 측정:

```powershell
sqlite3 "$env:TEMP\m11_5_verify_data\metadata.db" "SELECT a.name, a.kind, m.frame_w, m.frame_h, m.frame_count FROM assets a LEFT JOIN sprite_meta m ON m.asset_id=a.id WHERE a.kind IN ('sprite','spritesheet') ORDER BY a.id"
```

```powershell
sqlite3 "$env:TEMP\m11_5_verify_data\metadata.db" "SELECT a.name, l.axis, l.label FROM asset_labels l JOIN assets a ON a.id=l.asset_id WHERE l.axis IN ('category','palette','mood','animation') ORDER BY a.name, l.axis"
```

## 3. LIVE 결과 표 (Phase 1 gate) — ✅ 2026-05-22

driver: `scripts/drive_live_batch.py` (Qt tray 우회, BatchManager+BatchPoller 직접 구동).  Gemini batch inline destination 사용.

batch_jobs:

| job_id | modality | state | asset_count | success | failure |
|---:|---|---|---:|---:|---:|
| 1 | chat_image | succeeded | 1 | 1 | 0 |
| 2 | chat_spritesheet | succeeded | 5 | 5 | 0 |

→ chat_image 가 6 자산 fetch → classify_image_assets 가 5 자산을 spritesheet kind 로 promote (elemental_cyan 포함, D-1 작동 LIVE 확인) → crown_icon (sprite) 만 chat_image batch 진입.  chat_spritesheet 가 promote 된 5 자산 batch.  payload validation ValueError 0건.

| # | 자산 | M11.4 기대 | LIVE 결과 | 평가 |
|---:|---|---|---|---|
| 1 | elemental_cyan | kind=spritesheet, 6 frame | **kind=spritesheet, 64×64×6** ✅ | **D-1 color-edge LIVE 통과** |
| 2 | crown_icon | category ∈ {inventory_item, item, icon} | **category=inventory_item** ✅ | **LLM #3 patch LIVE 통과** |
| 3 | hero_warrior | category=character, 4 anim 라벨 | **character + idle/walk/attack/hurt + 'other'** ✅ | regression 0 |
| 4 | mage_purple | category=character, 3 anim 라벨 | **character + cast/idle/walk + 'other'** ✅ | regression 0 |
| 5 | knight_gold | kind=spritesheet, frame_w=32 (D-2 stride) | **kind=spritesheet, 32×32×8** ✅ | regression 0 (M11.3 "17/28" 은 D-2 적용 전 — 32 가 정상) |
| 6 | monster_red | kind=spritesheet, 4 frame | **kind=spritesheet, 48×48×4 + animation=idle (Gemma 추측)** ✅ | M11.2 chat_spritesheet modality 의 가치 LIVE 확인 |
| 7 | palette 응답 분포 | hex 0건 + tone group 안 | **crown_icon palette=warm, high_contrast — hex 0건** ✅ | tone group enum 내 응답 |

### 3.1 별도 발견 (M11.5 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| elemental_cyan category=character | LLM 분류 한계 — 합성 색 cycle orb 자산 시각이 character 와 구분 안 됨.  실 게임 자산은 색만 cycle 하는 시트가 드물어 영향 낮음 | M11.5 범위 밖 |
| 시트 자산 (hero/mage/knight/monster) palette 라벨 부재 | BATCH_SPRITESHEET_PROMPT 가 palette 를 명시 안 함 — chat_image 만 palette 응답 | 별도 patch 후보 (BATCH_SPRITESHEET_PROMPT 강화) |
| animation='other' 가 여러 자산에 등록 | prompt 가 'other' fallback 을 받는 영향 — 의미 X 라벨이 합산 | LabelRegistry filter 또는 prompt 'other' 금지 (별도 patch) |

## 4. Phase 2 / 4 분기 결정 매트릭스 — ✅ 2026-05-22

| trigger | LIVE 결과 | 결정 |
|---|---|---|
| #1 elemental_cyan kind | **spritesheet ✓** | **Phase 3 SKIP** (D-1 LIVE 통과) |
| #2 crown_icon category | **inventory_item ✓** | **M12 모델 업그레이드 trigger 안 함** + Phase 5 strict 진입 가능 |
| #7 palette hex | **0건 ✓** | Phase 6 hex 강화 불필요 |
| #7 palette tone group narrow | 응답 분포 적음 (crown_icon 만 palette 라벨) | **Phase 6 SKIP** — narrow 결정에 필요한 분포 부족, 시드 변경 무의미 |
| #3~#6 regression | 변경 0 ✓ | regression 0 |

→ **M11.5 patch 범위**: Phase 5 (llm_integration acceptable set strict 화) 만.

## 5. Phase 3 — AXIS_SPAN_RATIO 튜닝 (조건부, TBD)

LIVE 결과 #1 = sprite 일 때만 진입.  현재 가설:

* `_AXIS_SPAN_RATIO=0.8` ratio 조정 (0.7 / 0.75 / 0.85 sweep)
* 또는 boundary 후보 row 별 diff 의 표준편차 임계 도입 (object 만 변화 → std 高, 균일 색 경계 → std 低)

신규 테스트 ~3 (sweep 케이스 + std 검증).

## 6. Phase 5 — llm_integration acceptable set strict — ✅ 2026-05-22

`tests/test_llm_backend_gemini_inventory_item_integration.py`:
* crown: `{inventory_item, item, icon, ui_icon, other}` → **`{inventory_item, item}`** (icon/ui_icon/other 제거)
* ui_button: `{ui_icon, ui, icon, inventory_item, other}` → **`{ui_icon, ui}`** (icon/inventory_item/other 제거)

LIVE 옵트인 결과 (gemini-2.5-flash, 2026-05-22):

```
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_classified_as_inventory_item_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_classified_as_ui_icon_not_character PASSED

2 passed in 10.12s
```

→ Gemini 가 strict set 안에서 응답 (crown=inventory_item 또는 item, ui_button=ui_icon 또는 ui).  M11.4 prompt 가이드의 효과가 LIVE 1회 통과 확인.

## 7. Phase 6 — palette tone-group narrow (조건부, TBD)

LIVE 응답 분포 본 후 결정:

* **strict 채택 조건**: `vibrant`/`saturated`/`muted`/`desaturated`/`dark`/`light`/`earthy` 중 prompt 외 토큰 빈도 < 5% (Gemini 가 prompt enum 만 사용)
* **strict 채택 시 작업**: 시드 7 토큰 `is_enabled=0` 마이그 (delete 안 함, 기존 라벨 보호), `label_catalog_signature` 변경 확인
* **prompt 강화** (별도): `BATCH_IMAGE_PROMPT` 에 hex 예시 늘리기 + tone group 가이드 강화

신규 테스트 ~3.

## 8. 알려진 한계 (M11.5 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| Gemini 모델 업그레이드 (3.1-flash-lite → 3.1-flash) | M12 별도 spec | LIVE 결과 #2 = character 일 때 trigger |
| BATCH_SPRITESHEET_PROMPT category 강제 완화 (multi-frame inventory) | M12+ 별도 마일스톤 | 회전 coin 등 요구 시점 |
| `make_complex_sheets.py` 자산이 합성 픽셀 아트 → 실 게임 자산 분포와 차이 가능 | M11.5 범위 밖 | 사용자 라이브러리로 별도 검증 권장 |

## 9. Phase 7 — 회귀 + verification + PR (검증 완료 후)

1. 전체 회귀 통과:
   ```powershell
   & "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
   ```
   → `1592 + (Phase 별 신규)` passed 확인.
2. PR → main 머지.
3. `pyproject.toml` + `src/assetcache/__init__.py` 0.2.2 → 0.2.4 bump 커밋.
   (v0.2.3 publish 보류했으므로 0.2.3 결번 — v0.2.1 와 같은 패턴, [HISTORY](./HISTORY.md) 의 "Trusted Publishing 패턴" 참조.)
4. tag + push:
   ```powershell
   git tag v0.2.4
   ```
   ```powershell
   git push origin v0.2.4
   ```
5. Trusted Publishing OIDC workflow 자동 트리거 — 7회째 자동 publish (평균 30초).
6. [PyPI v0.2.4 publish 확인](https://pypi.org/project/assetcache-mcp/) + GitHub release 자동 생성 확인.

## 10. 현재 진행 상태 (2026-05-22)

| Phase | 상태 |
|---|---|
| 1 — LIVE 검증 (gate) | ✅ chat_image 1/1 + chat_spritesheet 5/5 success (elemental_cyan D-1 + crown_icon LLM #3 LIVE 통과) |
| 2 — 분기 결정 | ✅ Phase 3 SKIP / Phase 5 진입 / Phase 6 SKIP / M12 trigger 안 함 |
| 3 — AXIS_SPAN_RATIO 튜닝 | ⏭ SKIP (elemental_cyan promote 확인) |
| 5 — llm_integration acceptable set strict | 🟡 **진입** — crown `{inventory_item, item}`, ui_button `{ui_icon, ui}` strict 화 |
| 6 — palette narrow | ⏭ SKIP (LIVE 분포 부족) |
| 7 — PR + tag | ⏸ Phase 5 종료 후 |
