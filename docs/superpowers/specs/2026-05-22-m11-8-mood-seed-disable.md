# 2026-05-22 — M11.8 Design Spec: mood 시드 `neutral`/`minimalist` 비활성화 (v0.2.7 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md)
- 전제: [PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) M11.7 main 머지 (`04c205e`)
- 다음: `milestones/M11_8_plan.md`
- Version 후보: **v0.2.7 patch** (M11.7 LIVE 의 catch-all 'neutral' 잔존 해소)

## 1. 한 줄 요약

M11.7 [`M11_7_verification.md §3.1`](../../milestones/M11_7_verification.md) 의 잔존 — 시트 4/5 자산에 `mood='neutral'` 잔존 + `mood='minimalist'` 1/5 — 를 LabelRegistry 시드 `mood.neutral` + `mood.minimalist` `is_enabled=0` 마이그로 해소.  prompt 가이드만으로 막을 수 없는 Gemini catch-all 경향에 대한 **시드 단계 차단 layer**.

## 2. 결정 매트릭스

| # | 항목 | 작업량 | 효과 범위 | 마이그 | 채택 |
|---|---|---:|---|---|---|
| A3-mood-neutral | **`mood.neutral` `is_enabled=0`** — `core/labels.py` SEED + idempotent migration | ~0.3일 | LLM 응답 `mood=['neutral']` 토큰이 whitelist 위반 → drop | label_catalog_signature 변경 | ✅ |
| A3-mood-minimalist | **`mood.minimalist` `is_enabled=0`** — 동일 패턴 | ~0.1일 (위와 묶음) | LLM 응답 `mood=['minimalist']` 토큰 drop | 동일 | ✅ |
| A3-palette-neutral | **`palette.neutral` 은 절대 유지** | 0 | M11.6 tone group enum 핵심 토큰 (warm/cool/monochrome/high_contrast/pastel/neutral).  palette 응답에서는 'neutral' 이 유효 | — | ❌ (절대 금지) |
| A3-prompt | **두 prompt 의 mood enum 목록에서 'neutral' / 'minimalist' 제거** | ~0.1일 | LLM 응답 단계에서 catch-all 토큰 자체 노출 차단 | 0 | ✅ |

**채택**: A3-mood-neutral + A3-mood-minimalist + A3-prompt 묶음.  palette.neutral 은 절대 유지.

## 3. Architecture — 시드 비활성화 마이그 패턴

### 3.1 기존 인프라

- `LabelRegistry.bootstrap()` 가 시드 dict 를 SQLite `labels` 테이블에 upsert.  `is_enabled` 컬럼이 이미 존재 (M2 부터 시드 관리 시 사용자가 disable 가능).
- `label_catalog_signature` 가 시드 변경 시 cache invalidation 신호로 사용 (M11.2 기반).
- `LabelRegistry.list_labels(axis)` 는 `is_enabled=1` 만 반환 — 자동으로 LLM 응답 whitelist 에서 제거됨.

### 3.2 fix

`core/labels.py` 의 SEED dict 를 정의된 시점에는 `(label, description)` 튜플이지만, 일부 시드를 `is_enabled=0` 으로 마크할 방법이 현재 없음.  두 가지 옵션:

**옵션 A** — SEED dict 의 튜플을 3-tuple `(label, description, is_enabled=True)` 로 확장 + bootstrap 에 enabled 전파.

**옵션 B** — 별도 `DISABLED_BY_DEFAULT: dict[axis, set[str]]` 상수 + bootstrap 에서 후처리로 `is_enabled=0` 적용.

**채택**: **옵션 B** — 기존 dict 구조 보존, 변경 영향 좁음.  `DISABLED_BY_DEFAULT = {"mood": {"neutral", "minimalist"}}` 한 줄 추가.

### 3.3 idempotent migration

기존 DB 에 이미 `mood.neutral` 이 `is_enabled=1` 로 있고 사용자가 라벨을 0건이라도 붙였다면 **사용자 라벨은 보존**해야 함 (M11.5 패턴).  bootstrap 시:

```python
for axis, labels_to_disable in DISABLED_BY_DEFAULT.items():
    for label in labels_to_disable:
        # 사용자가 명시적으로 enabled=1 로 변경한 경우 존중 — 첫 마이그 시점 (즉 처음 보는
        # label_catalog_signature) 에만 is_enabled=0 적용
        store.set_label_enabled_if_unchanged(axis, label, False)
```

`set_label_enabled_if_unchanged` 는 신규 helper — 사용자 변경 흔적이 없는 (예: `label_overrides` 테이블 또는 별도 `meta.disabled_by_default_signature` 마커) 시드만 disable.

## 4. Architecture — prompt enum 동기화

