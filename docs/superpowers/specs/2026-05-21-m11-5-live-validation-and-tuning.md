# 2026-05-21 — M11.5 Design Spec: LIVE validation + tuning patches (v0.2.4 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md)
- 전제: [PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21) M11.4 main 머지 (`7794d48`) + v0.2.3 PyPI publish 단계 보류 가능
- 다음: `milestones/M11_5_plan.md` (starter)
- Version 후보: **v0.2.4 patch** (M11.4 의 LIVE 검증 결과로 trigger)

## 1. 한 줄 요약

M11.4 ([PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21)) 의 `milestones/M11_4_verification.md` §4 + §6 가 표시한 **6 한계** 를 LIVE 검증 결과 기반으로 fix.  주로 휴리스틱 임계값 튜닝 + 시드 narrowing + prompt 완화 + 검증 strict 화.

## 2. 결정 매트릭스

| # | 항목 | 작업량 | 효과 범위 | 마이그 | 채택 우선순위 |
|---|---|---:|---|---|---|
| 1 | **LIVE 검증** — m113_complex 6 자산 + 사이드카 시트로 D-1 / LLM #3 결과 측정 | ~수시간 | M11.4 측정 → 후속 분기 결정 | 0 | ✅ 1순위 (gate) |
| 2 | **AXIS_SPAN_RATIO 휴리스틱 튜닝** (현재 0.8) — false-positive/negative 발견 시 ratio 조정 또는 std-기반 강도 검증 | ~0.5일 | grid_detect color-edge 정확도 | 0 | △ #1 결과 후 |
| 3 | **palette tone-group narrow** — 시드에서 `vibrant`/`saturated`/`muted`/`desaturated`/`dark`/`light`/`earthy` 제외 | ~0.5일 | LLM 응답 분포 정리 | 기존 데이터 보호 필요 | △ #1 결과 후 (Gemini 응답 분포 봐서 결정) |
| 4 | **llm_integration acceptable set strict 화** — `inventory_item` 위주, `'other'` 제거 | ~0.2일 | prompt 효과 측정 정확도 | 0 | △ #1 결과 후 |
| 5 | **`BATCH_SPRITESHEET_PROMPT` `category='character'` 강제 완화** — multi-frame inventory (회전 coin 등) 지원 | ~1일 | spritesheet 분류 표현력 | 별도 마일스톤 | ❌ M12 또는 별도 spec |
| 6 | **Gemini 모델 업그레이드** (3.1-flash-lite → 3.1-flash 또는 3.5-flash) — `crown_icon` 류 정확도 | ~0.5일 | LLM 분류 정확도 (비용 ↑) | config 변경 | ❌ M12 (`2026-05-21-m12-...` spec) |

**채택**: M11.5 = #1 + (#2 ∪ #3 ∪ #4) (LIVE 결과 기반 가지치기).  M12 후보로 #5, #6 분리.

## 3. Architecture — #1 LIVE 검증 (gate)

### 3.1 셋업

`milestones/M11_4_verification.md` §3 의 fresh `--data-dir` 패턴 그대로 — m113_complex 6 자산 (elemental_cyan / crown_icon / hero_warrior / mage_purple / knight_gold / monster_red) + (선택) UI 버튼 시트 1~2 추가.

### 3.2 측정 지표 (SQL)

```sql
SELECT a.name, a.kind, m.frame_w, m.frame_h, m.frame_count
FROM assets a LEFT JOIN sprite_meta m ON m.asset_id=a.id
WHERE a.kind IN ('sprite','spritesheet') ORDER BY a.id;
```

```sql
SELECT a.name, l.axis, l.label
FROM asset_labels l JOIN assets a ON a.id=l.asset_id
WHERE l.axis IN ('category','palette','mood','animation')
ORDER BY a.name, l.axis;
```

### 3.3 기대 vs 실제 표

