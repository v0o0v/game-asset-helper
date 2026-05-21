# M11.5 Plan — LIVE validation + tuning patches (v0.2.4 candidate)

## 0. 본 plan 의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-21-m11-5-live-validation-and-tuning.md`](../docs/superpowers/specs/2026-05-21-m11-5-live-validation-and-tuning.md)
- 전제: [PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21) M11.4 main 머지 (`7794d48`) + (선택) v0.2.3 PyPI publish
- 본 plan 은 **starter** — LIVE 검증 결과 기반으로 다음 세션에서 가지치기 + Phase 확장.

## 1. 목표

`milestones/M11_4_verification.md` §4 + §6 의 한계 6건 중 **LIVE 결과 기반으로 trigger 되는 항목** 만 fix:

| # | 한계 | trigger 조건 |
|---:|---|---|
| 1 | LIVE 검증 자체 (m113_complex 6 자산 재실행) | 무조건 (gate) |
| 2 | `_AXIS_SPAN_RATIO=0.8` 휴리스틱 튜닝 | elemental_cyan 결과가 sprite 또는 hero_warrior 등이 spritesheet 가 아니게 됐을 때 |
| 3 | palette tone-group narrow | LIVE 응답에 `vibrant`/`saturated`/`muted` 등 prompt enum 밖 라벨이 자주 나올 때 |
| 4 | llm_integration acceptable set strict | LIVE 통과 후 1회 strict 화 (`'other'` 제거) |
| 5 (M12) | Gemini 모델 업그레이드 (3.1-flash-lite → 3.1-flash) | crown_icon 이 여전히 character 일 때 |
| 6 (M12) | BATCH_SPRITESHEET_PROMPT category 강제 완화 | 별도 마일스톤 — multi-frame inventory 요구 시점 |

#5, #6 은 M12 별도 spec 으로 분리 — M11.5 범위 밖.

## 2. 산출물

| # | 산출물 | 비고 |
|---:|---|---|
| 1 | `milestones/M11_5_verification.md` — LIVE 측정 결과 표 + 분기 결정 + patch 검증 | 무조건 |
| 2 | `core/sheet/grid_detect.py` — `_AXIS_SPAN_RATIO` 조정 또는 std-기반 검증 | #2 trigger 시 |
| 3 | `core/labels.py` — palette 시드 narrow + 마이그 (기존 라벨 disable) | #3 strict 시 |
| 4 | `core/analyzer/messages.py` — prompt hex 강조 추가 | #3 trigger 시 |
| 5 | `tests/test_sheet_grid_detect_color_edge.py` 확장 | #2 trigger 시 |
| 6 | `tests/test_label_registry_seed.py` 확장 | #3 strict 시 |
| 7 | `tests/test_llm_backend_gemini_inventory_item_integration.py` strict | #4 trigger 시 |

## 3. Phase 분할 (가지치기형)

### Phase 1 — LIVE 검증 (gate)

* fresh `--data-dir` + GEMINI_API_KEY + `batch.toggle="forced_on"` + m113_complex 6 자산 복사.
* `M11_4_verification.md` §3 의 SQL 로 측정 결과 표 채우기.
* `M11_5_verification.md` §1 에 결과 기록.

### Phase 2 — D-1 결과 분기

* elemental_cyan kind=spritesheet ✓ → Phase 3 skip
* sprite 유지 → Phase 3 (#2 AXIS_SPAN_RATIO 튜닝) 진입

### Phase 3 — AXIS_SPAN_RATIO 튜닝 (조건부)

* sweep 0.7/0.75/0.85 측정 (단위 test 7~9 통과 보장).
* 또는 std-기반 검증 도입 (boundary 후보 row 별 diff 표준편차 임계).
* 신규 ~3 test.

### Phase 4 — LLM #3 결과 분기

* crown_icon category != character ✓ → Phase 5 strict 화 진입
* character 유지 → M12 spec trigger (별도 마일스톤)

### Phase 5 — llm_integration strict (조건부)

* acceptable set 에서 `'other'` 제거, crown 은 `{inventory_item, item}` 만 허용.
* LIVE 1회 통과 후 push.

### Phase 6 — palette tone-group narrow (조건부)

* LIVE 응답 분포 본 후 결정.
* strict 채택 시 시드 7 토큰 disable + label_catalog_signature 변경 확인.
* 신규 ~3 test.

### Phase 7 — 회귀 + verification + PR

* 전체 회귀 `pytest -q` 통과 (1592 + Phase 별 신규).
* `M11_5_verification.md` 최종 결과 표.
* PR → main → tag v0.2.4 → Trusted Publishing 자동 publish (7회째).

## 4. 작업 시간 추정

- Phase 1: 0.5일 (사용자 LIVE 시간 포함)
- Phase 2/4 분기: 0
- Phase 3: 0.5일 (조건부)
- Phase 5: 0.2일 (조건부)
- Phase 6: 0.5일 (조건부)
- Phase 7: 0.3일
- **합계 ~1.5~2일** (LIVE 결과 모두 OK 면 0.7일)

## 5. 시작 명령

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git checkout main
```

```powershell
git pull
```

```powershell
git checkout -b feat/m11-5-live-validation-tuning
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ baseline 1592 확인 후 Phase 1 (LIVE 검증) 부터.

## 6. 검증 시나리오 (M11_5_verification.md skeleton)

| # | 자산 | 기대 결과 | LIVE 결과 (TBD) | 분기 |
|---:|---|---|---|---|
| 1 | elemental_cyan | kind=spritesheet | — | sprite 면 → Phase 3 |
| 2 | crown_icon | category ∈ {inventory_item, item, icon} | — | character 면 → M12 |
| 3 | hero_warrior (Aseprite) | 변경 0 | — | regression |
| 4 | mage_purple | 변경 0 | — | regression |
| 5 | knight_gold | frame_w=17 (D-2 그대로) | — | regression |
| 6 | monster_red | 변경 0 | — | regression |
| 7 | palette 응답 분포 | hex 0건 | — | hex 있으면 #3 strict |
