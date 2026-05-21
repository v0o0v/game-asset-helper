# M6 — 시트 분석 + 애니메이션 (설계 spec)

> 본 문서는 [M5 spec](./2026-05-17-m5-web-gui-and-library-redesign.md) 과 같은 형식이며, [`CLAUDE.md`](../../../CLAUDE.md) §2 / [`DESIGN.md`](../../../DESIGN.md) §4.2.2 + §6.6 + §11 Milestone 6 의 한 줄 항목을 작업 단위까지 풀어 적은 1차 결정 문서다. 본 spec 의 결정을 [`milestones/M6_plan.md`](../../../milestones/M6_plan.md) 가 phase / task 로 옮기고, 실제 구현은 plan 의 체크박스를 따라간다.
>
> **작성일**: 2026-05-18
> **타깃 마일스톤**: M6 (M5 완료 후)
> **예상 소요**: 1주 (~5일)
> **누적 자동 테스트 baseline**: M5 종료 시 796 passed + 1 skipped + 4 deselected. M6 종료 시 ~856 passed 목표.

---

## 1. 한 줄 요약

스프라이트 시트(여러 프레임이 격자로 배치된 PNG 또는 Aseprite/TexturePacker JSON 동반)를 분석 파이프라인에서 자동 감지·격자 분할·애니메이션 라벨링하고, 18번째 MCP 도구 `suggest_animation_frames` 로 `(asset_id, animation_name) → (frame_indices, fps_hint)` 매핑을 노출한다. 라이브러리 와이드 카드에 `🎞 N frames` 배지 추가. **신규 의존성 0**.

## 2. 배경 / 발견 사항 (코드베이스 실측)

- **`spritesheet` kind 는 placeholder 상태**:
  - `src/gah/mcp/models.py:16` — `_AssetKind = Literal["sprite", "spritesheet", "sound"]` 정의돼 있지만 분석 파이프라인은 채우지 않는다.
  - `src/gah/core/asset_kind.py:5` 주석 — *"the spritesheet split happens in M4 when the analyzer can look at the pixels"* — 실제로는 M6 로 이월.
  - `src/gah/core/store.py:63-66` — `SpriteMeta.{frame_w, frame_h, frame_count, animation_tags}` 컬럼이 이미 정의돼 있지만 어떤 분석 경로도 채우지 않는다.
- **animation axis 라벨 9개 이미 시드됨**: `src/gah/core/labels.py:248-257` 에서 `idle/walk/run/jump/attack/hurt/death/cast/crouch` 라벨이 `LabelRegistry` 부팅 시 등록됨. 본 M6 는 라벨 자체가 아니라 **프레임 인덱스 매핑**을 추가한다.
- **카드 배지 자리 준비됨**: `src/gah/web/templates/_card_wide.html` 의 메타 영역에 M6 가 끼워 넣을 자리가 이미 존재 (조건문만 활성하면 됨).
- **`classify()` 는 확장자만 본다**: PNG/WebP/JPG 모두 `"sprite"` 로 분류. 시트 여부는 픽셀을 봐야 알 수 있어 분석 단계에서 promote.
- **사이드카 JSON 파서 없음**: Aseprite / TexturePacker 어느 쪽도 코드 없음.
- **격자 추정 알고리즘 없음**: DESIGN §4.2.2 가 *"가로/세로로 투명 행/열을 찾아 자동 분할"* 이라고 명시하지만 구현은 없다.

## 3. 시나리오 (M6 종료 시 동작)

### 3.1 사이드카 JSON 동반 시트 (Aseprite export)

사용자가 `library/heroes_pack/hero_walk.png` (256×32, 가로 8 프레임) + `hero_walk.json` (Aseprite "Array" export) 을 드롭 →

1. `PackManager` 가 `assets.kind="sprite"` 로 인덱싱 (`classify()` 가 확장자 기반).
2. `AnalysisQueue` 가 픽업 → `sheet.detect()` 호출:
   - `<basename>.json` 발견 → `json_parser.parse()` → `AsepriteAtlas` 객체.
   - `frames` 배열 길이 = 8, 각 프레임 bbox + `duration` 추출.
   - `meta.frameTags` 에 `{"name":"walk","from":0,"to":7}` 있으면 그대로 매핑.
