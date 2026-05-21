# M11.4 검증 — grid_detect 강화 + LLM 분류 정확도 (v0.2.3 candidate)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-21-m11-4-grid-detect-strengthen-llm-accuracy.md`](../docs/superpowers/specs/2026-05-21-m11-4-grid-detect-strengthen-llm-accuracy.md)
- 상위 plan: [`M11_4_plan.md`](./M11_4_plan.md)
- 전제: [PR #20](https://github.com/v0o0v/assetcache-mcp/pull/20) M11.3 main 머지 + [v0.2.2 PyPI publish](https://pypi.org/project/assetcache-mcp/0.2.2/)
- 본 문서는 M11.3 LIVE 검증 v2 (`milestones/M11_3_verification.md` §4b) 에서 발견된 두 한계 (D-1 elemental_cyan 오분류 + LLM #3 crown_icon 오분류) 가 M11.4 구현으로 해소됐는지를 자동 + 수동 + LIVE 로 확인한다.

## 1. 자동 검증

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Expected: **1583 passed + 1 skipped + 59 deselected**.  baseline 1559 + 신규 24 (Phase 1 grid_detect color-edge 9 + Phase 2 seed 3 + Phase 3 payload_parser 5 + Phase 3 batch prompt 4 + Phase 4 sync prompt 3).  llm_integration deselect 는 57 → 59 (Phase 4 의 +2 — crown_icon + ui_button gemini chat).

### 1.1 옵트인 — 실 Gemini 호출 (GEMINI_API_KEY 필요)

```powershell
$env:GEMINI_API_KEY = "AIza..."
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -m llm_integration tests/test_llm_backend_gemini_inventory_item_integration.py -v
```

Expected: 2 case 모두 통과.

* `test_crown_classified_as_inventory_item_not_character` — 합성 crown PNG → category != 'character'.
* `test_ui_button_classified_as_ui_icon_not_character` — 합성 settings cog PNG → category != 'character'.

acceptable set (`inventory_item`/`item`/`icon`/`ui_icon`/`other`) 안에 들어오면 통과.  Gemini 가 여전히 character 로 응답하면 prompt 가이드 강화가 부족하다는 시그널 — M12 (모델 업그레이드 또는 prompt 추가 튜닝) 후보.

## 2. 수동 검증 시나리오 (synthetic — 라이브러리 사전 셋업 0)

### 2.1 grid_detect color-edge 단위 확인

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -c @"
from PIL import Image
from assetcache.core.sheet.grid_detect import grid_detect

colors = [(0,255,255),(255,0,255),(255,255,0),(255,0,0),(0,0,255),(0,255,0)]
img = Image.new('RGBA', (6*64, 64), (0,0,0,255))
for i, c in enumerate(colors):
    img.paste(Image.new('RGBA', (64, 64), c+(255,)), (i*64, 0))
print(grid_detect(img))
"@
```

Expected: `GridLayout(rows=1, cols=6, frame_w=64, frame_h=64)` — M11.3 의 None 한계 해소.

### 2.2 alpha_color_weight=0 으로 비활성 (M6 호환)

위와 동일 입력에 `grid_detect(img, alpha_color_weight=0.0)` 호출 → `None` (M6 동작 그대로).

### 2.3 시드 확장 확인

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -c @"
from assetcache.core.labels import SEED_LABELS
for axis in ('category', 'mood', 'palette'):
    tokens = sorted(t for t, _ in SEED_LABELS[axis])
    print(axis, '→', tokens)
"@
```

Expected:
* category 에 `inventory_item`, `ui_icon` 포함
* mood 에 `minimalist`, `neutral` 포함
* palette 에 `high_contrast` 포함

### 2.4 BATCH_IMAGE_PROMPT enum 명시 확인

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -c @"
from assetcache.core.analyzer.messages import BATCH_IMAGE_PROMPT
print(BATCH_IMAGE_PROMPT)
"@
```

Expected: category enum 에 `inventory_item, ui_icon` 명시, palette 줄에 `warm, cool, monochrome, high_contrast, pastel, neutral` + `do NOT use hex codes like #FDD835`, Guidance 블록에 `crown, sword, potion, ...` 예시 포함.

### 2.5 palette hex 거부 동작 확인

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -c @"
from assetcache.core.analyzer.payload_parser import validate_image_payload

class _Reg:
    def list_labels(self, axis, *, enabled_only=True, with_description=False):
        return {'category':['character','inventory_item','other'],
                'style':['pixel_art','other'],
                'mood':['heroic'],
                'palette':['warm','cool','neutral'],
                'animation':[]}.get(axis, [])

ok, err, fixed = validate_image_payload(
    {'category':'inventory_item','style':'pixel_art',
     'palette':['warm','#FDD835','cool']}, _Reg())
print('ok=', ok)
print('err=', err)
print('palette=', fixed['palette'])
"@
```

Expected: `ok=False`, `err` 에 `palette_hex=#FDD835` 마커 포함, `palette=['warm', 'cool']` (hex 만 제거).

## 3. 수동 검증 시나리오 (LIVE — m113_complex 자산 재사용)

M11.3 v2 검증에서 사용한 `make_complex_sheets.py` 자산 (`elemental_cyan`, `crown_icon` 등) 을 fresh `--data-dir` 으로 재검증.

### 3.1 fresh data dir 셋업

```powershell
$verifyData = "$env:TEMP\m11_4_verify_data"
```

```powershell
Remove-Item -Recurse -Force $verifyData -ErrorAction SilentlyContinue
```

```powershell
New-Item -ItemType Directory -Path "$verifyData\library\m113_complex" -Force | Out-Null
```

기존 m113_complex 자산을 위 `library\m113_complex\` 로 복사 (M11.3 검증 때 만든 PNG/JSON 그대로 재사용).

### 3.2 tray 실행 + GEMINI_API_KEY + forced_on batch

```powershell
$env:GEMINI_API_KEY = "AIza..."
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m assetcache --tray --data-dir $verifyData
```

`/settings` 에서:
- `chains.chat_image = ["gemini"]`, `chains.chat_spritesheet = ["gemini"]`
- `batch.toggle = "forced_on"`

분석이 끝나면 다음 SQL 로 확인:

```powershell
sqlite3 "$verifyData\metadata.db" "SELECT name, kind, frame_w, frame_h, frame_count FROM assets a LEFT JOIN sprite_meta m ON m.asset_id=a.id WHERE a.kind IN ('sprite','spritesheet') ORDER BY a.id"
```

```powershell
sqlite3 "$verifyData\metadata.db" "SELECT a.name, l.axis, l.label FROM asset_labels l JOIN assets a ON a.id=l.asset_id WHERE l.axis IN ('category','palette','mood') ORDER BY a.name, l.axis"
```

### 3.3 기대 결과

| # | 자산 | 기대 결과 (M11.4) | M11.3 결과 |
|---:|---|---|---|
| 1 | elemental_cyan (1×6 64×64) | kind=spritesheet (D-1 color-edge) | kind=sprite ⚠ |
| 2 | crown_icon (32×32 single) | category ∈ {inventory_item, item, icon} (LLM #3) | category=character ⚠ |
| 3 | hero_warrior (Aseprite 4×4) | 변경 없음 (animations_json 보존) | ✓ |
| 4 | mage_purple (Aseprite 3×4) | 변경 없음 | ✓ |
| 5 | knight_gold (grid 1×8) | 변경 없음 (frame_w=17 D-2 그대로) | ✓ |
| 6 | monster_red (grid 2×2) | 변경 없음 | ✓ |

palette 결과는 Gemini 가 prompt 의 tone group 가이드를 얼마나 따르는지에 따라 다름 — 최소한 `#XXXXXX` hex 가 라벨로 들어오는 일이 없어야 한다 (validate_image_payload 가 거부).

## 4. 알려진 한계

| 항목 | 한계 | 후속 |
|---|---|---|
| Gemini 자체 분류 정확도 (특히 crown 같은 단순 아이콘 → character 오분류) | prompt 가이드는 강화됐지만 모델이 따르지 않을 가능성 — LIVE Gemini 호출로만 최종 확인 | M12 (모델 업그레이드 또는 추가 prompt 튜닝) |
| `_AXIS_SPAN_RATIO=0.8` 휴리스틱 | frame 내부 노이즈가 axis 의 80% 이상을 덮으면 spurious 경계로 오인 가능 | 실 자산에서 발견 시 ratio 조정 또는 std-기반 검증 추가 |
| color-edge fallback 이 사이드카 있는 시트와 어떻게 상호작용하는지 LIVE 미검증 | alpha 경로 성공 시 fallback 안 타니까 안전할 거지만 | M11_4_verification §3 LIVE 단계 |
| llm_integration acceptable set 에 'other' 포함 | prompt 효과 측정 정확도 약함 | LIVE 결과 본 후 좁히기 (M12 후보) |

## 5. 검증 완료 후

1. PR → main 머지.
2. `pyproject.toml` + `src/assetcache/__init__.py` 0.2.2 → 0.2.3 bump 커밋.
3. tag + push:
   ```powershell
   git tag v0.2.3
   ```
   ```powershell
   git push origin v0.2.3
   ```
4. Trusted Publishing OIDC workflow 자동 트리거 — 6회째 자동 publish (평균 30초 예상).
5. [PyPI v0.2.3 publish 확인](https://pypi.org/project/assetcache-mcp/0.2.3/) + GitHub release 자동 생성 확인.

## 6. PR 머지 후 별도 patch 후보

| 항목 | 우선순위 | 발견 |
|---|---|---|
| AXIS_SPAN_RATIO 휴리스틱 튜닝 (실 자산에서 false-positive/negative 발견 시) | 낮 | LIVE 검증에서 발견 |
| palette tone-group 으로 좁히기 (vibrant/saturated/muted 등 시드에서 제외) | 낮 | Gemini 응답 분포 본 후 결정 |
| BATCH_SPRITESHEET_PROMPT 의 category='character' 강제 완화 (multi-frame inventory 시트 지원) | 낮 | spec 범위 밖, 별도 마일스톤 |