| # | 자산 | M11.4 기대 | LIVE 결과 | 분기 |
|---:|---|---|---|---|
| 1 | elemental_cyan | kind=spritesheet | TBD | sprite 면 → #2 튜닝, spritesheet 면 → D-1 OK |
| 2 | crown_icon | category != character | TBD | character 면 → #6 모델 업그레이드 trigger |
| 3 | hero_warrior | 변경 없음 | TBD | regression 0 여부 |
| 4 | mage_purple | 변경 없음 | TBD | 동일 |
| 5 | knight_gold | 변경 없음 | TBD | 동일 |
| 6 | monster_red | 변경 없음 | TBD | 동일 |
| 7 | palette 결과 | hex 응답 0 | TBD | hex 가 있으면 prompt 강화 (#3) |

## 4. Architecture — #2 AXIS_SPAN_RATIO 튜닝 (조건부)

### 4.1 현재 알고리즘

`grid_detect.py:_uniform_from_edges` — `active_counts >= perpendicular_size * 0.8` 만족하는 gap 만 frame 경계 후보로.  내부 객체 (orb) 의 가장자리는 axis 의 80% 미만 spanning 이라 자동 거부.

### 4.2 발견 가능 한계

* **false-positive**: frame 내부 큰 object 가 axis 의 80%+ 를 덮으면 경계로 오인 → spritesheet 가 아닌데 spritesheet 로 promote.  현실 자산에선 드물지만 가능.
* **false-negative**: 진짜 경계가 anti-aliasing 으로 axis 의 80% 미만 spanning → 검출 실패.

### 4.3 후보 fix

* **ratio 조정** — 0.7 또는 0.9 로 변경 (보수적 vs 공격적)
* **std-기반 강도 검증** — boundary 후보의 row-별 diff 표준편차가 낮을 때 (균일한 색 변화) 만 채택.  내부 object 는 std 가 높음 (orb 부분만 변화)

LIVE 검증 결과 보고 결정.

## 5. Architecture — #3 palette tone-group narrow

### 5.1 현재 시드

palette: 13 토큰 (warm, cool, neutral, monochrome, vibrant, saturated, muted, desaturated, dark, light, pastel, earthy, high_contrast).

M11.4 prompt 는 `[warm, cool, monochrome, high_contrast, pastel, neutral]` 만 enum 으로 명시 — 나머지 (`vibrant`/`saturated`/`muted`/`desaturated`/`dark`/`light`/`earthy`) 는 시드에 있지만 prompt 가 권장 안 함.

### 5.2 narrow 후보

* **strict**: 시드에서 prompt 외 토큰 제거 → 사용자 라벨 마이그 (기존 `vibrant` 라벨 가진 자산 → `warm` 또는 `neutral` 로 변환)
* **soft**: 시드 그대로, prompt 만 강화 — 사용자가 GUI 에서 명시적으로 추가한 라벨은 유지

LIVE 응답 분포 보고 결정 — `vibrant` 가 0건이면 strict.

### 5.3 마이그 영향 (strict 채택 시)

* `labels` 테이블에서 disable 처리 (delete 안 함 — 사용자 데이터 보호)
* `asset_labels` 의 disabled palette 라벨은 그대로 두되 검색 결과에서 제외 (LabelRegistry.list_labels enabled_only 기본)
* `label_catalog_signature` 변경 → MCP 클라이언트 cache invalidate

## 6. Architecture — #4 llm_integration acceptable set strict

### 6.1 현재

`tests/test_llm_backend_gemini_inventory_item_integration.py` 의 acceptable set:
* crown: `{inventory_item, item, icon, ui_icon, other}`
* ui_button: `{ui_icon, ui, icon, inventory_item, other}`

`other` 포함이 prompt 효과 측정 정확도 약함.

### 6.2 strict

* crown: `{inventory_item, item}` (icon/ui_icon 도 제외 — character 와 명확히 구분되는 카테고리만)
* ui_button: `{ui_icon, ui}`

LIVE 1회 통과 후 strict 화.

## 7. Module breakdown

### 7.1 신규 / 변경 파일

| 파일 | 변경 | 조건 |
|---|---|---|
| `milestones/M11_5_verification.md` | LIVE 측정 결과 + 분기 결정 기록 | 항상 |
| `src/assetcache/core/sheet/grid_detect.py` | `_AXIS_SPAN_RATIO` 조정 또는 `_uniform_from_edges` 에 std-검증 추가 | #2 trigger 시 |
| `src/assetcache/core/labels.py` | palette 시드 narrow + 마이그 | #3 strict 채택 시 |
| `src/assetcache/core/analyzer/messages.py` | BATCH_IMAGE_PROMPT 추가 강화 (hex 명시 + 예시 추가) | #3 trigger 시 |
| `tests/test_sheet_grid_detect_color_edge.py` | AXIS_SPAN_RATIO 변경 케이스 추가 | #2 trigger 시 |
| `tests/test_label_registry_seed.py` | narrow 시드 검증 | #3 strict 채택 시 |
| `tests/test_llm_backend_gemini_inventory_item_integration.py` | acceptable set strict | #4 trigger 시 |

## 8. Test strategy

* LIVE 검증 측정 → 결과 표 (위 §3.3) → 가지치기.
* 자동 회귀 0 유지 (M11.4 의 1592 baseline).
* 신규 단위 테스트 ~10 (각 분기별 + ratio 조정 ± std 검증).

## 9. 알려진 한계 (M11.5 범위 밖)

| 항목 | 우선순위 | 후속 |
|---|---|---|
| Gemini 모델 업그레이드 (3.1-flash → 3.5-flash) | 중 | M12 (별도 spec) — 비용 ↑ + 정확도 ↑ trade-off |
| BATCH_SPRITESHEET_PROMPT category 강제 완화 | 낮 | M12+ (multi-frame inventory 지원) |
| AsepriteAtlas hash-mode 비균일 시트 prompt | 낮 | M16 (유사 검색) 와 함께 |

## 10. 다음 단계

1. 이 spec 사용자 검토.
2. `milestones/M11_5_plan.md` 작성 (LIVE 검증 → 분기 plan).
3. LIVE 검증 진행 → 결과 표 채우기.
4. 결과 기반 patch 진행 (Phase 분할 — #2/#3/#4 중 trigger 된 항목만).
5. `M11_5_verification.md` — patch 후 자동 + 수동 검증.
6. PR → main → tag v0.2.4 → Trusted Publishing 자동 publish (7회째).

작업 단위 추정: **~1.5일** (LIVE 검증 0.5일 + trigger 된 patch 평균 1일).  LIVE 결과가 모두 OK 면 0.5일에 종료.