3. `SpritesheetAnalyzer` 가 8 프레임 합성 미리보기 (Pillow) → Gemma 4 호출 → `animation_hint=["walk"]` 응답 (frameTags 와 일치).
4. `Store.upsert_sprite_meta(asset_id, kind="spritesheet", frame_w=32, frame_h=32, frame_count=8, animation_tags=["walk"], animations_json={"walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 12, "source": "json_tag"}})`.
5. 라이브러리 와이드 카드에 `🎞 8 frames` 배지 출현.
6. Claude Code 가 `suggest_animation_frames({asset_id: 88, animation: "walk"})` 호출 → `{"frame_indices": [0,1,2,3,4,5,6,7], "fps_hint": 12}` 응답.

### 3.2 JSON 없는 균일 격자 시트

사용자가 `library/enemies_pack/slime.png` (128×32, 가로 4 프레임 균등 간격, JSON 없음) 드롭 →

1. M1 인덱싱 동일.
2. `sheet.detect()`:
   - JSON 사이드카 없음 → `grid_detect()` 호출.
   - Pillow 로 알파 채널 행 합 / 열 합 → 모든 행에 알파 있음 (가로 1줄), 4 등분 위치에 알파 0 인 열 발견 → `GridLayout(rows=1, cols=4, frame_w=32, frame_h=32)`.
3. `SpritesheetAnalyzer` 가 4 프레임 합성 → Gemma 호출 → `animation_hint=["walk", "idle"]` 응답.
4. 프레임 라벨 매핑 = Gemma 가 시트 전체에 walk + idle 라벨만 줬을 때 우리는 **frame range 정보를 모름**. v1 단순화: **시트 전체를 같은 라벨로 매핑** — `animations_json = {"walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"}, "idle": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"}}`.
5. 카드 배지 + MCP 응답 동일.

> v2 (M7+) 에서 사용자가 GUI 로 frame range 를 미세 조정하거나, Aseprite frameTags 와 Gemma 추론을 더 정교하게 머지하는 흐름 검토.

### 3.3 시트가 아닌 단일 스프라이트

사용자가 `library/icons/sword.png` (32×32 단일 이미지) 드롭 →

1. M1 인덱싱 동일 (`kind="sprite"`).
2. `sheet.detect()`:
   - JSON 사이드카 없음 → `grid_detect()` 호출.
   - 알파 채널 분석 결과 빈 행·열 없음 또는 단일 프레임 추정 → `None` 반환.
3. `SpriteAnalyzer` (기존 경로) 로 폴백 → `kind="sprite"` 유지 → 기존 M2~M5 흐름 그대로.

### 3.4 격자 자동 분할 실패

사용자가 비균등 atlas (TexturePacker hash 출력 없는 비정형 PNG) 드롭 →

1. JSON 없음 → `grid_detect()` 가 균등 간격 검증 실패 → `None`.
2. `SpriteAnalyzer` 폴백 → `kind="sprite"` 유지. 사용자가 GUI 로 frame size 입력하는 UX 는 v2 (M7+).

## 4. 결정사항

### 4.1 격자 검출은 분석기에서, classify() 는 변경 없음 (D1)

**결정** — `src/gah/core/asset_kind.py` 의 `classify()` 는 변경 없음. M1 의 확장자 기반 분류 유지. 분석기 단계 (`SpritesheetAnalyzer`) 에서 **검출 성공 시 `kind="spritesheet"` 로 promote**.

이유:
- `classify()` 는 watcher 가 인덱싱 단계에서 호출하는 즉시 분류기. 파일을 열어 픽셀을 보는 비싼 연산을 인덱싱 단계에 끼우면 워처 처리량 급감.
- 분석기는 어차피 파일을 열어 Pillow 로 작업하므로 sheet detection 은 자연스러운 추가 부담.
- `assets.kind` 컬럼은 분석 후 store 가 UPDATE — 기존 흐름 (`Store.upsert_asset`) 그대로.

### 4.2 사이드카 JSON 우선, 격자 자동 추정 폴백 (D2)

**결정** — DESIGN §4.2.2 그대로:

1. `<basename>.json` (예: `hero.png` ↔ `hero.json`) 같은 디렉터리 존재 검사.
2. 있으면 `json_parser.parse()` → 자동 형식 판별 (Aseprite / TexturePacker / Unknown) → 성공 시 frame list 반환.
3. JSON 없거나 파싱 실패 → `grid_detect()` (Pillow alpha 채널 행·열 스캔) → `GridLayout|None`.
4. 둘 다 실패 → 일반 `sprite` 로 폴백 (사용자 수동 입력 UX 는 v2 — M7+).

