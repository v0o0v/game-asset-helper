# 2026-05-22 — M11.7 Design Spec: mood label noise cleanup (v0.2.6 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md)
- 전제: [PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) M11.6 main 머지 (`da4f169`)
- 다음: `milestones/M11_7_plan.md`
- Version 후보: **v0.2.6 patch** (M11.6 LIVE 검증에서 발견된 mood 라벨 노이즈 2건 해소)

## 1. 한 줄 요약

M11.6 [`M11_6_verification.md §3.1`](../../milestones/M11_6_verification.md) 의 mood 응답 잡음 — (a) `crown_icon` (inventory_item) 에 `mood=heroic/playful` 합산 + (b) 시트 자산 5/5 가 일률적으로 `mood=minimalist/neutral` — 을 prompt 가이드만으로 차단.

## 2. 결정 매트릭스

| # | 항목 | 작업량 | 효과 범위 | 마이그 | 채택 |
|---|---|---:|---|---|---|
| A1 | **mood OPTIONAL** — 두 prompt 에 "mood 는 array, but leave `[]` if no clear mood applies" 추가 | ~0.2일 | Gemini 가 catch-all mood 토큰 채우는 패턴 차단 | 0 | ✅ |
| A2 | **category 별 mood 차단** — 두 prompt 에 "Do NOT include mood for inventory_item / ui_icon / tile / background" 명시 | ~0.2일 | inventory item / UI / tile 같은 정적 자산에 mood 강제 응답 차단 | 0 | ✅ |
| A3 | **시드 `minimalist`/`neutral` 비활성화** — `enabled=0` 마이그 (기존 라벨 보호) | ~0.4일 | 시트 자산이 동일 mood 로 합쳐지는 패턴 강제 차단 | label_catalog_signature 변경 | ❌ M11.7 범위 밖 |

**채택**: A1 + A2.  A3 는 LIVE 결과 보고 결정 (M11.8 후보).

## 3. Architecture — A1 mood OPTIONAL

### 3.1 현재 state

`BATCH_IMAGE_PROMPT` 의 mood 줄 ([core/analyzer/messages.py](../../src/assetcache/core/analyzer/messages.py)):

```
- mood (array of strings): pick from heroic, dark, playful, neutral,
  minimalist, calm, mysterious, intense, or similar
```

→ array 라고만 명시, empty 허용 여부 모호.  Gemini 는 array 응답이 비면 안전 차원에서 catch-all 토큰 (`neutral`, `minimalist`) 을 채우는 경향.

`BATCH_SPRITESHEET_PROMPT` 도 M11.6 A1 에서 동일 패턴 (mood enum 추가).

### 3.2 fix

두 prompt 의 mood 줄에 "leave `[]` if no clear mood applies" 명시.  이 가이드 한 줄이 Gemini 가 catch-all 강제 응답을 멈추는 결정적 시그널 (BATCH_IMAGE_PROMPT 의 palette 줄에서 hex 금지가 작동한 패턴과 동일).

## 4. Architecture — A2 category 별 mood 차단

### 4.1 현재 state

M11.6 LIVE 에서 crown_icon (category=inventory_item) 응답에 mood=`heroic`, `playful` 합산.  inventory item 은 정적 객체라 감정 라벨이 의미 없음.

### 4.2 fix

두 prompt 의 Guidance 블록에 다음 추가:

```
- Do NOT include mood values for inventory_item, ui_icon, tile, or
  background — these are static objects without emotional tone.
  Leave mood as [] for these categories.
```

LIVE 에서 A1 만으로 inventory_item mood 가 비워지면 A2 는 redundant 일 수도 있음.  하지만 명시적 가이드가 Gemini 일관성 측면에서 안전.

## 5. Module breakdown

### 5.1 변경 파일

| 파일 | 변경 | 조건 |
|---|---|---|
| `src/assetcache/core/analyzer/messages.py` | A1: 두 prompt 의 mood 줄에 "leave [] if no clear mood".  A2: Guidance 블록에 category 별 mood 차단 가이드 | 무조건 |
| `tests/test_prompt_mood_optional.py` (신규) | A1: 두 prompt 에 mood optional 가이드 노출 | 무조건 |
| `tests/test_prompt_category_mood_exclusion.py` (신규) | A2: 두 prompt 에 inventory_item/ui_icon/tile/background mood 차단 가이드 노출 | 무조건 |
| `tests/test_llm_backend_gemini_inventory_item_integration.py` (확장) | 옵트인 LIVE — crown_icon mood `[]` + spritesheet mood `[]` 또는 다양화 | 무조건, ~2 test |

### 5.2 의존성

신규 의존성 0.  M11.6 prompt 인프라 + payload_parser whitelist (mood 빈 배열 허용 — 이미 동작) 재사용.

## 6. Test strategy

### 6.1 자동 테스트

- 두 prompt 의 mood 줄에 "leave" + "[]" 같은 OPTIONAL 시그널 — 단위 test 2 (prompt 별 1)
- 두 prompt 의 Guidance 블록에 `inventory_item` + `ui_icon` + `tile` + `background` + mood 차단 키워드 — 단위 test 2 (prompt 별 1)
- 기존 tone group enum + 'other' 금지 가이드 보존 (regression) — 명시 단언 없이도 기존 test 보호

### 6.2 LIVE 검증

`scripts/drive_live_batch.py` 재실행 — M11.6 LIVE setup 그대로 (6 자산).  목표:

- crown_icon mood 라벨 = `[]` (LIVE DB 의 `asset_labels` axis=mood 0건)
- 시트 5 자산 mood 라벨 다양화 또는 빈 배열 (5/5 모두 minimalist+neutral 합치는 패턴 차단)
- 회귀: crown=inventory_item ✓ + 시트 palette 5/5 ✓ + 'other' 0건 ✓

LIVE 결과로 A3 (시드 비활성화) 채택 여부 결정.

## 7. 알려진 한계 (M11.7 범위 밖)

| 항목 | 우선순위 | 후속 |
|---|---|---|
| Gemini 모델 업그레이드 (3.1-flash-lite → 3.1-flash) | 중 | M12 별도 spec |
| 시드 `minimalist`/`neutral` 비활성화 (A3) | 낮 | LIVE A1+A2 효과 부족 시 M11.8 |
| mood 응답이 너무 풍부 (5+ 토큰) 일 때 cap | 낮 | M12+ 범위 |

## 8. 다음 단계

1. 이 spec 사용자 검토.
2. `milestones/M11_7_plan.md` 작성 (Phase 분할 — P1 prompt fix + 단위 test → P2 LIVE 검증 → P3 옵트인 LIVE 확장 + PR).
3. TDD red → green.
4. LIVE 검증 (M11.6 setup 재사용).
5. `M11_7_verification.md` — auto + 옵트인 + LIVE.
6. PR → main → tag v0.2.6 → Trusted Publishing OIDC 8회째 자동 (M11.4/M11.5/M11.6 의 v0.2.3/v0.2.4/v0.2.5 publish 보류 → 0.2.2 → 0.2.6 직접 bump).

작업 시간 추정: **~1일** (P1 0.5일 + P2 0.3일 + P3 0.2일).
