# M11.3 Plan — Detection Cache (B + C 결합, v0.2.2 candidate)

## 0. 본 plan 의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-21-m11-3-detection-cache.md`](../docs/superpowers/specs/2026-05-21-m11-3-detection-cache.md)
- 전제: [PR #19](https://github.com/v0o0v/assetcache-mcp/pull/19) M11.2 main 머지 (`d34f1dd`), 회귀 1528
- 다음 산출물: `M11_3_todo.md` (TDD red→green 체크리스트) + plan 의 Phase 별 detailed task
- 본 plan 은 **starter** — 다음 세션 시작 시 `superpowers:writing-plans` 로 확장 또는 직접 TDD.

## 1. 목표

M11.2 가 도입한 `detect_sheet` 의 시트당 3중 호출 (chat_image classify / chat_spritesheet classify / BatchPoller persist) 을 2-층 캐시로 1회로 압축. grid-only 시트가 다수인 라이브러리의 sweep 비용 ~6초/100장 절약.

## 2. 산출물

| # | 산출물 | 비고 |
|---:|---|---|
| 1 | `core/batch/sheet_classifier.py` 의 `classify_image_assets` 에 `cache` + `save_sprite_meta` 인자 추가 | sheet hit 시 sprite_meta 자동 enrich+save |
| 2 | `core/batch/manager.py` 의 `BatchManager._detection_cache: OrderedDict` (LRU max 1024) + classify 호출 시 전달 | sweep 메모리 캐시 (옵션 C) |
| 3 | `core/batch/poller.py` 의 `_try_enrich_with_sheet` 가 `store.get_sprite_meta` 확인 + animations_json 재구성 + detect 우회 | DB cache 활용 (옵션 B) |
| 4 | `core/store.py` 의 `get_sprite_meta(asset_id)` 헬퍼 (없으면 추가, 있으면 그대로) | 기존 확인 필요 |
| 5 | `tests/test_batch_sheet_classifier_cache.py` (신규, ~5 케이스) | cache + save_sprite_meta 동작 |
| 6 | `tests/test_batch_manager_detection_cache.py` (신규, ~5 케이스) | sweep cache + LRU eviction |
| 7 | `tests/test_batch_poller_sprite_meta_cache.py` (신규, ~5 케이스) | sprite_meta 있으면 detect 우회 |
| 8 | `milestones/M11_3_verification.md` (M11.2 와 묶어서 수동 검증) | 시나리오 = M11.2 검증 시나리오 + 캐시 hit 확인 1건 |

## 3. Phase 분할 (얇은 starter)

### Phase 1 — classify_image_assets cache + save_sprite_meta 인자

- store.get_sprite_meta 존재 확인 (없으면 추가)
- classify_image_assets 시그니처 확장 + 캐시 사용 + 시트 hit 시 자동 enrich+save (`compute_sprite_meta` 호출)
- 신규 테스트 ~5건

### Phase 2 — BatchManager `_detection_cache`

- `OrderedDict` LRU (max 1024) 초기화
- `_do_submit("chat_image")` 와 `("chat_spritesheet")` 모두 cache 전달
- 신규 테스트 ~5건 (same-sweep 재사용 + LRU eviction)

### Phase 3 — BatchPoller sprite_meta 캐시 활용

- `_try_enrich_with_sheet` 가 `store.get_sprite_meta` 확인 후 우회
- animations_json → AnimationSpec 재구성 helper (작은 free function)
- 신규 테스트 ~5건 (cache hit 시 detect 0회 + 라벨 동일성)

### Phase 4 — 회귀 + verification + PR

- 전체 회귀 `pytest -q` 통과 (1528 + ~15)
- 옵트인 미적용 (외부 API 변경 0)
- `M11_3_verification.md` — M11.2 의 5 시나리오 + 새 §2.6 (캐시 hit 측정)
- PR → main 머지 → 사용자 수동 검증 (M11.2 + M11.3 묶어서) → tag v0.2.2 → Trusted Publishing 자동 publish (5회째)

## 4. 작업 시간 추정

- Phase 1~3: 0.5~0.6일
- Phase 4 (검증/publish): 0.1~0.2일
- **합계 ~0.7~0.8일**

## 5. 시작 명령

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git checkout feat/m11-3-detection-cache
```

(이미 본 작업 시작 시 생성됨 — main `d34f1dd` 기준)

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ 1528 passed 확인 후 Phase 1 부터.

## 6. 핵심 설계 결정 (spec §3, §4)

- 채택: **옵션 B + C 결합** (~0.7일) — 옵션 A 별도 테이블 (~1일) 대신 sprite_meta + sweep memory 활용
- BatchManager `_detection_cache` 는 process lifetime 메모리 LRU (max 1024)
- sprite_meta cache 의 stale 검출 미적용 — 시트 파일 변경 시 사용자 직접 재분석 트리거 (향후 patch 후보)
- `classify_image_assets` 가 시트 hit 시 즉시 `compute_sprite_meta + enrich + save` 까지 수행 — sprite_meta 저장이 새로운 책임으로 들어옴

## 7. 수동 검증 (M11.2 와 묶어서 한 번에)

M11.3 머지 후 `milestones/M11_3_verification.md` 에 따라 수동 검증:
1. M11.2 5 시나리오 — grid-only 시트 / Aseprite 시트 / sprite-only / chains 누락 / /analyzing 4행
2. M11.3 1 시나리오 — 같은 시트 batch 진입 시 로그/타이밍으로 detect_sheet 호출 횟수 확인 (1회 expected)
3. 통과 시 → tag v0.2.2 → Trusted Publishing 자동 publish