### 4.3 animations 저장 모델 = `sprite_meta.animations_json` 단일 컬럼 (D3)

**결정** — 새 컬럼 추가:

```sql
ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT;
```

값 예시:
```json
{
  "walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 12, "source": "json_tag"},
  "idle": {"start_frame": 8, "end_frame": 11, "fps_hint": 8, "source": "gemma_inferred"}
}
```

`source` enum: `"json_tag"` (Aseprite/TexturePacker JSON 내 frameTags) | `"gemma_inferred"` (Gemma 응답 + 시트 전체 매핑) | `"user"` (v2 의 GUI 수동 입력 placeholder).

기존 `animation_tags TEXT` 컬럼은 **v1 backward compat 로 유지** — analyzer 가 함께 채움 (라벨 이름 배열만, 예: `["walk", "idle"]`). v2 에서 deprecation 평가.

별도 테이블 (`sheet_frames`, `sheet_animations`) 대신 단일 컬럼 채택 이유:
- M6 1주 일정에 마이그레이션 + JOIN 부담 낭비.
- v1 시나리오 (균일 격자 + Aseprite 정형 시트) 에 단일 컬럼 충분.
- 비정형 atlas 풍부 표현은 M7+ 에서 v2 로 별도 마일스톤 또는 패치 (M8 사이 끼울 수 있음).

### 4.4 8칸 그리드 미리보기 Gemma 호출 (D4)

**결정** — DESIGN §4.2.2 그대로:

- 프레임 ≤ 8: 모든 프레임을 가로 8칸 (프레임 수 만큼) 1행 그리드로 합성.
- 프레임 > 8: **선형 stride 샘플링** `indices = [round(i * (N - 1) / 7) for i in range(8)]` — 8 프레임을 선택해 가로 8칸 1행 합성. 예: N=16 → `[0, 2, 4, 6, 9, 11, 13, 15]`. N=24 → `[0, 3, 7, 10, 13, 16, 20, 23]`.
- 합성 이미지 max 768×768 (기존 SpriteAnalyzer 의 `max_long_edge` 와 동일).
- Gemma 응답: 기존 SpriteAnalyzer 의 `animation_hint: array (0..4) from [{animation_enum}]` 스키마 그대로 — animation 라벨 추출.

### 4.5 MCP 도구 18번째 — `suggest_animation_frames` (D5)

**결정** — DESIGN §6.6 그대로:

```jsonc
// input
{ "asset_id": 88, "animation": "walk" }

// output
{ "frame_indices": [4, 5, 6, 7, 8, 9], "fps_hint": 12 }
```

에러 코드:
- `404_not_found` — `asset_id` 가 존재하지 않거나 `sprite_meta` 가 없음.
- `400_invalid_input` — `kind != "spritesheet"`. 메시지: `"asset N is kind=sprite, not a spritesheet"`.
- `404_not_found` — animation 이 `animations_json` 에 없음. 메시지: `"animation 'X' not found — available: [walk, idle]"`.

`frame_indices` = `list(range(start_frame, end_frame + 1))` (inclusive). 시트가 균일하면 단순한 연속 시퀀스, Aseprite frameTags 가 있으면 그쪽 정의 그대로.

### 4.6 와이드 카드 배지 (D6)

**결정** — `_card_wide.html` 메타 영역에 추가:

```html
{% if row.kind == "spritesheet" and row.frame_count %}
  <span class="frame-badge" aria-label="{{ row.frame_count }} frames">
    🎞 {{ row.frame_count }} frames
  </span>
{% endif %}
```

CSS 변수 `--frame-badge-bg`, `--frame-badge-fg` 를 `themes.css` 에 추가 (light/dark 모두). `SearchHit` dataclass 에 `frame_count: int | None = None` 필드 추가 (`core/search.py`). 라이브러리 router 가 `sprite_meta.frame_count` 조회 후 SearchHit 에 주입.

### 4.7 fps_hint 기본 12, Aseprite duration 에서 역산 (D7)