M11.6 BATCH_IMAGE_PROMPT / BATCH_SPRITESHEET_PROMPT 의 mood 줄:

```
mood (array of strings, optional): pick from heroic, dark, playful, neutral, minimalist, calm, mysterious, intense, or similar
```

→ 'neutral' 과 'minimalist' 제거.  남는 enum: `heroic, dark, playful, calm, mysterious, intense, or similar` (5 토큰 + "or similar").

## 5. Module breakdown

### 5.1 변경 파일

| 파일 | 변경 | 조건 |
|---|---|---|
| `src/assetcache/core/labels.py` | `DISABLED_BY_DEFAULT: dict[str, set[str]]` 상수 + bootstrap 에 disable 패스 추가 | 무조건 |
| `src/assetcache/core/store.py` | `set_label_enabled_if_unchanged(axis, label, enabled)` helper 신설 + `meta.disabled_by_default_signature` 마커 추적 | 무조건 |
| `src/assetcache/core/analyzer/messages.py` | mood enum 목록에서 'neutral' / 'minimalist' 제거 (두 prompt) | 무조건 |
| `tests/test_label_registry_disabled_by_default.py` (신규) | DISABLED_BY_DEFAULT 적용 + idempotent + 사용자 변경 보호 | 무조건, ~5 test |
| `tests/test_prompt_mood_enum_excludes_neutral_minimalist.py` (신규) | 두 prompt mood 줄에서 neutral/minimalist 부재 + 다른 mood 토큰 보존 | 무조건, ~2 test |
| `tests/test_llm_backend_gemini_inventory_item_integration.py` (확장) | 옵트인 — 시트 strip 응답 mood 에 'neutral' 0건 단언 | 무조건, ~1 test |

### 5.2 의존성

신규 의존성 0.  M11.6 + M11.7 의 prompt + LabelRegistry 인프라 재사용.

## 6. Test strategy

### 6.1 자동 테스트

- `DISABLED_BY_DEFAULT` 상수 정의 + bootstrap 적용 확인 — 단위 test 2
- 기존 DB 가 `mood.neutral` `is_enabled=1` 인 상태에서 bootstrap 호출 → `is_enabled=0` 으로 변경 (마이그) — 단위 test 1
- 사용자가 `mood.neutral` 을 명시적으로 `is_enabled=1` 로 복원 후 bootstrap 재호출 → 변경 안 됨 (사용자 변경 보호) — 단위 test 1
- `palette.neutral` 은 영향 없음 (axis 격리) — 단위 test 1
- 두 prompt mood 줄에서 'neutral' + 'minimalist' 토큰 부재 + 다른 mood 토큰 (`heroic`, `dark`, `playful`, `calm`, `mysterious`, `intense`) 보존 — 단위 test 2

### 6.2 LIVE 검증

`scripts/drive_live_batch.py` 재실행 (M11.7 LIVE setup 그대로).  목표:

- 시트 5 자산 mood='neutral' = **0건** (M11.7 의 4/5 → 0/5)
- 시트 5 자산 mood='minimalist' = **0건** (M11.7 의 1/5 → 0/5)
- mood 라벨 응답이 있다면 `heroic`/`dark`/`playful`/`calm`/`mysterious`/`intense` 중에서 (다양화)
- 회귀: M11.6 palette 5/5 + M11.7 crown mood 0 + 'other' 0건 모두 유지

## 7. 알려진 한계 (M11.8 범위 밖)

| 항목 | 우선순위 | 후속 |
|---|---|---|
| 사용자가 `mood.neutral` 을 enable 복원 시 LIVE 응답 분포 | 낮 | 사용자 자율 선택 — 강제 안 함 |
| `palette.neutral` 응답이 시트 자산에서 보일 가능성 (M11.6 의 hero=cool+neutral) | 정상 | 변경 없음 — tone group enum 유지 |
| `mood` enum 의 다른 catch-all 토큰 (`calm`?) | M11.9+ | LIVE 응답 분포 모니터링 후 결정 |

## 8. 다음 단계

1. 이 spec 사용자 검토.
2. `milestones/M11_8_plan.md` 작성 (Phase 분할 — P1 시드 + migration TDD → P2 prompt 동기화 TDD → P3 LIVE 검증 → P4 PR).
3. TDD red → green.
4. LIVE 검증 (M11.7 setup 재사용).
5. `M11_8_verification.md` — auto + 옵트인 + LIVE.
6. PR → main → tag v0.2.7 → Trusted Publishing OIDC 자동 (M11.4~M11.7 의 v0.2.3~v0.2.6 publish 누적 보류 — 0.2.2 → 0.2.7 직접 bump).

작업 시간 추정: **~1일** (P1 0.5일 + P2 0.2일 + P3 0.2일 + P4 0.1일).