**결정** —
- Aseprite JSON 의 각 프레임에 `duration` (ms) 이 있으면 평균 frame duration 으로 역산: `fps_hint = round(1000 / mean_duration_ms)`.
- duration 없거나 0 인 프레임이 있으면 기본 `fps_hint=12`.
- TexturePacker JSON 은 duration 정보 없음 → 항상 12.
- Gemma 추론 케이스도 항상 12 (Gemma 가 fps 를 알려주지 않음).

### 4.8 격자 추정 알고리즘 (D8)

**결정** —

```python
def grid_detect(img: PIL.Image) -> GridLayout | None:
    """Pillow alpha 채널 행·열 합으로 균일 격자 추정.

    Steps:
      1. RGBA 변환. 알파 없으면 None.
      2. 각 행의 알파 합 / 각 열의 알파 합 계산 (numpy).
      3. 알파 합이 0 인 행·열을 "투명 경계" 로 식별.
      4. 투명 경계 사이 간격이 모두 같아야 균일 격자.
      5. 균일 검증 통과 시 GridLayout(rows, cols, frame_w, frame_h) 반환.
      6. 실패 (알파 없음 / 비균일 / 단일 프레임 추정) → None.
    """
```

**한계** (v1):
- 알파 없는 시트 (불투명 PNG 위에 시트 그려진 경우) 미지원 — `None` 반환.
- 비균일 간격 atlas 미지원 — Aseprite/TexturePacker JSON 동반 필요.
- 단일 프레임 (rows=1, cols=1) 은 시트로 분류 안 함 (그냥 sprite).

### 4.9 사이드카 JSON 파서 자동 판별 (D9)

**결정** —

```python
def parse(json_path: Path) -> AsepriteAtlas | TexturePackerAtlas | None:
    """Try Aseprite first, then TexturePacker. Return None on failure."""
    data = json.loads(json_path.read_text())

    # Aseprite: frames = dict OR array, meta.app starts with "Aseprite"
    if isinstance(data.get("meta", {}).get("app", ""), str) and \
       data["meta"]["app"].lower().startswith("aseprite"):
        return _parse_aseprite(data)

    # TexturePacker: frames = dict OR array, meta.app = "TexturePacker"
    if "TexturePacker" in data.get("meta", {}).get("app", ""):
        return _parse_texture_packer(data)

    # 폴백: frames 가 dict 면 hash, array 면 array — Aseprite 시도
    if isinstance(data.get("frames"), (dict, list)):
        try:
            return _parse_aseprite(data)
        except (KeyError, ValueError):
            pass

    return None
```

Aseprite "Array" 모드: `frames = [{"frame": {"x":0,"y":0,"w":32,"h":32}, "duration": 100}, ...]` + `meta.frameTags = [{"name":"walk","from":0,"to":7}]`.

Aseprite "Hash" 모드: `frames = {"hero 0.aseprite": {...}, ...}` — 순서를 보장하기 위해 키 정렬 (자연 정렬: `"hero 0"` → `"hero 1"` → … → `"hero 10"`).

TexturePacker: `frames` 형식이 비슷하지만 `frameTags` 없음. duration 정보 없음.

`AsepriteAtlas(frames: list[FrameSpec], tags: list[AnimationSpec])` 데이터클래스.
`TexturePackerAtlas(frames: list[FrameSpec])` 데이터클래스.

### 4.10 schema 변경 = 컬럼 1개 추가, 마이그레이션 (D10)

**결정** — `Store.initialize()` 에서 `ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT;` 실행. SQLite 의 `ADD COLUMN` 은 NULL 디폴트라 기존 데이터 무영향.

마이그레이션은 idempotent — `PRAGMA table_info(sprite_meta)` 로 컬럼 존재 검사 후 ADD. 또는 try/except 로 `OperationalError: duplicate column` 무시.

## 5. 모듈 계획

### 5.1 신규 모듈

| 경로 | 책임 |
|---|---|
| `src/gah/core/sheet/__init__.py` | 빈 패키지 마커 |
| `src/gah/core/sheet/types.py` | `FrameSpec(x, y, w, h, duration_ms, name)` / `AnimationSpec(name, start, end, fps_hint, source)` / `GridLayout(rows, cols, frame_w, frame_h)` / `AsepriteAtlas` / `TexturePackerAtlas` 데이터클래스 |
| `src/gah/core/sheet/json_parser.py` | `parse(json_path) -> AsepriteAtlas | TexturePackerAtlas | None` + 자동 형식 판별 (§4.9) |
| `src/gah/core/sheet/grid_detect.py` | `grid_detect(img: PIL.Image) -> GridLayout | None` (§4.8) |
| `src/gah/core/sheet/preview.py` | `make_preview_composite(img, layout_or_atlas, max_size=768) -> PIL.Image` — 8칸 합성 미리보기 (§4.4) |
| `src/gah/core/analyzer/spritesheet.py` | `SpritesheetAnalyzer` — `analyze(input) -> AnalyzerResult`. 내부에서 `sheet.detect()` 호출, 실패 시 `SpriteAnalyzer` 위임 |

### 5.2 수정 모듈

| 경로 | 변경 |
|---|---|
| `src/gah/core/store.py` | (1) `SpriteMeta.animations_json: dict | None = None` 필드 추가 (`@dataclass(frozen=True)` 갱신). (2) `initialize()` 에 idempotent ALTER TABLE. (3) `upsert_sprite_meta` 의 INSERT/UPDATE SQL 에 `animations_json` 컬럼 포함. (4) `get_sprite_meta(asset_id) -> SpriteMeta | None` 헬퍼 추가 (kind 가 spritesheet 일 때 MCP 도구가 호출). (5) `update_asset_kind(asset_id, kind)` 메서드 추가 — analyzer 가 promote 할 때 사용. |
| `src/gah/core/analysis_queue.py` | `_analyze_one(task)` 분기 — `kind == "sprite"` 일 때 `SpritesheetAnalyzer` 호출 (내부에서 sprite 폴백). Sound 는 변경 없음. |
| `src/gah/core/analyzer/__init__.py` | `SpritesheetAnalyzer` export. |
| `src/gah/core/search.py` | `SearchHit` 에 `frame_count: int | None = None` 필드 추가. `HybridSearcher._hydrate_hit()` 가 sprite_meta JOIN 시 frame_count 읽음. |
| `src/gah/web/routers/library.py` | `_hit_to_row()` (또는 동등 직렬화 함수) 가 `frame_count` 를 응답에 포함 (`row.frame_count`). |
| `src/gah/web/templates/_card_wide.html` | `🎞 N frames` 배지 추가 (§4.6). |
| `src/gah/web/static/css/themes.css` | `--frame-badge-bg`, `--frame-badge-fg` light/dark 추가. |
| `src/gah/web/static/css/main.css` | `.frame-badge` 클래스 스타일 추가. |
| `src/gah/mcp/models.py` | (1) `SuggestAnimationFramesRequest(asset_id: int, animation: str)`. (2) `SuggestAnimationFramesResult(frame_indices: list[int], fps_hint: int)`. |
| `src/gah/mcp/tools.py` | `tool_suggest_animation_frames(deps, req) -> SuggestAnimationFramesResult` (§4.5). |
| `src/gah/mcp/server.py` | `register_all_tools` 에 `suggest_animation_frames` 추가 (17 → **18**). `INSTRUCTIONS` 갱신 — §6 또는 새 절 추가 (Claude 가 animation 추론을 자동 호출하는 흐름). 로그 `tools=17` → `tools=18`. |
| `docs/MCP_USAGE_GUIDE.md` | 18번째 도구 설명 + 사용 예시 추가. |
| `DESIGN.md` | §4.2.2 갱신 (구현 완료 표시), §6.6 갱신 (실제 구현 결과), §11 Milestone 6 완료 표시. |
| `CLAUDE.md` | §2 진행 현황 표 — M6 행 (대기 → 진행 → 완료). §8 다음 작업 갱신 (M7). |
| `HANDOFF.md` | M6 완료 인계 — 자동 테스트 통과 카운트 + 시나리오 + 다음 작업 (M7 Unity Asset Store). |
| `pyproject.toml` | **변경 없음** (신규 의존성 0). |

### 5.3 테스트 (~60 신규 케이스)

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_sheet_types.py` | ~5 | `FrameSpec` / `AnimationSpec` / `GridLayout` / `AsepriteAtlas` / `TexturePackerAtlas` 데이터클래스 동등성 / 직렬화 |
| `tests/test_sheet_json_parser.py` | ~12 | Aseprite "Array" 파싱 / Aseprite "Hash" 파싱 + 자연 정렬 / TexturePacker 파싱 / `meta.frameTags` 매핑 / `duration` 평균 fps 역산 / 알 수 없는 형식 → None / 빈 JSON → None / 잘못된 JSON → None + log / 빈 frames → None / duration 0 인 프레임 → fps 12 폴백 / Aseprite 자동 감지 (`meta.app="Aseprite"`) / TexturePacker 자동 감지 (`meta.app="TexturePacker"`) |
| `tests/test_sheet_grid_detect.py` | ~10 | 가로 N 프레임 균일 격자 검출 / 세로 N 프레임 균일 격자 / 알파 없음 → None / 비균일 간격 → None / 단일 프레임 → None / 알파 행 합 / 알파 열 합 / 그리드 (2 행 × 4 열) / 작은 이미지 (16×16, 1×1) → None / 빈 알파 (모두 투명) → None |
| `tests/test_sheet_preview.py` | ~5 | 8 프레임 정확히 → 그대로 합성 / 16 프레임 → 선형 stride 8 (인덱스 `[0,2,4,6,9,11,13,15]`) / 4 프레임 → 그대로 / 768×768 max 검증 / RGBA 합성 |
| `tests/test_analyzer_spritesheet.py` | ~10 | JSON 사이드카 → AsepriteAtlas 사용 / JSON 없음 + grid 검출 → GridLayout 사용 / 둘 다 실패 → SpriteAnalyzer 폴백 / `kind="spritesheet"` promote / animations_json 채워짐 / frame_w/h/count 채워짐 / animation_tags backward compat 채워짐 / Gemma 응답 + frameTags 머지 / Gemma 실패 → partial state / 단일 라벨 시 시트 전체 매핑 |
| `tests/test_store_m6.py` | ~8 | `animations_json` 컬럼 마이그레이션 idempotent / `upsert_sprite_meta` 와 animations_json 왕복 / `get_sprite_meta(id)` / `update_asset_kind(id, "spritesheet")` / 기존 데이터 NULL 호환 / animations_json 직렬화 라운드트립 / 마이그레이션 두 번 실행 / 컬럼 미존재 시 자동 추가 |
| `tests/test_mcp_tools_m6.py` | ~12 | `suggest_animation_frames` 정상 (Aseprite frameTags 케이스) / Gemma 추론 케이스 / asset_id 미존재 → 404 / kind=sprite → 400 / animation 미존재 → 404 (available 메시지) / frame_indices inclusive (start..end) / fps_hint 12 폴백 / fps_hint Aseprite duration 역산 / animations_json NULL → 404 / 빈 animations dict → 404 / 정확한 인덱스 시퀀스 / kind=sound → 400 |
| `tests/test_web_card_frame_badge.py` | ~5 | spritesheet 카드 → 배지 렌더 / sprite 카드 → 배지 미렌더 / sound 카드 → 배지 미렌더 / frame_count=None → 배지 미렌더 / aria-label 정확 |
| `tests/test_mcp_integration.py` (수정) | 0 신규 / 갱신 | `tools/list` 응답 17 → **18** 도구 (`suggest_animation_frames` 포함). `INSTRUCTIONS` 길이 변화 무관. |

**합계 ~67 신규 active 케이스**.

baseline 796 + ~67 = **~863 active 목표**.

## 6. 작업 phase

| Phase | 기간 | 산출물 |
|---|---:|---|
| **0 — 스캐폴딩 + 테스트 fixture** | 0.5일 | `core/sheet/` 패키지 + `types.py` + Aseprite/TexturePacker 샘플 JSON fixtures + 4 테스트 파일의 red 케이스 작성 |
| **1 — JSON 파서 + grid_detect + preview** | 1.5일 | `json_parser.py` / `grid_detect.py` / `preview.py` 구현 + ~32 테스트 통과 |
| **2 — SpritesheetAnalyzer + Store 마이그레이션** | 1일 | `analyzer/spritesheet.py` + `store.py` 컬럼 추가 + `analysis_queue.py` 라우팅 + ~18 테스트 통과 |
| **3 — MCP 도구 18번째 + INSTRUCTIONS** | 1일 | `tool_suggest_animation_frames` + `register_all_tools` + `mcp_integration` 18 도구 검증 + ~12 테스트 통과 |
| **4 — Web 카드 배지** | 0.5일 | `_card_wide.html` + `SearchHit.frame_count` + library router + CSS + ~5 테스트 통과 |
| **5 — 문서 마감 + verification** | 0.5일 | `M6_verification.md` + DESIGN/CLAUDE/HANDOFF/MCP_USAGE_GUIDE 갱신 |
| **합계** | **~5일** | |

## 7. 핵심 결정 요약 (체크리스트)

- [x] **D1**: `classify()` 변경 없음, 분석기에서 promote.
- [x] **D2**: JSON 사이드카 우선, 격자 자동 추정 폴백.
- [x] **D3**: `sprite_meta.animations_json` 단일 컬럼.
- [x] **D4**: 8칸 그리드 미리보기 Gemma 호출.
- [x] **D5**: `suggest_animation_frames` = 18번째 MCP 도구.
- [x] **D6**: 와이드 카드 `🎞 N frames` 배지.
- [x] **D7**: `fps_hint` 기본 12, Aseprite duration 역산.
- [x] **D8**: Pillow alpha 채널 행·열 합 격자 추정.
- [x] **D9**: `<basename>.json` 사이드카 자동 형식 판별.
- [x] **D10**: `ALTER TABLE` idempotent 마이그레이션.

## 8. v1 의도적 미룬 항목 (v2 또는 M7+ 흡수)

- **사용자 frame size 입력 GUI** — 격자 자동 분할 실패 시 사용자가 수동 입력 (DESIGN §4.2.2 마지막 줄). M7+ 또는 별도 작은 패치.
- **비정형 atlas 풍부 표현** — TexturePacker hash atlas, Aseprite slice 영역, sprite atlas 의 패딩/회전. M7+ 별도 마일스톤 또는 v2 (sheet_frames 테이블 추가).
- **per-frame duration 풍부 노출** — `suggest_animation_frames` 가 frame 별 duration_ms 도 노출. v1 은 `fps_hint` 평균만.
- **animation 일괄 재라벨링 GUI** — 사용자가 시트 카드에서 frame range 를 마우스로 조정. M7+.
- **시트 통계 (도미넌트 색 / pixel art 판정) 의 시트별 미세 조정** — 현재 SpriteAnalyzer 의 시트 전체 평균 그대로. v2 에서 frame 단위 통계 검토.
- **`request_rescan(scope="sheets_only")`** — 시트만 재분석 트리거. v2.
- **Aseprite slice 영역** — `meta.slices` 의 nine-slice 정보 활용. M7+.
- **무손실 GIF / WebP 애니메이션** — `.gif` / `.webp` 시트는 v2. v1 은 PNG 만.

## 9. 알려진 한계 (v1 종료 시)

- 격자 자동 분할은 **알파 채널 의존**. 불투명 시트 (단색 배경 위 그려진 시트) 는 JSON 사이드카 필수.
- Gemma 가 시트 전체에 여러 라벨 (`walk + idle`) 을 줬을 때 **frame range 분할 불가** — 시트 전체를 같은 범위로 매핑. Aseprite frameTags 있으면 분할 가능.
- `frame_count = 1` 인 자산은 시트로 분류 안 함 (의도적 — 단일 프레임 시트는 의미 없음).
- `fps_hint` 가 시트 평균 — Aseprite 가 프레임별로 다른 duration 을 설정한 경우 평균으로 단순화.
- 라이브러리에 기존 분석된 시트 후보가 있어도 **재분석 트리거 없음** — `request_rescan` 으로 명시 호출 필요 또는 자동 promote 는 v2.

## 10. 신규 의존성

**없음**. Pillow / numpy / Ollama 클라이언트 / mcp / FastAPI / Jinja2 모두 기존.

## 11. 참고 자료

- [Aseprite — Export Sprite Sheet (CLI)](https://www.aseprite.org/docs/cli/) — JSON Array / Hash 형식
- [TexturePacker — Sprite Sheet Format Reference](https://www.codeandweb.com/texturepacker/documentation/sprite-sheet-format) — JSON 출력 스펙
- [Pillow — Image.getchannel / numpy 변환](https://pillow.readthedocs.io/) — 알파 채널 추출
- [`DESIGN.md` §4.2.2](../../../DESIGN.md) — 시트 분석 흐름 정의
- [`DESIGN.md` §6.6](../../../DESIGN.md) — `suggest_animation_frames` MCP 도구 명세

---

**spec 종료**. 본 spec 의 결정을 [`milestones/M6_plan.md`](../../../milestones/M6_plan.md) 가 task 단위로 풀어 적고, `milestones/M6_todo.md` 가 TDD 체크리스트로 추적한다.
