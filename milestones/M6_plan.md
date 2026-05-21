# M6 — 시트 분석 + 애니메이션 (구현 계획)

> **에이전트 작업자에게**: REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (권장) 또는 `superpowers:executing-plans` 로 task 단위 구현. Step 은 `- [ ]` 체크박스로 추적. 본 plan 은 [`M5_plan.md`](./M5_plan.md) 와 같은 한국어 마일스톤 표준 형식이며, [`docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md`](../docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md) (이하 "M6 spec") 의 10 결정 + 시나리오 4개 + 모듈 계획을 작업 단위까지 1:1 로 옮긴 것이다.

**목표** — 스프라이트 시트 자동 격자 분할(Aseprite/TexturePacker JSON 사이드카 우선 + Pillow alpha 채널 행/열 합 격자 추정 폴백) + Gemma 4 의 8칸 그리드 미리보기로 애니메이션 라벨링 + MCP 18번째 도구 `suggest_animation_frames` + 라이브러리 와이드 카드 `🎞 N frames` 배지. M5 의 모든 인프라(MCP 17 도구·SQLite 스키마·웹 UI·SpriteAnalyzer·OllamaClient) 100% 보존.

**아키텍처** — `core/sheet/` 신규 패키지가 sheet detection 3단계 (JSON 사이드카 → 격자 추정 → 폴백) 캡슐화. `core/analyzer/spritesheet.py` 가 기존 `SpriteAnalyzer` 컴포지션 + 감지 성공 시 `kind="spritesheet"` 로 promote. `sprite_meta` 에 신규 컬럼 `animations_json` (idempotent ALTER) 1개만 추가, 회귀 0. MCP server / FastAPI / Qt 트레이 / 분석 큐 / search 백엔드 코드는 분기점만 미세 수정.

**기술 스택** — Python 측 추가 의존성 0 (Pillow / numpy / Ollama / mcp 모두 기존). 신규 모듈 5 (`sheet/types`, `sheet/json_parser`, `sheet/grid_detect`, `sheet/preview`, `analyzer/spritesheet`). 수정 모듈 ~10. 신규 테스트 ~67 케이스.

---

## 1. 목표 (시나리오)

M6 가 끝나면 다음 네 시나리오가 정상 동작한다. (spec §3 의 4 시나리오를 plan 작업 단위로 매핑)

### 1.1 사이드카 JSON 동반 시트 (Aseprite)

사용자가 `library/heroes_pack/hero_walk.png` (256×32, 가로 8 프레임) + `hero_walk.json` (Aseprite "Array" export) 드롭 → 분석 파이프라인이:

1. JSON 사이드카 발견 → `AsepriteAtlas` 파싱 (`frames[8]`, `meta.frameTags=[{name:"walk",from:0,to:7}]`).
2. 8칸 합성 미리보기 → Gemma 호출 → `animation_hint=["walk"]`.
3. Store 저장: `kind="spritesheet"`, `frame_w=32, frame_h=32, frame_count=8, animations_json={"walk":{"start_frame":0,"end_frame":7,"fps_hint":12,"source":"json_tag"}}`.
4. 라이브러리 카드: `🎞 8 frames` 배지 노출.
5. Claude `suggest_animation_frames(88, "walk")` → `{frame_indices:[0..7], fps_hint:12}`.

### 1.2 JSON 없는 균일 격자 시트

사용자가 `library/enemies/slime.png` (128×32, 가로 4 프레임 균등, JSON 없음) 드롭 → `grid_detect()` 가 균일 격자 검출 → Gemma 가 `animation_hint=["walk","idle"]` → animations_json 에 시트 전체 매핑(`start=0, end=3` 두 라벨 모두). 카드 배지 + MCP 응답 동일.

### 1.3 시트가 아닌 단일 스프라이트

`library/icons/sword.png` (32×32) 드롭 → JSON 없음 → `grid_detect()` 가 빈 행/열 못 찾음 → `None` → `SpriteAnalyzer` 폴백 → `kind="sprite"` 유지. 배지 미노출.

### 1.4 격자 자동 분할 실패

비균일 atlas (JSON 없는 비정형 시트) → `grid_detect()` 가 균일 검증 실패 → `None` → `SpriteAnalyzer` 폴백 → `kind="sprite"` 유지. 사용자 수동 frame size 입력은 M7+ v2.

## 2. 산출물

### 2.1 코드 모듈

| 파일/디렉터리 | 책임 | 상태 |
|---|---|---|
| `src/gah/core/sheet/__init__.py` | 빈 패키지 마커. | 신규 |
| `src/gah/core/sheet/types.py` | `FrameSpec`/`AnimationSpec`/`GridLayout`/`AsepriteAtlas`/`TexturePackerAtlas` 데이터클래스 (frozen, 직렬화). | 신규 |
| `src/gah/core/sheet/json_parser.py` | `parse(json_path) -> AsepriteAtlas | TexturePackerAtlas | None` + 자동 형식 판별 (Aseprite Array/Hash + TexturePacker) + Aseprite `frameTags` 추출 + duration→fps_hint 평균. | 신규 |
| `src/gah/core/sheet/grid_detect.py` | `grid_detect(img: PIL.Image) -> GridLayout | None` — Pillow alpha 행/열 합 + 균일 간격 검증. 알파 없음·비균일·단일 프레임 → None. | 신규 |
| `src/gah/core/sheet/preview.py` | `make_preview_composite(img, frames_or_layout, max_size=768) -> PIL.Image` — 8칸 1행 합성 (≤8 그대로, >8 선형 stride `round(i*(N-1)/7)`). | 신규 |
| `src/gah/core/sheet/detect.py` | `detect_sheet(abs_path: Path) -> SheetDetection | None` — JSON 사이드카 → `grid_detect` → None 3단계 오케스트레이션. `SheetDetection(frames: list[FrameSpec], tags: list[AnimationSpec], source: str)`. | 신규 |
| `src/gah/core/analyzer/spritesheet.py` | `SpritesheetAnalyzer` 클래스 — `analyze(input) -> AnalyzerResult`. 내부에서 `detect_sheet()` 호출, 성공 시 `kind="spritesheet"` + animations_json 채움, 실패 시 SpriteAnalyzer 위임. | 신규 |
| `src/gah/core/analyzer/__init__.py` (수정) | `SpritesheetAnalyzer` export. | 수정 |
| `src/gah/core/store.py` (수정) | (1) `SpriteMeta` 에 `animations_json: dict | None = None` 필드. (2) `Store.initialize()` 에 idempotent `ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT`. (3) `save_sprite_meta` 의 SQL 에 컬럼 추가. (4) `get_sprite_meta(asset_id) -> SpriteMeta | None` 헬퍼 신규. (5) `update_asset_kind(asset_id, kind: str)` 신규. | 수정 |
| `src/gah/core/analysis_queue.py` (수정) | `_analyze_one` 의 분기 — `row.kind == "sprite"` 일 때 `self.spritesheet` (신규 의존성) 사용. `__init__` 에 `spritesheet: SpritesheetAnalyzer` 인자 추가. `_persist` 가 `result.kind == "spritesheet"` 면 `update_asset_kind` 호출. | 수정 |
| `src/gah/app.py` (수정) | `run_tray` 에서 `SpritesheetAnalyzer` 인스턴스 생성 후 `AnalysisQueue(spritesheet=...)` 주입. | 수정 |
| `src/gah/core/search.py` (수정) | `_hydrate_meta` 의 `kind_meta` 채우기에 `kind == "spritesheet"` 분기 추가 — `frame_count`/`frame_w`/`frame_h` 노출. | 수정 |
| `src/gah/web/routers/library.py` (수정) | `_hit_to_row()` (또는 카드 직렬화 함수) 가 `meta.frame_count` 를 row 에 포함. | 수정 |
| `src/gah/web/templates/_card_wide.html` (수정) | `🎞 N frames` 배지 추가 (kind=="spritesheet" 조건). | 수정 |
| `src/gah/web/templates/_card_list.html` (수정) | 동일 배지 추가 (리스트 뷰). | 수정 |
| `src/gah/web/static/css/themes.css` (수정) | `--frame-badge-bg`/`--frame-badge-fg` light/dark 추가. | 수정 |
| `src/gah/web/static/css/main.css` (수정) | `.frame-badge` 클래스 스타일 추가. | 수정 |
| `src/gah/mcp/models.py` (수정) | `SuggestAnimationFramesRequest(asset_id: int ge=1, animation: str min_length=1)` + `SuggestAnimationFramesResult(frame_indices: list[int], fps_hint: int)`. | 수정 |
| `src/gah/mcp/tools.py` (수정) | `tool_suggest_animation_frames(deps, req) -> SuggestAnimationFramesResult` — store 의 `get_sprite_meta` 호출 + animations_json lookup + 에러 매핑 (404/400/404). | 수정 |
| `src/gah/mcp/server.py` (수정) | `register_all_tools` 에 18번째 도구 등록. `tools=17` → `tools=18` 로그. INSTRUCTIONS §5 또는 새 절 추가 (Claude 가 spritesheet 자산을 Unity AnimationClip 으로 변환하는 흐름 안내). | 수정 |
| `docs/MCP_USAGE_GUIDE.md` (수정) | 18번째 도구 설명 + 사용 예시 추가. | 수정 |
| `DESIGN.md` (수정) | §4.2.2 갱신 (구현 완료 표시). §6.6 갱신 (실제 구현 결과). §11 M6 완료 표시. | 수정 |
| `CLAUDE.md` (수정) | §2 진행 현황 표 — M6 행 (대기 → 진행 → 완료). §8 다음 작업 갱신 (M7). | 수정 (M6 끝에) |
| `HANDOFF.md` (수정) | M6 완료 인계 — 자동 테스트 통과 카운트 + 시나리오 + 다음 작업 (M7 Unity Asset Store). | 수정 (M6 끝에) |
| `pyproject.toml` | **변경 없음** (신규 의존성 0). | — |
| `milestones/M6_todo.md` | TDD 체크리스트. | 신규 |
| `milestones/M6_verification.md` | M6 끝에 작성. | 신규 |

### 2.2 테스트

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_sheet_types.py` | ~5 | 5 데이터클래스 동등성·해시·repr |
| `tests/test_sheet_json_parser.py` | ~12 | Aseprite Array / Hash 자연 정렬 / TexturePacker / frameTags 매핑 / duration→fps 역산 / 알 수 없는 형식 → None / 빈 frames → None / 잘못된 JSON → None + log / `meta.app` 자동 감지 / duration 0 → fps 12 폴백 / hash 키 자연 정렬 검증 / TexturePacker `frameTags` 부재 OK |
| `tests/test_sheet_grid_detect.py` | ~10 | 가로 N 균일 / 세로 N 균일 / 알파 없음 → None / 비균일 → None / 단일 프레임 (1×1) → None / 2 행 × 4 열 검출 / 빈 알파 (전부 투명) → None / 작은 이미지 (8×8) → None / 알파 행/열 합 계산 정확 / 경계 픽셀 처리 |
| `tests/test_sheet_preview.py` | ~5 | 8 프레임 → 그대로 합성 / 16 프레임 → stride `[0,2,4,6,9,11,13,15]` / 4 프레임 → 그대로 / 768×768 max / RGBA 합성 |
| `tests/test_sheet_detect.py` | ~6 | JSON 사이드카 우선 / JSON 실패 시 grid_detect / 둘 다 None → None / 사이드카 경로 결정 (`<basename>.json`) / 비-PNG 입력 처리 / SheetDetection.source 정확 |
| `tests/test_analyzer_spritesheet.py` | ~10 | JSON 사이드카 → AsepriteAtlas 사용 + animations_json 채워짐 / grid 검출 → 시트 전체 매핑 / 둘 다 실패 → SpriteAnalyzer 폴백 (kind="sprite") / `kind="spritesheet"` promote / frame_w/h/count 정확 / animation_tags backward compat 채워짐 / Gemma 응답 + frameTags 머지 (frameTags 우선) / Gemma 실패 → partial state + animations_json 채워짐 / single label 시 시트 전체 매핑 / RGBA 가 아닌 PNG 처리 |
| `tests/test_store_m6.py` | ~8 | animations_json 컬럼 마이그레이션 idempotent / save_sprite_meta 와 animations_json 왕복 / get_sprite_meta(id) / update_asset_kind(id, "spritesheet") / 기존 데이터 NULL 호환 / animations_json dict 직렬화 라운드트립 / 마이그레이션 두 번 실행 / animations_json=None 도 정상 저장 |
| `tests/test_mcp_tools_m6.py` | ~12 | suggest_animation_frames 정상 (Aseprite frameTags) / Gemma 추론 케이스 / asset_id 미존재 → 404 / kind=sprite → 400 / animation 미존재 → 404 (available 메시지) / frame_indices inclusive / fps_hint 12 폴백 / fps_hint Aseprite 역산 / animations_json NULL → 404 / 빈 animations dict → 404 / 정확 인덱스 시퀀스 / kind=sound → 400 |
| `tests/test_web_card_frame_badge.py` | ~5 | spritesheet 카드 → 배지 렌더 / sprite 카드 → 배지 미렌더 / sound 카드 → 배지 미렌더 / frame_count=None → 배지 미렌더 / aria-label 정확 |
| `tests/test_mcp_integration.py` (수정) | 0 신규 / 갱신 | tools/list 응답 17 → **18** 도구 (`suggest_animation_frames` 포함) |

**합계 ~73 신규 active 케이스** (옵트인 0 신규, 기존 1 갱신). baseline 796 + 73 ≈ **~869 active** 예상. 정확 수는 verification 에서 확인.

## 3. 핵심 결정사항 (spec §4 의 10 결정 그대로)

| # | 결정 | spec 절 |
|---|---|---|
| D1 | classify() 변경 없음, 분석기에서 promote. | §4.1 |
| D2 | 사이드카 JSON 우선, grid_detect 폴백. | §4.2 |
| D3 | sprite_meta.animations_json 단일 컬럼. | §4.3 |
| D4 | 8칸 그리드 미리보기 Gemma 호출 + 선형 stride 샘플링. | §4.4 |
| D5 | suggest_animation_frames = 18번째 MCP 도구. | §4.5 |
| D6 | 와이드 카드 `🎞 N frames` 배지. | §4.6 |
| D7 | fps_hint 기본 12, Aseprite duration 역산. | §4.7 |
| D8 | Pillow alpha 행/열 합 격자 추정. | §4.8 |
| D9 | `<basename>.json` 자동 형식 판별. | §4.9 |
| D10 | idempotent ALTER TABLE 마이그레이션. | §4.10 |

---

## 4. 작업 단위

작업은 phase 순서대로 진행하고, 각 phase 의 task 는 표시된 순서대로 (앞 task 가 뒤 task 의 빌딩 블록). 각 task 는 **테스트 먼저 → 구현 → 통과 → 회귀 → 커밋** 사이클을 지킨다.

### 4.0 Phase 0 — 스캐폴딩 + 테스트 fixtures (~0.5일)

#### Task 0.1 — 브랜치 + sheet 패키지 스캐폴딩

**Files:**
- Create: `src/gah/core/sheet/__init__.py`

- [ ] **Step 1**: 현재 브랜치 확인 — `git status` → `On branch feat/m6-sheet-animation` clean (이미 분기됨).

- [ ] **Step 2**: 빈 패키지 마커 생성:

```python
"""M6 — sprite sheet 검출·파싱·미리보기 합성.

JSON 사이드카(Aseprite/TexturePacker) 우선, Pillow alpha 채널 격자 추정
폴백, 8칸 그리드 미리보기 합성을 책임진다. M6 spec §4.1~§4.9 참고.
"""
```

- [ ] **Step 3**: 임포트 smoke — `python -c "import gah.core.sheet; print('ok')"` → `ok`.

- [ ] **Step 4**: 커밋 — `scaffold(m6): core/sheet 패키지 마커 추가`.

#### Task 0.2 — sheet/types.py 데이터클래스

**Files:**
- Create: `src/gah/core/sheet/types.py`
- Create: `tests/test_sheet_types.py`

- [ ] **Step 1: 실패 테스트** (5 케이스):

```python
"""M6 — sheet 데이터클래스 동등성·해시·repr 회귀."""
from __future__ import annotations

from gah.core.sheet.types import (
    AnimationSpec,
    AsepriteAtlas,
    FrameSpec,
    GridLayout,
    TexturePackerAtlas,
)


def test_frame_spec_frozen_and_equal():
    a = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="hero 0")
    b = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="hero 0")
    assert a == b
    # frozen — 변경 시 FrozenInstanceError
    import dataclasses
    try:
        a.x = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    assert False, "FrameSpec must be frozen"


def test_animation_spec_round_trip():
    spec = AnimationSpec(name="walk", start_frame=0, end_frame=7,
                          fps_hint=12, source="json_tag")
    assert spec.name == "walk"
    assert spec.start_frame == 0
    assert spec.end_frame == 7
    assert spec.fps_hint == 12
    assert spec.source == "json_tag"


def test_grid_layout_simple():
    g = GridLayout(rows=1, cols=8, frame_w=32, frame_h=32)
    assert g.frame_count == 8


def test_aseprite_atlas_contains_frames_and_tags():
    frame = FrameSpec(x=0, y=0, w=32, h=32, duration_ms=100, name="0")
    tag = AnimationSpec(name="walk", start_frame=0, end_frame=0,
                       fps_hint=10, source="json_tag")
    atlas = AsepriteAtlas(frames=[frame], tags=[tag])
    assert len(atlas.frames) == 1
    assert atlas.tags[0].name == "walk"


def test_texture_packer_atlas_no_tags():
    frame = FrameSpec(x=0, y=0, w=64, h=64, duration_ms=0, name="a.png")
    atlas = TexturePackerAtlas(frames=[frame])
    assert len(atlas.frames) == 1
```

- [ ] **Step 2**: `pytest tests/test_sheet_types.py -v` → 5 FAIL `ModuleNotFoundError: gah.core.sheet.types`.

- [ ] **Step 3: 구현**:

```python
"""M6 — sheet 검출·파싱 결과 데이터클래스.

비기록 후속 분석기 / MCP 도구 / 테스트가 공유. ``frozen=True`` 로 불변
보장. M6 spec §4.3 / §4.9.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameSpec:
    """단일 프레임의 픽셀 박스 + (옵션) 표시 시간 + 원본 이름."""

    x: int
    y: int
    w: int
    h: int
    duration_ms: int  # 0 이면 정보 없음 — fps_hint 평균 계산에서 제외
    name: str  # Aseprite hash 모드의 원본 키 또는 array 모드 인덱스 문자열


@dataclass(frozen=True)
class AnimationSpec:
    """이름 붙은 애니메이션 = 시트 내 프레임 range."""

    name: str  # animation 라벨 (walk/idle/...)
    start_frame: int
    end_frame: int  # inclusive
    fps_hint: int  # 1 이상
    source: str  # 'json_tag' | 'gemma_inferred' | 'user'


@dataclass(frozen=True)
class GridLayout:
    """균일 격자 시트의 행·열·프레임 크기."""

    rows: int
    cols: int
    frame_w: int
    frame_h: int

    @property
    def frame_count(self) -> int:
        return self.rows * self.cols


@dataclass(frozen=True)
class AsepriteAtlas:
    """Aseprite export 파싱 결과 — frames + (선택) frameTags."""

    frames: list[FrameSpec]
    tags: list[AnimationSpec]


@dataclass(frozen=True)
class TexturePackerAtlas:
    """TexturePacker export — frames 만."""

    frames: list[FrameSpec]
```

- [ ] **Step 4**: `pytest tests/test_sheet_types.py -v` → 5 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 796 + 5 = 801 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): sheet 데이터클래스 5종 (FrameSpec/AnimationSpec/GridLayout/AsepriteAtlas/TexturePackerAtlas)`.

#### Task 0.3 — 테스트 fixture (Aseprite/TexturePacker 샘플)

**Files:**
- Create: `tests/fixtures/sheets/hero_walk_aseprite_array.json`
- Create: `tests/fixtures/sheets/hero_walk_aseprite_hash.json`
- Create: `tests/fixtures/sheets/icons_texturepacker.json`

- [ ] **Step 1**: `tests/fixtures/sheets/` 디렉터리 생성.

- [ ] **Step 2**: `hero_walk_aseprite_array.json` 작성 — Aseprite array 모드 + frameTags:

```json
{
  "frames": [
    { "filename": "hero 0", "frame": {"x":0,"y":0,"w":32,"h":32}, "duration": 100 },
    { "filename": "hero 1", "frame": {"x":32,"y":0,"w":32,"h":32}, "duration": 100 },
    { "filename": "hero 2", "frame": {"x":64,"y":0,"w":32,"h":32}, "duration": 100 },
    { "filename": "hero 3", "frame": {"x":96,"y":0,"w":32,"h":32}, "duration": 100 },
    { "filename": "hero 4", "frame": {"x":128,"y":0,"w":32,"h":32}, "duration": 80 },
    { "filename": "hero 5", "frame": {"x":160,"y":0,"w":32,"h":32}, "duration": 80 },
    { "filename": "hero 6", "frame": {"x":192,"y":0,"w":32,"h":32}, "duration": 80 },
    { "filename": "hero 7", "frame": {"x":224,"y":0,"w":32,"h":32}, "duration": 80 }
  ],
  "meta": {
    "app": "https://www.aseprite.org/",
    "version": "1.3.7",
    "format": "RGBA8888",
    "size": {"w":256,"h":32},
    "scale": "1",
    "frameTags": [{"name":"walk","from":0,"to":7,"direction":"forward"}]
  }
}
```

- [ ] **Step 3**: `hero_walk_aseprite_hash.json` — hash 모드 (자연 정렬 검증용, 10 프레임으로 키 정렬 함정 포함):

```json
{
  "frames": {
    "hero 10.aseprite": {"frame":{"x":320,"y":0,"w":32,"h":32},"duration":100},
    "hero 1.aseprite":  {"frame":{"x":32,"y":0,"w":32,"h":32},"duration":100},
    "hero 0.aseprite":  {"frame":{"x":0,"y":0,"w":32,"h":32},"duration":100},
    "hero 2.aseprite":  {"frame":{"x":64,"y":0,"w":32,"h":32},"duration":100},
    "hero 3.aseprite":  {"frame":{"x":96,"y":0,"w":32,"h":32},"duration":100},
    "hero 4.aseprite":  {"frame":{"x":128,"y":0,"w":32,"h":32},"duration":100},
    "hero 5.aseprite":  {"frame":{"x":160,"y":0,"w":32,"h":32},"duration":100},
    "hero 6.aseprite":  {"frame":{"x":192,"y":0,"w":32,"h":32},"duration":100},
    "hero 7.aseprite":  {"frame":{"x":224,"y":0,"w":32,"h":32},"duration":100},
    "hero 8.aseprite":  {"frame":{"x":256,"y":0,"w":32,"h":32},"duration":100},
    "hero 9.aseprite":  {"frame":{"x":288,"y":0,"w":32,"h":32},"duration":100}
  },
  "meta": {
    "app": "https://www.aseprite.org/",
    "version": "1.3.7",
    "format": "RGBA8888",
    "size": {"w":352,"h":32},
    "scale": "1"
  }
}
```

- [ ] **Step 4**: `icons_texturepacker.json`:

```json
{
  "frames": [
    {"filename":"sword.png","frame":{"x":0,"y":0,"w":16,"h":16}},
    {"filename":"shield.png","frame":{"x":16,"y":0,"w":16,"h":16}},
    {"filename":"potion.png","frame":{"x":0,"y":16,"w":16,"h":16}},
    {"filename":"gem.png","frame":{"x":16,"y":16,"w":16,"h":16}}
  ],
  "meta": {
    "app": "https://www.codeandweb.com/texturepacker",
    "version": "1.0",
    "image": "icons.png",
    "format": "RGBA8888",
    "size": {"w":32,"h":32},
    "scale": "1"
  }
}
```

- [ ] **Step 5**: 회귀 — `pytest -q` → 801 passed (fixture 추가만, 회귀 0).

- [ ] **Step 6**: 커밋 — `test(m6): Aseprite array/hash + TexturePacker JSON fixtures`.

---

### 4.1 Phase 1 — JSON 파서 + grid_detect + preview 합성 (~1.5일)

#### Task 1.1 — `sheet/json_parser.py` 구현

**Files:**
- Create: `src/gah/core/sheet/json_parser.py`
- Create: `tests/test_sheet_json_parser.py`

- [ ] **Step 1: 실패 테스트** (12 케이스) — `tests/test_sheet_json_parser.py`:

```python
"""M6 — sheet JSON 파서 (Aseprite Array/Hash + TexturePacker)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gah.core.sheet.json_parser import parse
from gah.core.sheet.types import AsepriteAtlas, TexturePackerAtlas

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def test_aseprite_array_8_frames():
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert isinstance(atlas, AsepriteAtlas)
    assert len(atlas.frames) == 8
    assert atlas.frames[0].x == 0 and atlas.frames[0].w == 32
    assert atlas.frames[7].x == 224

def test_aseprite_array_frame_tags():
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert len(atlas.tags) == 1
    walk = atlas.tags[0]
    assert walk.name == "walk"
    assert walk.start_frame == 0
    assert walk.end_frame == 7
    assert walk.source == "json_tag"


def test_aseprite_array_duration_to_fps_average():
    # 4×100ms + 4×80ms → 평균 90ms → 1000/90 ≈ 11.1 → round = 11
    atlas = parse(FIXTURES / "hero_walk_aseprite_array.json")
    assert atlas.tags[0].fps_hint == 11


def test_aseprite_hash_natural_sort():
    # 키 자연 정렬: hero 0..hero 10 — 사전 정렬 시 'hero 10' 이 'hero 2' 앞으로 가는 함정 회피
    atlas = parse(FIXTURES / "hero_walk_aseprite_hash.json")
    assert isinstance(atlas, AsepriteAtlas)
    assert len(atlas.frames) == 11
    # 자연 정렬이면 인덱스 0 = "hero 0", 1 = "hero 1", ..., 10 = "hero 10"
    assert atlas.frames[0].x == 0
    assert atlas.frames[1].x == 32
    assert atlas.frames[10].x == 320  # 마지막이 'hero 10' 이어야 함


def test_aseprite_hash_no_frame_tags_returns_empty_tags():
    atlas = parse(FIXTURES / "hero_walk_aseprite_hash.json")
    assert atlas.tags == []


def test_texture_packer_4_frames():
    atlas = parse(FIXTURES / "icons_texturepacker.json")
    assert isinstance(atlas, TexturePackerAtlas)
    assert len(atlas.frames) == 4
    assert atlas.frames[0].name == "sword.png"


def test_unknown_format_returns_none(tmp_path):
    p = tmp_path / "unknown.json"
    p.write_text(json.dumps({"unrelated": True}))
    assert parse(p) is None


def test_empty_frames_returns_none(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"meta": {"app": "Aseprite"}, "frames": []}))
    assert parse(p) is None


def test_invalid_json_returns_none(tmp_path, caplog):
    p = tmp_path / "broken.json"
    p.write_text("{ not valid json")
    assert parse(p) is None
    assert any("json" in rec.message.lower() for rec in caplog.records)


def test_aseprite_meta_app_detection(tmp_path):
    # meta.app 이 'Aseprite' 시작이면 Aseprite 분기
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [{"filename":"a","frame":{"x":0,"y":0,"w":8,"h":8},"duration":100}],
        "meta": {"app": "Aseprite v1.4 (custom)"}
    }))
    atlas = parse(p)
    assert isinstance(atlas, AsepriteAtlas)


def test_duration_zero_fps_fallback_12(tmp_path):
    # 모든 duration=0 이면 fps_hint=12 (기본)
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [
            {"filename":"a","frame":{"x":0,"y":0,"w":8,"h":8},"duration":0},
            {"filename":"b","frame":{"x":8,"y":0,"w":8,"h":8},"duration":0},
        ],
        "meta": {"app": "Aseprite", "frameTags":[{"name":"x","from":0,"to":1}]}
    }))
    atlas = parse(p)
    assert atlas.tags[0].fps_hint == 12


def test_texture_packer_app_detection(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "frames": [{"filename":"a.png","frame":{"x":0,"y":0,"w":8,"h":8}}],
        "meta": {"app": "https://www.codeandweb.com/texturepacker"}
    }))
    atlas = parse(p)
    assert isinstance(atlas, TexturePackerAtlas)
```

- [ ] **Step 2**: `pytest tests/test_sheet_json_parser.py -v` → 12 FAIL `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `src/gah/core/sheet/json_parser.py`:

```python
"""M6 — Aseprite + TexturePacker JSON 파서.

자동 형식 판별: meta.app 키워드 → Aseprite/TexturePacker. frames 가 dict
(hash 모드) 면 자연 정렬 후 array 화. duration 평균에서 fps_hint 역산.
M6 spec §4.7 / §4.9.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .types import AnimationSpec, AsepriteAtlas, FrameSpec, TexturePackerAtlas

log = logging.getLogger(__name__)

_DEFAULT_FPS = 12

_NATURAL_RE = re.compile(r"(\d+)|(\D+)")


def _natural_key(s: str) -> list:
    """'hero 10' 이 'hero 2' 뒤로 가도록 숫자 부분을 int 로 비교."""
    out: list = []
    for m in _NATURAL_RE.finditer(s):
        digits, text = m.group(1), m.group(2)
        if digits is not None:
            out.append((0, int(digits)))
        else:
            out.append((1, text))
    return out


def _avg_fps_from_durations(durations: list[int]) -> int:
    positives = [d for d in durations if d > 0]
    if not positives:
        return _DEFAULT_FPS
    avg_ms = sum(positives) / len(positives)
    if avg_ms <= 0:
        return _DEFAULT_FPS
    return max(1, round(1000.0 / avg_ms))


def parse(json_path: Path) -> "AsepriteAtlas | TexturePackerAtlas | None":
    """JSON 파일을 읽어 Aseprite 또는 TexturePacker atlas 로 파싱.

    포맷을 판별 못 하거나 frames 가 비어 있으면 None.
    """
    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("sheet JSON load failed: %s — %s", json_path, e)
        return None

    app = ""
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    if isinstance(meta.get("app"), str):
        app = meta["app"].lower()

    frames_field = data.get("frames")
    if not frames_field:
        return None

    # 1) TexturePacker 우선 (frames=list, meta.app 명시)
    if "texturepacker" in app:
        return _parse_texture_packer(frames_field)

    # 2) Aseprite (meta.app 명시 또는 frameTags 존재 또는 모르면 시도)
    if "aseprite" in app or isinstance(meta.get("frameTags"), list):
        return _parse_aseprite(frames_field, meta)

    # 3) meta.app 미명시지만 frames 형태가 Aseprite 와 같으면 시도, 실패 시 None
    try:
        atlas = _parse_aseprite(frames_field, meta)
        if atlas and atlas.frames:
            return atlas
    except (KeyError, TypeError, ValueError):
        pass

    return None


def _parse_aseprite(frames_field, meta: dict) -> "AsepriteAtlas | None":
    if isinstance(frames_field, dict):
        ordered_keys = sorted(frames_field.keys(), key=_natural_key)
        frame_items = [(k, frames_field[k]) for k in ordered_keys]
    elif isinstance(frames_field, list):
        frame_items = [(item.get("filename", str(i)), item)
                       for i, item in enumerate(frames_field)]
    else:
        return None

    frames: list[FrameSpec] = []
    for name, item in frame_items:
        f = item.get("frame")
        if not isinstance(f, dict):
            return None
        try:
            frames.append(FrameSpec(
                x=int(f["x"]), y=int(f["y"]),
                w=int(f["w"]), h=int(f["h"]),
                duration_ms=int(item.get("duration", 0) or 0),
                name=str(name),
            ))
        except (KeyError, TypeError, ValueError):
            return None

    if not frames:
        return None

    tags_field = meta.get("frameTags") if isinstance(meta, dict) else None
    tags: list[AnimationSpec] = []
    if isinstance(tags_field, list):
        for t in tags_field:
            if not isinstance(t, dict):
                continue
            try:
                start = int(t["from"])
                end = int(t["to"])
            except (KeyError, TypeError, ValueError):
                continue
            range_durations = [frames[i].duration_ms
                               for i in range(start, min(end + 1, len(frames)))]
            tags.append(AnimationSpec(
                name=str(t.get("name") or "unnamed"),
                start_frame=start,
                end_frame=end,
                fps_hint=_avg_fps_from_durations(range_durations),
                source="json_tag",
            ))

    return AsepriteAtlas(frames=frames, tags=tags)


def _parse_texture_packer(frames_field) -> "TexturePackerAtlas | None":
    if isinstance(frames_field, dict):
        ordered_keys = sorted(frames_field.keys(), key=_natural_key)
        frame_items = [(k, frames_field[k]) for k in ordered_keys]
    elif isinstance(frames_field, list):
        frame_items = [(item.get("filename", str(i)), item)
                       for i, item in enumerate(frames_field)]
    else:
        return None

    frames: list[FrameSpec] = []
    for name, item in frame_items:
        f = item.get("frame")
        if not isinstance(f, dict):
            return None
        try:
            frames.append(FrameSpec(
                x=int(f["x"]), y=int(f["y"]),
                w=int(f["w"]), h=int(f["h"]),
                duration_ms=0,
                name=str(name),
            ))
        except (KeyError, TypeError, ValueError):
            return None

    if not frames:
        return None
    return TexturePackerAtlas(frames=frames)
```

- [ ] **Step 4**: `pytest tests/test_sheet_json_parser.py -v` → 12 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 801 + 12 = 813 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): sheet/json_parser — Aseprite(array/hash) + TexturePacker 자동 감지`.

#### Task 1.2 — `sheet/grid_detect.py` 구현

**Files:**
- Create: `src/gah/core/sheet/grid_detect.py`
- Create: `tests/test_sheet_grid_detect.py`

- [ ] **Step 1: 실패 테스트** (10 케이스) — `tests/test_sheet_grid_detect.py`:

```python
"""M6 — Pillow alpha 채널 격자 추정."""
from __future__ import annotations

from PIL import Image

from gah.core.sheet.grid_detect import grid_detect
from gah.core.sheet.types import GridLayout


def _make_grid(rows: int, cols: int, frame_w: int, frame_h: int,
               gap_w: int = 2, gap_h: int = 2) -> Image.Image:
    """프레임 사이에 투명 행/열 갭을 둔 합성 이미지를 만든다."""
    total_w = cols * frame_w + (cols - 1) * gap_w
    total_h = rows * frame_h + (rows - 1) * gap_h
    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    for r in range(rows):
        for c in range(cols):
            x = c * (frame_w + gap_w)
            y = r * (frame_h + gap_h)
            tile = Image.new("RGBA", (frame_w, frame_h), (200, 100, 50, 255))
            img.paste(tile, (x, y))
    return img


def test_horizontal_8_frames():
    img = _make_grid(rows=1, cols=8, frame_w=32, frame_h=32)
    layout = grid_detect(img)
    assert isinstance(layout, GridLayout)
    assert layout.rows == 1
    assert layout.cols == 8
    assert layout.frame_w == 32
    assert layout.frame_h == 32


def test_vertical_4_frames():
    img = _make_grid(rows=4, cols=1, frame_w=64, frame_h=32)
    layout = grid_detect(img)
    assert layout.rows == 4
    assert layout.cols == 1


def test_no_alpha_returns_none():
    img = Image.new("RGB", (128, 32), (255, 255, 255))
    assert grid_detect(img) is None


def test_nonuniform_gaps_returns_none():
    # 갭이 일관되지 않은 인공 이미지
    img = Image.new("RGBA", (100, 32), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (0, 0))
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (35, 0))  # gap=3
    img.paste(Image.new("RGBA", (32, 32), (200, 100, 50, 255)), (75, 0))  # gap=8
    assert grid_detect(img) is None


def test_single_frame_returns_none():
    img = Image.new("RGBA", (32, 32), (200, 100, 50, 255))
    assert grid_detect(img) is None


def test_2_rows_4_cols():
    img = _make_grid(rows=2, cols=4, frame_w=16, frame_h=16)
    layout = grid_detect(img)
    assert layout.rows == 2
    assert layout.cols == 4
    assert layout.frame_w == 16
    assert layout.frame_h == 16


def test_all_transparent_returns_none():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    assert grid_detect(img) is None


def test_tiny_image_returns_none():
    img = Image.new("RGBA", (8, 8), (200, 100, 50, 255))
    assert grid_detect(img) is None


def test_padded_horizontal_2_frames():
    # 가장 작은 가로 격자
    img = _make_grid(rows=1, cols=2, frame_w=16, frame_h=16)
    layout = grid_detect(img)
    assert layout.rows == 1
    assert layout.cols == 2


def test_boundary_no_gap_works():
    # 갭 0 (프레임이 딱 붙은 경우) — alpha 가 항상 채워져서 검출 불가 → None
    img = Image.new("RGBA", (64, 32), (200, 100, 50, 255))
    assert grid_detect(img) is None
```

- [ ] **Step 2**: `pytest tests/test_sheet_grid_detect.py -v` → 10 FAIL `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `src/gah/core/sheet/grid_detect.py`:

```python
"""M6 — Pillow alpha 채널 행/열 합으로 균일 격자 추정.

알파 합이 0 인 행/열을 "투명 경계" 로 보고, 경계 사이의 간격이 모두
같으면 균일 격자로 판정한다. 알파 없거나 비균일·단일 프레임·작은
이미지는 None. M6 spec §4.8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import GridLayout

if TYPE_CHECKING:
    from PIL.Image import Image

_MIN_DIM = 16  # 작은 이미지는 격자 추정 의미 없음


def grid_detect(img: "Image") -> GridLayout | None:
    import numpy as np

    if img.size[0] < _MIN_DIM or img.size[1] < _MIN_DIM:
        return None
    if img.mode != "RGBA":
        try:
            rgba = img.convert("RGBA")
        except (ValueError, OSError):
            return None
    else:
        rgba = img

    arr = np.asarray(rgba)
    if arr.shape[-1] != 4:
        return None
    alpha = arr[:, :, 3]

    # 알파가 전부 0 또는 전부 양수면 격자 검출 불가
    row_sums = alpha.sum(axis=1)
    col_sums = alpha.sum(axis=0)
    if int(row_sums.max()) == 0 or int(col_sums.max()) == 0:
        return None
    if int(row_sums.min()) > 0 and int(col_sums.min()) > 0:
        return None

    # 행/열 격자 추정
    cols = _split_count_from_axis(col_sums)
    rows = _split_count_from_axis(row_sums)
    if cols < 1 or rows < 1:
        return None
    if rows == 1 and cols == 1:
        return None

    # 프레임 크기 = (전체 - 갭) / 분할 수
    # 갭은 우선 0 가정, 균일 분할이 정수로 떨어지면 사용.
    h, w = arr.shape[:2]
    frame_w = _uniform_frame_size(col_sums, cols)
    frame_h = _uniform_frame_size(row_sums, rows)
    if frame_w is None or frame_h is None:
        return None

    return GridLayout(rows=rows, cols=cols, frame_w=frame_w, frame_h=frame_h)


def _split_count_from_axis(sums) -> int:
    """투명 경계로 분리된 프레임 수를 센다.

    경계 = 합이 0 인 연속 구간. 프레임 = 합이 > 0 인 연속 구간.
    """
    in_frame = False
    count = 0
    for v in sums:
        if int(v) > 0:
            if not in_frame:
                count += 1
                in_frame = True
        else:
            in_frame = False
    return count


def _uniform_frame_size(sums, count: int) -> int | None:
    """프레임 길이가 모두 같으면 그 길이를, 아니면 None."""
    # 연속된 양수 구간의 길이를 모은다
    lengths: list[int] = []
    current = 0
    for v in sums:
        if int(v) > 0:
            current += 1
        else:
            if current > 0:
                lengths.append(current)
            current = 0
    if current > 0:
        lengths.append(current)
    if len(lengths) != count:
        return None
    if not lengths:
        return None
    first = lengths[0]
    if all(l == first for l in lengths):
        return int(first)
    return None
```

- [ ] **Step 4**: `pytest tests/test_sheet_grid_detect.py -v` → 10 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 813 + 10 = 823 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): sheet/grid_detect — Pillow alpha 행/열 합 격자 추정`.

#### Task 1.3 — `sheet/preview.py` 8칸 합성

**Files:**
- Create: `src/gah/core/sheet/preview.py`
- Create: `tests/test_sheet_preview.py`

- [ ] **Step 1: 실패 테스트** (5 케이스):

```python
"""M6 — 8칸 1행 합성 미리보기."""
from __future__ import annotations

from PIL import Image

from gah.core.sheet.preview import make_preview_composite, sample_indices
from gah.core.sheet.types import FrameSpec


def _sheet_with_frames(frame_count: int, fw: int = 32, fh: int = 32) -> tuple[Image.Image, list[FrameSpec]]:
    img = Image.new("RGBA", (frame_count * fw, fh), (0, 0, 0, 0))
    frames: list[FrameSpec] = []
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh),
                         (((i * 30) % 255), 100, 50, 255))
        img.paste(tile, (i * fw, 0))
        frames.append(FrameSpec(x=i * fw, y=0, w=fw, h=fh,
                                duration_ms=100, name=str(i)))
    return img, frames


def test_8_frames_used_as_is():
    img, frames = _sheet_with_frames(8)
    composite = make_preview_composite(img, frames, max_size=512)
    # 8 × 32 = 256 wide × 32 high
    assert composite.size == (8 * 32, 32)


def test_16_frames_linear_stride():
    indices = sample_indices(16, 8)
    assert indices == [0, 2, 4, 6, 9, 11, 13, 15]


def test_4_frames_used_as_is():
    img, frames = _sheet_with_frames(4)
    composite = make_preview_composite(img, frames, max_size=512)
    assert composite.size == (4 * 32, 32)


def test_composite_respects_max_size():
    # 32 프레임 × 512px 가로폭 = 너무 큼 → max=200 으로 축소
    img, frames = _sheet_with_frames(32, fw=64, fh=64)
    composite = make_preview_composite(img, frames, max_size=200)
    assert max(composite.size) <= 200


def test_rgba_preserved():
    img, frames = _sheet_with_frames(8)
    composite = make_preview_composite(img, frames, max_size=512)
    assert composite.mode in ("RGBA", "RGB")
```

- [ ] **Step 2**: `pytest tests/test_sheet_preview.py -v` → 5 FAIL.

- [ ] **Step 3: 구현** — `src/gah/core/sheet/preview.py`:

```python
"""M6 — 8칸 1행 합성 미리보기.

≤8 프레임은 그대로, >8 은 선형 stride 샘플링 8개로 합성. max_size 로
긴 변 다운스케일. M6 spec §4.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image
    from .types import FrameSpec

_PREVIEW_FRAME_COUNT = 8


def sample_indices(total: int, k: int = _PREVIEW_FRAME_COUNT) -> list[int]:
    """0..total-1 에서 균등 간격 k 개 인덱스.

    total ≤ k 이면 0..total-1 모두 반환. 그렇지 않으면 선형 stride
    `round(i * (total - 1) / (k - 1))` 로 k 개 선택.
    """
    if total <= 0 or k <= 0:
        return []
    if total <= k:
        return list(range(total))
    return [round(i * (total - 1) / (k - 1)) for i in range(k)]


def make_preview_composite(
    img: "Image",
    frames: "list[FrameSpec]",
    *,
    max_size: int = 768,
) -> "Image":
    """frames 의 일부(또는 전부) 를 가로 1행으로 합성한 미리보기."""
    from PIL import Image as _PILImage

    if not frames:
        return img.copy()

    idxs = sample_indices(len(frames), _PREVIEW_FRAME_COUNT)
    selected = [frames[i] for i in idxs]
    # 모든 프레임 크기가 같다고 가정 (시트의 정의에 가까움). 다르면 첫 프레임 기준 리사이즈.
    fw, fh = selected[0].w, selected[0].h
    total_w = fw * len(selected)
    composite = _PILImage.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    rgba = img.convert("RGBA") if img.mode != "RGBA" else img
    for i, f in enumerate(selected):
        tile = rgba.crop((f.x, f.y, f.x + f.w, f.y + f.h))
        if tile.size != (fw, fh):
            tile = tile.resize((fw, fh), _PILImage.LANCZOS)
        composite.paste(tile, (i * fw, 0))

    # max_size 다운스케일
    if max(composite.size) > max_size:
        scale = max_size / max(composite.size)
        new_size = (max(1, int(composite.size[0] * scale)),
                    max(1, int(composite.size[1] * scale)))
        composite = composite.resize(new_size, _PILImage.LANCZOS)
    return composite
```

- [ ] **Step 4**: `pytest tests/test_sheet_preview.py -v` → 5 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 823 + 5 = 828 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): sheet/preview — 8칸 1행 합성 + 선형 stride 샘플링`.

#### Task 1.4 — `sheet/detect.py` 오케스트레이션

**Files:**
- Create: `src/gah/core/sheet/detect.py`
- Create: `tests/test_sheet_detect.py`

- [ ] **Step 1: 실패 테스트** (6 케이스):

```python
"""M6 — sheet detection 오케스트레이션 (JSON 사이드카 → grid → None)."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from gah.core.sheet.detect import SheetDetection, detect_sheet

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def _save_sheet_png(path: Path, frame_count: int, fw: int = 32, fh: int = 32,
                    gap: int = 2) -> None:
    total_w = frame_count * fw + (frame_count - 1) * gap
    img = Image.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh), (200, 100, 50, 255))
        img.paste(tile, (i * (fw + gap), 0))
    img.save(path)


def test_json_sidecar_preferred(tmp_path):
    # PNG + JSON 모두 있으면 JSON 사용 (frames 가 JSON 기준)
    png = tmp_path / "hero_walk_aseprite_array.png"
    json_src = FIXTURES / "hero_walk_aseprite_array.json"
    _save_sheet_png(png, frame_count=8)
    shutil.copy(json_src, tmp_path / "hero_walk_aseprite_array.json")

    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "json"
    assert len(detection.frames) == 8
    assert len(detection.tags) == 1


def test_grid_fallback_when_no_json(tmp_path):
    png = tmp_path / "slime.png"
    _save_sheet_png(png, frame_count=4)
    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "grid"
    assert len(detection.frames) == 4
    assert detection.tags == []


def test_returns_none_when_no_json_and_no_grid(tmp_path):
    # 단일 프레임 — JSON 없음, grid 검출 불가
    png = tmp_path / "sword.png"
    Image.new("RGBA", (32, 32), (200, 100, 50, 255)).save(png)
    assert detect_sheet(png) is None


def test_sidecar_path_naming(tmp_path):
    # png 와 같은 이름의 .json
    png = tmp_path / "abc.png"
    json_path = tmp_path / "abc.json"
    _save_sheet_png(png, frame_count=8)
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json", json_path)
    detection = detect_sheet(png)
    assert detection is not None
    assert detection.source == "json"


def test_invalid_image_returns_none(tmp_path):
    # PNG 아닌 파일 — Pillow open 실패
    p = tmp_path / "junk.bin"
    p.write_bytes(b"not a real image")
    assert detect_sheet(p) is None


def test_sheet_detection_dataclass_fields():
    sd = SheetDetection(frames=[], tags=[], source="grid")
    assert sd.frames == []
    assert sd.tags == []
    assert sd.source == "grid"
```

- [ ] **Step 2**: `pytest tests/test_sheet_detect.py -v` → 6 FAIL.

- [ ] **Step 3: 구현** — `src/gah/core/sheet/detect.py`:

```python
"""M6 — sheet 검출 오케스트레이션.

3단계: <basename>.json → grid_detect → None.
M6 spec §4.2 / §4.8 / §4.9.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .grid_detect import grid_detect
from .json_parser import parse as parse_json
from .types import AnimationSpec, AsepriteAtlas, FrameSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SheetDetection:
    frames: list[FrameSpec]
    tags: list[AnimationSpec]
    source: str  # 'json' | 'grid'


def detect_sheet(image_path: Path) -> "SheetDetection | None":
    image_path = Path(image_path)
    json_path = image_path.with_suffix(".json")

    # 1) JSON 사이드카
    if json_path.exists():
        atlas = parse_json(json_path)
        if atlas is not None and atlas.frames:
            tags = atlas.tags if isinstance(atlas, AsepriteAtlas) else []
            return SheetDetection(frames=list(atlas.frames),
                                  tags=list(tags),
                                  source="json")

    # 2) Pillow alpha 격자 추정
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(image_path) as img:
            img.load()
            layout = grid_detect(img)
    except (OSError, ValueError) as e:
        log.warning("sheet open failed: %s — %s", image_path, e)
        return None

    if layout is None:
        return None

    # GridLayout 을 FrameSpec 시퀀스로 풀어쓴다 (균일 간격 가정)
    # 갭 = (전체 - rows*frame_h) / (rows-1). 단순화: PNG 의 frame 위치는 grid 분할 후 stride 검사로 보정.
    # v1 단순화: 갭 0 가정한 인덱스, 큐 워크플로에선 시트 단위 메타만 쓰므로 미세 위치 오차 무관.
    frames: list[FrameSpec] = []
    # 균일 stride 추정: 갭 포함 stride = ceil(total / count)
    with _PILImage.open(image_path) as img:
        total_w, total_h = img.size
    stride_x = total_w // layout.cols if layout.cols > 0 else layout.frame_w
    stride_y = total_h // layout.rows if layout.rows > 0 else layout.frame_h
    idx = 0
    for r in range(layout.rows):
        for c in range(layout.cols):
            frames.append(FrameSpec(
                x=c * stride_x, y=r * stride_y,
                w=layout.frame_w, h=layout.frame_h,
                duration_ms=0, name=str(idx),
            ))
            idx += 1
    return SheetDetection(frames=frames, tags=[], source="grid")
```

- [ ] **Step 4**: `pytest tests/test_sheet_detect.py -v` → 6 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 828 + 6 = 834 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): sheet/detect — JSON 사이드카 + grid_detect 오케스트레이션`.

---

### 4.2 Phase 2 — SpritesheetAnalyzer + Store 마이그레이션 (~1일)

#### Task 2.1 — Store 마이그레이션 (animations_json 컬럼)

**Files:**
- Modify: `src/gah/core/store.py`
- Create: `tests/test_store_m6.py`

- [ ] **Step 1: 실패 테스트** (8 케이스) — `tests/test_store_m6.py`:

```python
"""M6 — Store animations_json 컬럼 + get_sprite_meta + update_asset_kind."""
from __future__ import annotations

import json

import pytest

from gah.core.store import SpriteMeta, Store


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    yield s
    s.close()


def _seed_pack_and_asset(store: Store) -> int:
    pid = store.upsert_pack(name="pack1", path="pack1", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="pack1/hero.png", kind="sprite",
        file_hash="h1", file_size=1024,
    )
    return aid


def test_animations_json_column_exists(store):
    rows = store.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols


def test_save_sprite_meta_round_trip_animations(store):
    aid = _seed_pack_and_asset(store)
    anim = {"walk": {"start_frame": 0, "end_frame": 7,
                     "fps_hint": 12, "source": "json_tag"}}
    meta = SpriteMeta(
        width=256, height=32, has_alpha=True, is_pixel_art=False,
        dominant_colors=["#000000"],
        frame_w=32, frame_h=32, frame_count=8,
        animation_tags=["walk"], animations_json=anim,
    )
    store.save_sprite_meta(aid, meta)
    got = store.get_sprite_meta(aid)
    assert got is not None
    assert got.animations_json == anim
    assert got.frame_count == 8


def test_save_sprite_meta_animations_none(store):
    aid = _seed_pack_and_asset(store)
    meta = SpriteMeta(
        width=32, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=["#000000"],
    )
    store.save_sprite_meta(aid, meta)
    got = store.get_sprite_meta(aid)
    assert got is not None
    assert got.animations_json is None
    assert got.frame_count is None


def test_get_sprite_meta_missing_asset(store):
    assert store.get_sprite_meta(999_999) is None


def test_update_asset_kind(store):
    aid = _seed_pack_and_asset(store)
    store.update_asset_kind(aid, "spritesheet")
    row = store.conn.execute(
        "SELECT kind FROM assets WHERE id = ?", (aid,)
    ).fetchone()
    assert row[0] == "spritesheet"


def test_migration_idempotent(tmp_path):
    # 두 번 initialize 호출해도 OK
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    s.initialize()  # 회귀 0
    rows = s.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols
    s.close()


def test_legacy_db_without_animations_column(tmp_path):
    # 컬럼이 없던 옛 DB 를 시뮬레이션 — initialize() 가 컬럼 추가
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sprite_meta (
        asset_id INTEGER PRIMARY KEY, width INTEGER, height INTEGER,
        has_alpha INTEGER, is_pixel_art INTEGER, dominant_colors TEXT,
        frame_w INTEGER, frame_h INTEGER, frame_count INTEGER,
        animation_tags TEXT
    )""")
    conn.commit()
    conn.close()
    s = Store(db)
    s.initialize()  # ADD COLUMN
    rows = s.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols
    s.close()


def test_animations_json_dict_serialization(store):
    aid = _seed_pack_and_asset(store)
    payload = {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"},
        "idle": {"start_frame": 4, "end_frame": 7, "fps_hint": 8, "source": "gemma_inferred"},
    }
    meta = SpriteMeta(
        width=128, height=32, has_alpha=True, is_pixel_art=False,
        dominant_colors=[],
        frame_w=16, frame_h=32, frame_count=8,
        animation_tags=["walk", "idle"], animations_json=payload,
    )
    store.save_sprite_meta(aid, meta)
    raw = store.conn.execute(
        "SELECT animations_json FROM sprite_meta WHERE asset_id = ?",
        (aid,)
    ).fetchone()[0]
    assert json.loads(raw) == payload
```

- [ ] **Step 2**: `pytest tests/test_store_m6.py -v` → 8 FAIL (`animations_json` 모름, `get_sprite_meta`/`update_asset_kind` 메서드 없음).

- [ ] **Step 3: 구현** — `src/gah/core/store.py`:

(1) `SpriteMeta` 데이터클래스에 필드 추가 (라인 ~56):

```python
@dataclass(frozen=True)
class SpriteMeta:
    width: int
    height: int
    has_alpha: bool
    is_pixel_art: bool
    dominant_colors: list[str]
    frame_w: int | None = None
    frame_h: int | None = None
    frame_count: int | None = None
    animation_tags: list[str] | None = None  # M5 가 채움 → M6 분석기가 채움
    animations_json: dict | None = None  # M6 — {name: {start_frame, end_frame, fps_hint, source}}
```

(2) `Store.initialize()` 의 적절한 위치 (CREATE TABLE 직후, 또는 별도 메서드) 에 idempotent ALTER 호출 추가. 기존 `initialize` 메서드 끝에:

```python
def initialize(self) -> None:
    # ... (기존 CREATE TABLE statements) ...
    self._migrate_m6_animations_json()

def _migrate_m6_animations_json(self) -> None:
    """M6 — sprite_meta.animations_json 컬럼 idempotent 추가."""
    cur = self.conn.execute("PRAGMA table_info(sprite_meta)")
    cols = {r[1] for r in cur.fetchall()}
    if "animations_json" not in cols:
        with self.write_lock:
            self.conn.execute(
                "ALTER TABLE sprite_meta ADD COLUMN animations_json TEXT"
            )
```

(3) `save_sprite_meta` SQL 갱신:

```python
def save_sprite_meta(self, asset_id: int, meta: SpriteMeta) -> None:
    import json

    with self.write_lock:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO sprite_meta (
              asset_id, width, height, has_alpha, is_pixel_art,
              dominant_colors, frame_w, frame_h, frame_count, animation_tags,
              animations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                meta.width,
                meta.height,
                1 if meta.has_alpha else 0,
                1 if meta.is_pixel_art else 0,
                json.dumps(meta.dominant_colors),
                meta.frame_w,
                meta.frame_h,
                meta.frame_count,
                json.dumps(meta.animation_tags) if meta.animation_tags else None,
                json.dumps(meta.animations_json) if meta.animations_json else None,
            ),
        )
```

(4) 신규 헬퍼:

```python
def get_sprite_meta(self, asset_id: int) -> "SpriteMeta | None":
    import json

    row = self.conn.execute(
        """
        SELECT width, height, has_alpha, is_pixel_art, dominant_colors,
               frame_w, frame_h, frame_count, animation_tags, animations_json
          FROM sprite_meta WHERE asset_id = ?
        """,
        (asset_id,),
    ).fetchone()
    if row is None:
        return None
    return SpriteMeta(
        width=int(row[0]), height=int(row[1]),
        has_alpha=bool(row[2]), is_pixel_art=bool(row[3]),
        dominant_colors=json.loads(row[4]) if row[4] else [],
        frame_w=int(row[5]) if row[5] is not None else None,
        frame_h=int(row[6]) if row[6] is not None else None,
        frame_count=int(row[7]) if row[7] is not None else None,
        animation_tags=json.loads(row[8]) if row[8] else None,
        animations_json=json.loads(row[9]) if row[9] else None,
    )


def update_asset_kind(self, asset_id: int, kind: str) -> None:
    """분석기가 sprite → spritesheet 로 promote 할 때 호출."""
    if kind not in ("sprite", "spritesheet", "sound"):
        raise ValueError(f"invalid kind: {kind}")
    with self.write_lock:
        self.conn.execute(
            "UPDATE assets SET kind = ? WHERE id = ?", (kind, asset_id)
        )
```

- [ ] **Step 4**: `pytest tests/test_store_m6.py -v` → 8 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 834 + 8 = 842 passed (M0~M5 회귀 0).

- [ ] **Step 6**: 커밋 — `feat(m6): Store animations_json 컬럼 + get_sprite_meta + update_asset_kind`.

#### Task 2.2 — `SpritesheetAnalyzer` 구현

**Files:**
- Create: `src/gah/core/analyzer/spritesheet.py`
- Modify: `src/gah/core/analyzer/__init__.py`
- Create: `tests/test_analyzer_spritesheet.py`

- [ ] **Step 1: 실패 테스트** (10 케이스) — `tests/test_analyzer_spritesheet.py`:

```python
"""M6 — SpritesheetAnalyzer (시트 감지 + Gemma + 폴백)."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from gah.core.analyzer.base import AnalyzerInput, AnalyzerResult
from gah.core.analyzer.spritesheet import SpritesheetAnalyzer

FIXTURES = Path(__file__).parent / "fixtures" / "sheets"


def _make_sheet_png(path: Path, frame_count: int, fw: int = 32, fh: int = 32, gap: int = 2):
    total_w = frame_count * fw + (frame_count - 1) * gap
    img = Image.new("RGBA", (total_w, fh), (0, 0, 0, 0))
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh), (((i * 30) % 255), 100, 50, 255))
        img.paste(tile, (i * (fw + gap), 0))
    img.save(path)


def _make_single_png(path: Path):
    Image.new("RGBA", (32, 32), (200, 100, 50, 255)).save(path)


@pytest.fixture()
def sprite_mock():
    """SpriteAnalyzer mock — analyze() 가 dummy AnalyzerResult 반환."""
    from gah.core.store import SpriteMeta
    from gah.core.searchable import SearchableTexts
    sa = MagicMock()
    sa.analyze.return_value = AnalyzerResult(
        kind="sprite", state="ok", error=None,
        sprite_meta=SpriteMeta(width=32, height=32, has_alpha=True,
                              is_pixel_art=True, dominant_colors=["#000000"]),
        sound_meta=None,
        labels=[],
        searchable=SearchableTexts(for_fts="x", for_embed="x"),
        embedding_vector=b"\0" * 4, embedding_dim=1,
        embedding_model="test",
        description="",
    )
    return sa


@pytest.fixture()
def ollama_mock():
    """OllamaClient mock — animation_hint=['walk'] 응답."""
    o = MagicMock()
    o.chat.return_value = {
        "description": "hero walking", "subject": "hero",
        "category": "character", "style": "pixel_art",
        "mood": ["energetic"], "palette": ["warm"],
        "animation_hint": ["walk"], "confidence": 0.8,
    }
    return o


@pytest.fixture()
def registry_mock():
    r = MagicMock()
    r.list_labels.return_value = ["walk", "idle", "run", "attack", "hurt",
                                  "death", "cast", "crouch", "jump", "other"]
    return r


@pytest.fixture()
def embedder_mock():
    e = MagicMock()
    e.model = "test-embed"
    e.encode_text.return_value = (b"\0\0\0\0", 1)
    return e


def test_aseprite_json_sidecar_promotes_to_spritesheet(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "hero_walk_aseprite_array.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "hero_walk_aseprite_array.json")
    _make_sheet_png(png, frame_count=8)

    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=1, pack_id=1,
                       abs_path=png, rel_path="x/hero_walk.png")
    result = analyzer.analyze(inp)

    assert result.kind == "spritesheet"
    assert result.sprite_meta is not None
    assert result.sprite_meta.frame_count == 8
    assert result.sprite_meta.frame_w == 32
    assert result.sprite_meta.frame_h == 32
    assert "walk" in (result.sprite_meta.animations_json or {})
    walk = result.sprite_meta.animations_json["walk"]
    assert walk["start_frame"] == 0
    assert walk["end_frame"] == 7
    assert walk["source"] == "json_tag"


def test_grid_only_uses_full_sheet_range(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "slime.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=2, pack_id=1, abs_path=png, rel_path="x/slime.png")
    result = analyzer.analyze(inp)

    assert result.kind == "spritesheet"
    assert result.sprite_meta.frame_count == 4
    anim = result.sprite_meta.animations_json
    assert "walk" in anim
    assert anim["walk"]["start_frame"] == 0
    assert anim["walk"]["end_frame"] == 3
    assert anim["walk"]["source"] == "gemma_inferred"


def test_single_image_falls_back_to_sprite(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "sword.png"
    _make_single_png(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=3, pack_id=1, abs_path=png, rel_path="x/sword.png")
    result = analyzer.analyze(inp)

    assert result.kind == "sprite"
    # SpriteAnalyzer mock 이 호출됐는지
    sprite_mock.analyze.assert_called_once()


def test_animation_tags_backward_compat(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "x_aseprite.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x_aseprite.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=4, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert "walk" in (result.sprite_meta.animation_tags or [])


def test_gemma_failure_partial_state(tmp_path, sprite_mock, registry_mock, embedder_mock):
    from gah.core.ollama_client import OllamaError
    bad_ollama = MagicMock()
    bad_ollama.chat.side_effect = OllamaError("timeout")
    png = tmp_path / "x.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=bad_ollama,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=5, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    # frame 정보는 JSON 으로부터 채워졌으나 state=partial
    assert result.kind == "spritesheet"
    assert result.sprite_meta.frame_count == 8
    assert result.state == "partial"
    # frameTags 가 있으므로 animations_json 에 walk 가 들어 있어야 함
    assert "walk" in (result.sprite_meta.animations_json or {})


def test_aseprite_tags_take_priority_over_gemma(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    # Gemma 가 "run" 을 추측해도, JSON frameTags 의 "walk" 가 우선
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": ["run"], "confidence": 0.5,
    }
    png = tmp_path / "x.png"
    shutil.copy(FIXTURES / "hero_walk_aseprite_array.json",
                tmp_path / "x.json")
    _make_sheet_png(png, frame_count=8)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=6, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    anim = result.sprite_meta.animations_json
    assert "walk" in anim
    assert anim["walk"]["source"] == "json_tag"
    # run 도 추가됐을 수 있지만 우선순위 walk
    if "run" in anim:
        assert anim["run"]["source"] == "gemma_inferred"


def test_multi_label_gemma_full_sheet_range(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    # JSON 없음 → grid detect → Gemma 가 walk + idle 두 라벨 → 둘 다 시트 전체 범위
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": ["walk", "idle"], "confidence": 0.6,
    }
    png = tmp_path / "x.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=7, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    anim = result.sprite_meta.animations_json
    assert "walk" in anim and "idle" in anim
    assert anim["walk"]["end_frame"] == 3
    assert anim["idle"]["end_frame"] == 3


def test_non_rgba_png_handled(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    # RGB (알파 없음) — grid_detect None → SpriteAnalyzer 폴백
    png = tmp_path / "rgb.png"
    Image.new("RGB", (128, 32), (100, 100, 100)).save(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=8, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert result.kind == "sprite"
    sprite_mock.analyze.assert_called_once()


def test_detection_grid_no_animation_hint(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    # Gemma 가 animation_hint 미반환 → animations_json 은 빈 dict
    ollama_mock.chat.return_value = {
        "description": "x", "subject": "x",
        "category": "character", "style": "pixel_art",
        "mood": [], "palette": [],
        "animation_hint": [], "confidence": 0.7,
    }
    png = tmp_path / "x.png"
    _make_sheet_png(png, frame_count=4)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=9, pack_id=1, abs_path=png, rel_path="x.png")
    result = analyzer.analyze(inp)
    assert result.kind == "spritesheet"
    assert result.sprite_meta.animations_json == {}


def test_analyzer_input_propagated_to_sprite_fallback(tmp_path, sprite_mock, ollama_mock, registry_mock, embedder_mock):
    png = tmp_path / "single.png"
    _make_single_png(png)
    analyzer = SpritesheetAnalyzer(
        sprite=sprite_mock, ollama=ollama_mock,
        registry=registry_mock, embedder=embedder_mock, clip=None,
    )
    inp = AnalyzerInput(asset_id=42, pack_id=1, abs_path=png, rel_path="single.png")
    analyzer.analyze(inp)
    call_args = sprite_mock.analyze.call_args
    assert call_args[0][0].asset_id == 42
    assert call_args[0][0].abs_path == png
```

- [ ] **Step 2**: `pytest tests/test_analyzer_spritesheet.py -v` → 10 FAIL.

- [ ] **Step 3: 구현** — `src/gah/core/analyzer/spritesheet.py`:

```python
"""M6 — SpritesheetAnalyzer.

sheet.detect 가 성공하면 spritesheet 으로 promote 하고 8칸 합성을
Gemma 에 보내 animation_hint 를 받는다. 실패 시 일반 SpriteAnalyzer 로
위임. M6 spec §4.4.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

from ..ollama_client import ChatMessage, OllamaError
from ..searchable import build_searchable
from ..sheet.detect import detect_sheet
from ..sheet.preview import make_preview_composite
from ..store import LabelScore, SpriteMeta
from .base import AnalyzerInput, AnalyzerResult

if TYPE_CHECKING:
    from ..embedding import EmbeddingEncoder
    from ..labels import LabelRegistry
    from ..ollama_client import OllamaClient
    from .sprite import SpriteAnalyzer

log = logging.getLogger(__name__)

_PREVIEW_MAX = 768


class SpritesheetAnalyzer:
    def __init__(
        self,
        *,
        sprite: "SpriteAnalyzer",
        ollama: "OllamaClient",
        registry: "LabelRegistry",
        embedder: "EmbeddingEncoder",
        clip=None,
    ) -> None:
        self.sprite = sprite
        self.ollama = ollama
        self.registry = registry
        self.embedder = embedder
        self.clip = clip

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        detection = detect_sheet(inp.abs_path)
        if detection is None:
            # 폴백 — 일반 SpriteAnalyzer
            return self.sprite.analyze(inp)

        from PIL import Image as _PILImage

        try:
            with _PILImage.open(inp.abs_path) as src:
                src.load()
                composite = make_preview_composite(
                    src, list(detection.frames), max_size=_PREVIEW_MAX
                )
        except (OSError, ValueError):
            log.exception("preview composite failed: %s", inp.abs_path)
            return self.sprite.analyze(inp)

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        gemma_payload, state, error = self._call_gemma(
            img_b64=img_b64, language=inp.language,
        )

        # frame_w/h 추정 — 첫 프레임 박스 사용
        first = detection.frames[0]
        frame_w, frame_h = first.w, first.h

        # animations_json 조립: JSON frameTags 우선, Gemma 추론 라벨은 시트 전체 범위
        animations_json: dict = {}
        for tag in detection.tags:
            animations_json[tag.name] = {
                "start_frame": tag.start_frame,
                "end_frame": tag.end_frame,
                "fps_hint": tag.fps_hint,
                "source": tag.source,
            }
        hints = gemma_payload.get("animation_hint") or []
        for label in hints:
            if not isinstance(label, str) or not label:
                continue
            if label in animations_json:
                continue  # frameTags 가 이미 정의 — 우선
            animations_json[label] = {
                "start_frame": 0,
                "end_frame": len(detection.frames) - 1,
                "fps_hint": 12,
                "source": "gemma_inferred",
            }

        animation_tags = list(animations_json.keys())  # backward compat

        # 기본 sprite meta 측정 (단일 합성 미리보기 기준이 아니라 원본 이미지)
        try:
            import numpy as np
            from PIL import Image as _PIL
            with _PIL.open(inp.abs_path) as orig:
                rgba = orig.convert("RGBA")
                w, h = rgba.size
                arr = np.asarray(rgba)
                has_alpha = bool((arr[:, :, 3] < 255).any())
        except (OSError, ValueError):
            w, h, has_alpha = composite.size[0], composite.size[1], True
            arr = None

        sprite_meta = SpriteMeta(
            width=w, height=h,
            has_alpha=has_alpha, is_pixel_art=True,  # 시트는 보통 픽셀 아트 — 단순화
            dominant_colors=[],
            frame_w=frame_w, frame_h=frame_h, frame_count=len(detection.frames),
            animation_tags=animation_tags if animation_tags else None,
            animations_json=animations_json,
        )

        labels: list[LabelScore] = []
        for label in hints:
            if isinstance(label, str) and label:
                labels.append(LabelScore(
                    axis="animation", label=label,
                    score=float(gemma_payload.get("confidence") or 0.5),
                    source="gemma", weight="primary",
                ))

        searchable = build_searchable(
            meta=sprite_meta, labels=labels, label_descriptions={},
            description=gemma_payload.get("description", "") or "",
            rel_path=inp.rel_path,
        )

        try:
            blob, dim = self.embedder.encode_text(searchable.for_embed)
        except OllamaError:
            blob, dim = b"", 0
            if state == "ok":
                state = "partial"

        return AnalyzerResult(
            kind="spritesheet", state=state, error=error,
            sprite_meta=sprite_meta, sound_meta=None,
            labels=labels, searchable=searchable,
            embedding_vector=blob, embedding_dim=dim,
            embedding_model=self.embedder.model,
            description=gemma_payload.get("description", "") or "",
        )

    def _call_gemma(
        self, *, img_b64: str, language: str,
    ) -> tuple[dict, str, str | None]:
        anim_enum = ", ".join(self.registry.list_labels("animation"))
        system = (
            "You are a game animation labeler. Respond ONLY with valid JSON.\n\n"
            "Input is a horizontal strip of sprite frames.\n"
            "Schema:\n"
            f"- animation_hint: array (1..4) from [{anim_enum}]\n"
            "- description: one sentence in {lang}\n"
            "- subject: short noun phrase in {lang}\n"
            "- category: 'character'\n"
            "- style: 'pixel_art'\n"
            "- mood: []\n"
            "- palette: []\n"
            "- confidence: float 0..1\n"
        ).replace("{lang}", language)
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content="Identify the animation in this strip.",
                       images_b64=[img_b64]),
        ]
        try:
            payload = self.ollama.chat(messages, force_json=True, num_ctx=4000)
            return payload, "ok", None
        except OllamaError as e:
            return ({"animation_hint": [], "description": "",
                    "subject": "", "category": "other",
                    "style": "other", "mood": [], "palette": [],
                    "confidence": 0.0}, "partial", f"ollama: {e}")
```

(2) `src/gah/core/analyzer/__init__.py` 에 export:

```python
from .sound import SoundAnalyzer
from .sprite import SpriteAnalyzer
from .spritesheet import SpritesheetAnalyzer

__all__ = ["SoundAnalyzer", "SpriteAnalyzer", "SpritesheetAnalyzer"]
```

- [ ] **Step 4**: `pytest tests/test_analyzer_spritesheet.py -v` → 10 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 842 + 10 = 852 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): SpritesheetAnalyzer — JSON 사이드카 + grid + Gemma animation_hint`.

#### Task 2.3 — `AnalysisQueue` 라우팅 + `app.py` 의존성 주입

**Files:**
- Modify: `src/gah/core/analysis_queue.py`
- Modify: `src/gah/app.py`

- [ ] **Step 1: 회귀 테스트 확인** — 기존 `test_analysis_queue*.py` 가 변경 후에도 통과해야 함. Spritesheet 분기 추가 후 `pytest tests/test_analysis_queue*.py -q` → 기존 케이스 0 회귀.

- [ ] **Step 2: AnalysisQueue 수정**:

(1) `__init__` 시그니처에 `spritesheet` 추가:

```python
def __init__(
    self,
    store: "Store",
    *,
    sprite: "SpriteAnalyzer",
    spritesheet: "SpritesheetAnalyzer",  # M6 신규
    sound: "SoundAnalyzer",
    concurrency: int = 1,
    eta_window: int = 10,
    clock: Callable[[], float] = time.monotonic,
    library_root: Path | None = None,
) -> None:
    super().__init__()
    self.store = store
    self.sprite = sprite
    self.spritesheet = spritesheet  # M6
    self.sound = sound
    # ... (기존 그대로)
```

(2) `_analyze_one` 의 분기 갱신 (라인 ~244):

```python
analyzer = (
    self.spritesheet if row.kind == "sprite"
    else self.sound
)
result = analyzer.analyze(inp)
```

(3) `_persist` 가 promote 처리:

```python
def _persist(self, asset_id: int, result) -> None:
    if result.sprite_meta is not None:
        self.store.save_sprite_meta(asset_id, result.sprite_meta)
    if result.sound_meta is not None:
        self.store.save_sound_meta(asset_id, result.sound_meta)
    self.store.save_asset_labels(asset_id, result.labels)
    if result.embedding_dim > 0:
        self.store.save_embedding(
            asset_id, result.embedding_model,
            result.embedding_vector, result.embedding_dim,
        )
    self.store.update_fts(asset_id, result.searchable.for_fts)
    # M6 — analyzer 가 sprite → spritesheet 로 promote 했으면 assets.kind UPDATE
    if result.kind == "spritesheet":
        self.store.update_asset_kind(asset_id, "spritesheet")
    self.store.mark_asset_state(
        asset_id, result.state, error=result.error,
        analyzed_at=int(time.time()),
    )
```

- [ ] **Step 3: app.py 수정** — `run_tray` 의 분석기 인스턴스화 위치 (M5 의 app.py 검색해서 sprite 분석기 생성하는 자리에 추가):

```python
from gah.core.analyzer.sprite import SpriteAnalyzer
from gah.core.analyzer.spritesheet import SpritesheetAnalyzer  # M6

sprite_analyzer = SpriteAnalyzer(
    ollama=ollama_image, clip=clip, embedder=embedder, registry=registry,
)
spritesheet_analyzer = SpritesheetAnalyzer(  # M6
    sprite=sprite_analyzer, ollama=ollama_image,
    registry=registry, embedder=embedder, clip=clip,
)
queue = AnalysisQueue(
    store, sprite=sprite_analyzer,
    spritesheet=spritesheet_analyzer,  # M6
    sound=sound_analyzer,
    concurrency=cfg.analysis_concurrency,
    library_root=paths.library_dir,
)
```

- [ ] **Step 4: 회귀** — `pytest -q` → 852 passed (회귀 0). 기존 `test_analysis_queue*.py` 에 `spritesheet=` 인자 누락으로 실패하면 mock 추가 후 다시.

- [ ] **Step 5: 기존 큐 테스트 수정** — fixture 에 `spritesheet=` 추가 필수. `tests/test_analysis_queue*.py` 의 모든 `AnalysisQueue(...)` 생성 호출에 `spritesheet=spritesheet_mock` 추가 (mock 은 sprite_mock 과 동일 패턴):

```python
@pytest.fixture
def spritesheet_mock(sprite_mock):
    from unittest.mock import MagicMock
    s = MagicMock()
    # 기본 동작: detection 실패 케이스 → SpriteAnalyzer 위임
    s.analyze.side_effect = lambda inp: sprite_mock.analyze(inp)
    return s
```

→ `pytest tests/test_analysis_queue*.py -q` 통과 확인.

- [ ] **Step 6**: 회귀 — `pytest -q` → 852 passed (기존 통과 유지).

- [ ] **Step 7**: 커밋 — `feat(m6): AnalysisQueue + app.py 가 SpritesheetAnalyzer 라우팅 + kind promote`.

---

### 4.3 Phase 3 — MCP 도구 18번째 `suggest_animation_frames` (~1일)

#### Task 3.1 — `mcp/models.py` Pydantic 모델

**Files:**
- Modify: `src/gah/mcp/models.py`

- [ ] **Step 1**: 기존 모델 패턴 확인 — `RecordAssetUseRequest` 같은 dataclass/Pydantic 시그니처.

- [ ] **Step 2: 구현** — `src/gah/mcp/models.py` 끝에 추가:

```python
# ── M6 — Sheet animation frames ──────────────────────────────────────


class SuggestAnimationFramesRequest(BaseModel):
    asset_id: int = Field(ge=1)
    animation: str = Field(min_length=1, max_length=64)


class SuggestAnimationFramesResult(BaseModel):
    frame_indices: list[int]
    fps_hint: int
```

(BaseModel/Field 가 이미 import 돼 있는지 확인 — M5 에서 다른 신규 모델이 이미 import 함.)

- [ ] **Step 3**: import smoke — `python -c "from gah.mcp.models import SuggestAnimationFramesRequest; print('ok')"` → `ok`.

- [ ] **Step 4**: 회귀 — `pytest -q` → 852 passed.

- [ ] **Step 5**: 커밋 — `feat(m6): mcp models SuggestAnimationFrames{Request,Result}`.

#### Task 3.2 — `tool_suggest_animation_frames` 구현

**Files:**
- Modify: `src/gah/mcp/tools.py`
- Create: `tests/test_mcp_tools_m6.py`

- [ ] **Step 1: 실패 테스트** (12 케이스) — `tests/test_mcp_tools_m6.py`:

```python
"""M6 — tool_suggest_animation_frames."""
from __future__ import annotations

import pytest

from gah.core.store import SpriteMeta, Store
from gah.mcp.models import SuggestAnimationFramesRequest
from gah.mcp.tools import McpToolError, ToolDeps, tool_suggest_animation_frames


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    yield s
    s.close()


@pytest.fixture()
def deps(store):
    from unittest.mock import MagicMock
    return ToolDeps(
        store=store, search=MagicMock(), usage=MagicMock(),
        registry=MagicMock(), queue=None, config=MagicMock(),
        paths=None,
    )


def _seed_spritesheet(store: Store, animations: dict) -> int:
    pid = store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="p/x.png", kind="spritesheet",
        file_hash="h", file_size=1024,
    )
    meta = SpriteMeta(
        width=256, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_w=32, frame_h=32, frame_count=8,
        animation_tags=list(animations.keys()),
        animations_json=animations,
    )
    store.save_sprite_meta(aid, meta)
    return aid


def test_aseprite_frame_tag_lookup(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 12, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [0, 1, 2, 3, 4, 5, 6, 7]
    assert res.fps_hint == 12


def test_gemma_inferred_lookup(deps, store):
    aid = _seed_spritesheet(store, {
        "idle": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="idle")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [0, 1, 2, 3]


def test_asset_not_found(deps):
    req = SuggestAnimationFramesRequest(asset_id=999, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_kind_sprite_400(deps, store):
    pid = store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="p/sword.png", kind="sprite",
        file_hash="h", file_size=64,
    )
    # sprite_meta 없거나 있어도 kind=sprite 면 400
    store.save_sprite_meta(aid, SpriteMeta(
        width=32, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
    ))
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "400_invalid_input"
    assert "spritesheet" in exc_info.value.message.lower()


def test_kind_sound_400(deps, store):
    pid = store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="p/x.wav", kind="sound",
        file_hash="h", file_size=64,
    )
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "400_invalid_input"


def test_animation_not_in_sheet_404_with_available(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "json_tag"},
        "idle": {"start_frame": 4, "end_frame": 7, "fps_hint": 8, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="attack")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"
    assert "walk" in exc_info.value.message
    assert "idle" in exc_info.value.message


def test_inclusive_range(deps, store):
    # start=2, end=5 → indices [2,3,4,5]
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 2, "end_frame": 5, "fps_hint": 10, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == [2, 3, 4, 5]
    assert res.fps_hint == 10


def test_fps_hint_default_12(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 1, "fps_hint": 12, "source": "gemma_inferred"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.fps_hint == 12


def test_fps_hint_aseprite_average(deps, store):
    aid = _seed_spritesheet(store, {
        "walk": {"start_frame": 0, "end_frame": 7, "fps_hint": 11, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    res = tool_suggest_animation_frames(deps, req)
    assert res.fps_hint == 11


def test_animations_json_null_returns_404(deps, store):
    pid = store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="p/x.png", kind="spritesheet",
        file_hash="h", file_size=64,
    )
    store.save_sprite_meta(aid, SpriteMeta(
        width=128, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_w=32, frame_h=32, frame_count=4,
        animations_json=None,
    ))
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_empty_animations_dict_returns_404(deps, store):
    aid = _seed_spritesheet(store, {})
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="walk")
    with pytest.raises(McpToolError) as exc_info:
        tool_suggest_animation_frames(deps, req)
    assert exc_info.value.code == "404_not_found"


def test_correct_index_sequence_for_long_range(deps, store):
    aid = _seed_spritesheet(store, {
        "run": {"start_frame": 0, "end_frame": 23, "fps_hint": 24, "source": "json_tag"},
    })
    req = SuggestAnimationFramesRequest(asset_id=aid, animation="run")
    res = tool_suggest_animation_frames(deps, req)
    assert res.frame_indices == list(range(24))
    assert res.fps_hint == 24
```

- [ ] **Step 2**: `pytest tests/test_mcp_tools_m6.py -v` → 12 FAIL.

- [ ] **Step 3: 구현** — `src/gah/mcp/tools.py` 끝에 추가:

```python
# ── M6 — suggest_animation_frames ─────────────────────────────────────


def tool_suggest_animation_frames(
    deps: ToolDeps, req: "SuggestAnimationFramesRequest"
) -> "SuggestAnimationFramesResult":
    """asset_id 시트의 animation 라벨에 해당하는 프레임 인덱스 + fps_hint.

    M6 spec §4.5. 에러:
      - 404_not_found: asset_id 없음 / sprite_meta 없음 / animation 없음 / animations_json NULL
      - 400_invalid_input: kind != spritesheet
    """
    from .models import (
        SuggestAnimationFramesRequest,
        SuggestAnimationFramesResult,
    )

    # 자산 존재 확인 + kind 검사
    row = deps.store.conn.execute(
        "SELECT kind FROM assets WHERE id = ?", (req.asset_id,)
    ).fetchone()
    if row is None:
        raise McpToolError(
            "404_not_found", f"asset {req.asset_id} not found"
        )
    kind = str(row[0])
    if kind != "spritesheet":
        raise McpToolError(
            "400_invalid_input",
            f"asset {req.asset_id} is kind={kind}, not a spritesheet",
        )

    meta = deps.store.get_sprite_meta(req.asset_id)
    if meta is None or not meta.animations_json:
        raise McpToolError(
            "404_not_found",
            f"asset {req.asset_id} has no animations recorded",
        )

    anim_dict = meta.animations_json
    if req.animation not in anim_dict:
        available = sorted(anim_dict.keys())
        raise McpToolError(
            "404_not_found",
            f"animation '{req.animation}' not found — available: {available}",
        )

    spec = anim_dict[req.animation]
    start = int(spec.get("start_frame", 0))
    end = int(spec.get("end_frame", start))
    fps = int(spec.get("fps_hint", 12)) or 12
    indices = list(range(start, end + 1))
    return SuggestAnimationFramesResult(frame_indices=indices, fps_hint=fps)
```

(import 추가 — `models.py` 의 신규 클래스 임포트):

```python
from .models import (
    ...
    SuggestAnimationFramesRequest,
    SuggestAnimationFramesResult,
)
```

- [ ] **Step 4**: `pytest tests/test_mcp_tools_m6.py -v` → 12 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 852 + 12 = 864 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): tool_suggest_animation_frames + Pydantic 모델`.

#### Task 3.3 — MCP server 등록 (18번째 도구)

**Files:**
- Modify: `src/gah/mcp/server.py`
- Modify: `tests/test_mcp_integration.py`

- [ ] **Step 1: 실패 테스트 갱신** — `tests/test_mcp_integration.py` 의 `expected` 셋에 `"suggest_animation_frames"` 추가, `len(names) == 17` 을 `== 18` 로:

```python
expected = {
    # M3 12 도구
    "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
    "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
    "list_label_axes", "list_labels", "describe_label",
    # M4 4 신규 도구
    "save_search", "list_saved_searches", "delete_saved_search",
    "run_saved_search",
    # M5 1 신규 도구
    "request_user_pick",
    # M6 1 신규 도구
    "suggest_animation_frames",
}
assert expected <= names and len(names) == 18
```

- [ ] **Step 2**: `pytest -m mcp_integration -v` → 1 FAIL (`len == 17` 조건이 깨짐).

- [ ] **Step 3: 구현** — `src/gah/mcp/server.py` 의 `register_all_tools` 끝에 추가:

```python
# M6 Phase 3: 18번째 도구
@server.tool(description="스프라이트 시트의 애니메이션(walk/idle/...)에 해당하는 frame_indices + fps_hint 를 반환한다 (Unity AnimationClip 직접 사용).")
def suggest_animation_frames(req: m.SuggestAnimationFramesRequest) -> m.SuggestAnimationFramesResult:
    return t.tool_suggest_animation_frames(deps, req)
```

`run_stdio()` 의 로그 라인 갱신 — `tools=17` → `tools=18`:

```python
log.info("MCP stdio server starting; tools=18 instructions_len=%d", len(INSTRUCTIONS))
```

`INSTRUCTIONS` 본문 끝에 시트 사용 흐름 추가:

```python
INSTRUCTIONS = (
    "..."  # 기존 본문
    "\n\n"
    "## 시트 + 애니메이션 (M6)\n"
    "- find_asset 결과 중 kind='spritesheet' 인 자산이 있고 사용자가 "
    "특정 애니메이션(예: walk) 을 요청했다면, suggest_animation_frames(asset_id, animation) "
    "로 프레임 인덱스 + fps_hint 를 받아 Unity AnimationClip 코드를 직접 만들 수 있다.\n"
    "- 사용 가능한 animation 이름은 자산의 animations_json 키. "
    "404_not_found 응답의 메시지에 available 목록이 포함됨.\n"
)
```

- [ ] **Step 4**: `pytest -m mcp_integration -v` → 2/2 passed (실 subprocess 가 18 도구 반환).

- [ ] **Step 5**: 회귀 — `pytest -q` → 864 passed.

- [ ] **Step 6**: 커밋 — `feat(m6): MCP suggest_animation_frames 18번째 도구 등록`.

---

### 4.4 Phase 4 — Web 와이드 카드 `🎞 N frames` 배지 (~0.5일)

#### Task 4.1 — `search.py` `_hydrate_meta` 에 frame_count 노출

**Files:**
- Modify: `src/gah/core/search.py`

- [ ] **Step 1: 실패 테스트** — 기존 검색 테스트 중 spritesheet kind 를 시드하는 케이스가 없음. 신규 검증을 Task 4.3 의 카드 테스트로 흡수 (이중 작성 회피).

- [ ] **Step 2: 구현** — `src/gah/core/search.py` 의 `_hydrate_meta` 메서드에서 `kind == "sound"` 분기 옆에 `spritesheet` 분기 추가:

```python
kind_meta: dict[str, Any] = {}
if k == "sound":
    srow = self.store.conn.execute(
        "SELECT duration_ms, loopable FROM sound_meta WHERE asset_id = ?",
        (int(aid),),
    ).fetchone()
    if srow:
        kind_meta["duration_ms"] = int(srow[0])
        kind_meta["loopable"] = bool(srow[1]) if srow[1] is not None else None
elif k == "spritesheet":  # M6
    srow = self.store.conn.execute(
        "SELECT frame_w, frame_h, frame_count FROM sprite_meta WHERE asset_id = ?",
        (int(aid),),
    ).fetchone()
    if srow:
        kind_meta["frame_w"] = int(srow[0]) if srow[0] is not None else None
        kind_meta["frame_h"] = int(srow[1]) if srow[1] is not None else None
        kind_meta["frame_count"] = int(srow[2]) if srow[2] is not None else None
```

- [ ] **Step 3**: 회귀 — `pytest -q` → 864 passed (회귀 0).

- [ ] **Step 4**: 커밋 — `feat(m6): search._hydrate_meta — spritesheet frame_count 노출`.

#### Task 4.2 — `_row_to_dict` / `_asset_row_to_dict` 에 frame_count 노출

**Files:**
- Modify: `src/gah/web/routers/library.py`

기존 `_row_to_dict` 가 `asdict(row)` 후 `meta` 에서 `width/height/size_kb` 를 top-level 로 flatten 하는 패턴. M6 는 같은 패턴으로 `frame_count` 를 top-level 로 노출.

- [ ] **Step 1: `_row_to_dict` 수정** — `src/gah/web/routers/library.py:84` 직후에 추가:

```python
def _row_to_dict(row: Any) -> dict[str, Any]:
    # ... 기존 코드 ...

    # sprite_meta 에서 width/height 추출 (meta dict 에 있을 수 있음)
    meta = d.get("meta") or {}
    d.setdefault("width", meta.get("width"))
    d.setdefault("height", meta.get("height"))
    d.setdefault("size_kb", meta.get("size_kb"))
    # M6 — spritesheet 의 frame 정보를 top-level 로 flatten
    d.setdefault("frame_count", meta.get("frame_count"))
    d.setdefault("frame_w", meta.get("frame_w"))
    d.setdefault("frame_h", meta.get("frame_h"))

    # matched_labels 는 list[dict] 이지만 asdict 이후 그대로 유지됨
    return d
```

- [ ] **Step 2: `_asset_row_to_dict` 수정** — 디폴트 상태(빈 검색) 의 폴백 직렬화도 `frame_count` 필드를 채워야 일관성. `src/gah/web/routers/library.py:111` 의 함수 끝부분:

```python
def _asset_row_to_dict(row: Any) -> dict[str, Any]:
    from pathlib import Path as _Path

    d: dict[str, Any] = {
        "asset_id": row.id,
        # ... 기존 필드 ...
        "kind": row.kind,
        # M6 — frame_count 는 sprite_meta JOIN 없이 빠르게 처리하지 않으므로 None.
        # 시트 카드는 검색 경로에서만 배지 노출.
        "frame_count": None,
        "frame_w": None,
        "frame_h": None,
    }
    return d
```

- [ ] **Step 3**: 회귀 — `pytest -q` → 864 passed (회귀 0).

- [ ] **Step 4**: 커밋 — `feat(m6): library router _row_to_dict + _asset_row_to_dict — frame_count flatten`.

#### Task 4.3 — 카드 template + CSS 배지

**Files:**
- Modify: `src/gah/web/templates/_card_wide.html`
- Modify: `src/gah/web/templates/_card_list.html`
- Modify: `src/gah/web/static/css/main.css`
- Modify: `src/gah/web/static/css/themes.css`
- Create: `tests/test_web_card_frame_badge.py`

- [ ] **Step 1: 실패 테스트** (5 케이스) — `tests/test_web_card_frame_badge.py`:

```python
"""M6 — 와이드/리스트 카드의 🎞 N frames 배지."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import build_test_app  # 또는 적절한 fixture 헬퍼


def _seed_spritesheet_asset(store) -> int:
    from gah.core.store import SpriteMeta
    pid = store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = store.upsert_asset(
        pack_id=pid, rel_path="p/hero.png", kind="spritesheet",
        file_hash="h", file_size=1024,
    )
    store.save_sprite_meta(aid, SpriteMeta(
        width=256, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_w=32, frame_h=32, frame_count=8,
        animation_tags=["walk"],
        animations_json={"walk": {"start_frame":0,"end_frame":7,"fps_hint":12,"source":"json_tag"}},
    ))
    store.mark_asset_state(aid, "ok", error=None, analyzed_at=1)
    return aid


def test_spritesheet_card_shows_frame_badge(deps_fixture):
    aid = _seed_spritesheet_asset(deps_fixture.store)
    app = build_test_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" in r.text
    assert "8 frames" in r.text or "8 frame" in r.text


def test_sprite_card_no_frame_badge(deps_fixture):
    from gah.core.store import SpriteMeta
    pid = deps_fixture.store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = deps_fixture.store.upsert_asset(
        pack_id=pid, rel_path="p/sword.png", kind="sprite",
        file_hash="h", file_size=64,
    )
    deps_fixture.store.save_sprite_meta(aid, SpriteMeta(
        width=32, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
    ))
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=1)
    app = build_test_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text


def test_sound_card_no_frame_badge(deps_fixture):
    pid = deps_fixture.store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = deps_fixture.store.upsert_asset(
        pack_id=pid, rel_path="p/x.wav", kind="sound",
        file_hash="h", file_size=128,
    )
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=1)
    app = build_test_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text


def test_spritesheet_with_null_frame_count_no_badge(deps_fixture):
    # 시트지만 frame_count 가 NULL 인 비정상 상태 — 배지 미렌더
    from gah.core.store import SpriteMeta
    pid = deps_fixture.store.upsert_pack(name="p", path="p", vendor="kenney")
    aid = deps_fixture.store.upsert_asset(
        pack_id=pid, rel_path="p/x.png", kind="spritesheet",
        file_hash="h", file_size=64,
    )
    deps_fixture.store.save_sprite_meta(aid, SpriteMeta(
        width=128, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=[],
        frame_count=None,
    ))
    deps_fixture.store.mark_asset_state(aid, "ok", error=None, analyzed_at=1)
    app = build_test_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    assert r.status_code == 200
    assert "🎞" not in r.text


def test_frame_badge_aria_label(deps_fixture):
    aid = _seed_spritesheet_asset(deps_fixture.store)
    app = build_test_app(deps_fixture)
    client = TestClient(app)
    r = client.post("/ui/search-results", data={"query": ""})
    # aria-label 또는 title 속성으로 접근성
    assert ("aria-label" in r.text and "8" in r.text) or "title=" in r.text
```

> `deps_fixture` / `build_test_app` 은 M5 Phase 3 cleanup 에서 통합된 `tests/conftest.py` 의 fixture. M5 의 `test_web_pages.py` 와 같은 패턴.

- [ ] **Step 2**: `pytest tests/test_web_card_frame_badge.py -v` → 5 FAIL.

- [ ] **Step 3: 템플릿 갱신** — `src/gah/web/templates/_card_wide.html`:

기존 `<div class="card-meta" x-show="$store.search.cardMeta.pack">` 블록 위에 배지 추가:

```html
<div class="card-meta" x-show="$store.search.cardMeta.pack">
  {{ row.pack_name or "" }}
  {% if row.kind == "sprite" and row.width and row.height %}
    &middot; {{ row.width }}&times;{{ row.height }}
  {% endif %}
  {% if row.kind == "spritesheet" and row.frame_count %}
    &middot;
    <span class="frame-badge"
          aria-label="{{ row.frame_count }} frames"
          title="{{ row.frame_count }} frames">
      🎞 {{ row.frame_count }} frames
    </span>
  {% endif %}
  <span x-show="$store.search.cardMeta.size">
    {% if row.size_kb %} &middot; {{ row.size_kb }}KB{% endif %}
  </span>
</div>
```

- [ ] **Step 4: 리스트 카드** — `src/gah/web/templates/_card_list.html` 에 동일 배지 추가 (해당 메타 영역에).

- [ ] **Step 5: CSS 갱신** — `src/gah/web/static/css/main.css` 에 추가:

```css
/* M6 — frame count badge for spritesheet cards */
.frame-badge {
  display: inline-block;
  padding: 1px 6px;
  background: var(--frame-badge-bg);
  color: var(--frame-badge-fg);
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: 600;
  white-space: nowrap;
}
```

`src/gah/web/static/css/themes.css` 에 light/dark 변수 추가 (기존 `:root` 와 `@media (prefers-color-scheme: dark)` 블록 안에):

```css
:root {
  /* ... 기존 변수들 ... */
  --frame-badge-bg: #e6f0ff;
  --frame-badge-fg: #1d4ed8;
}

@media (prefers-color-scheme: dark) {
  :root {
    /* ... 기존 변수들 ... */
    --frame-badge-bg: #1e3a8a;
    --frame-badge-fg: #bfdbfe;
  }
}
```

- [ ] **Step 6**: `pytest tests/test_web_card_frame_badge.py -v` → 5 passed.

- [ ] **Step 7**: 회귀 — `pytest -q` → 864 + 5 = 869 passed.

- [ ] **Step 8**: 커밋 — `feat(m6): 와이드/리스트 카드 🎞 N frames 배지 + light/dark CSS`.

---

### 4.5 Phase 5 — 문서 마감 + verification (~0.5일)

#### Task 5.1 — DESIGN.md 갱신

**Files:**
- Modify: `DESIGN.md`

- [ ] **Step 1**: §4.2.2 본문에 "M6 완료" 표시 + 실제 구현 결과 반영:

```markdown
#### 4.2.2 스프라이트 시트 (`spritesheets/*.png`) ✅ M6 완료

1. 동명 `.json` 이 있으면 우선 사용 — `core/sheet/json_parser.py` 가 Aseprite Array/Hash + TexturePacker 자동 형식 판별.
2. 없으면 격자 추정 — `core/sheet/grid_detect.py` 가 Pillow alpha 채널 행/열 합으로 균일 격자 검출. 실패 시 일반 `sprite` 로 폴백 (사용자 frame size 입력 GUI 는 M7+ v2).
3. 프레임을 가로 8칸 그리드로 합성 (`core/sheet/preview.py`, 8 이하 그대로, 그 이상 선형 stride 샘플링) → Gemma 4 호출 → `animation_hint` 받음.
4. 결과는 시트 단위 + Aseprite frameTags 가 있으면 frame range 단위로도 `sprite_meta.animations_json` 에 저장.
```

- [ ] **Step 2**: §6.6 본문에 "M6 완료" + 실제 응답 예시:

```markdown
### 6.6 `suggest_animation_frames` ✅ M6 완료

스프라이트 시트의 특정 애니메이션(예: `walk`)에 해당하는 프레임 인덱스 배열 + `fps_hint` 를 돌려준다. Unity의 `AnimationClip` 을 만들 때 직접 쓰일 데이터.

```jsonc
// input
{ "asset_id": 88, "animation": "walk" }

// output (Aseprite frameTags 기반, 평균 duration 90ms 에서 역산)
{ "frame_indices": [0,1,2,3,4,5,6,7], "fps_hint": 11 }
```

에러:
- `404_not_found` — `asset_id` 없음, `sprite_meta` 없음, animation 미존재 (응답 메시지에 available 목록 포함).
- `400_invalid_input` — `kind != "spritesheet"`.
```

- [ ] **Step 3**: §11 Milestone 6 표시 변경 + 완료 메모:

```markdown
### Milestone 6 — 시트 분석 + 애니메이션 (1주) ✅ 완료

- 격자 자동 분할, Aseprite/TexturePacker JSON 지원.
- `suggest_animation_frames` 도구 (17 → 18).
- 와이드/리스트 카드 우상단에 `🎞 N frames` 배지.
- v1 알려진 한계: 알파 없는 시트는 JSON 사이드카 필수, 비균일 atlas v2.
```

- [ ] **Step 4**: 커밋 — `docs(m6): DESIGN.md §4.2.2 + §6.6 + §11 M6 완료 반영`.

#### Task 5.2 — MCP_USAGE_GUIDE.md 갱신

**Files:**
- Modify: `docs/MCP_USAGE_GUIDE.md`

- [ ] **Step 1**: 18번째 도구 절 추가:

```markdown
### 6.13 `suggest_animation_frames` (M6 신규)

스프라이트 시트 자산의 애니메이션 → 프레임 인덱스 매핑.

```jsonc
// input
{ "asset_id": 88, "animation": "walk" }

// output
{ "frame_indices": [0,1,2,3,4,5,6,7], "fps_hint": 11 }
```

사용 예시 (Claude Code 가 Unity AnimationClip 생성):

```csharp
// Unity Editor 스크립트
var clip = new AnimationClip { frameRate = 11 };
// frame_indices = [0,1,2,3,4,5,6,7]
// sprite_w=32, sprite_h=32 → 각 프레임의 Rect 계산
```

에러 — §6.6 참고.
```

- [ ] **Step 2**: 도구 카운트 갱신 — 본문에 "17 도구" 가 있으면 "18 도구" 로 일괄.

- [ ] **Step 3**: 커밋 — `docs(m6): MCP_USAGE_GUIDE 18번째 도구 + Unity AnimationClip 예시`.

#### Task 5.3 — M6_verification.md 작성

**Files:**
- Create: `milestones/M6_verification.md`

- [ ] **Step 1**: M5_verification 의 형식을 따라 작성:

```markdown
# M6 검증 보고서

**최종 상태**: ✅ 자동 검증 모두 통과 (YYYY-MM-DD). 사용자 수동 확인 항목 ~6 단계 — §4 에 단계별 체크리스트.

M5 의 17 MCP 도구 + 웹 UI 위에 **시트 자동 분할 (Aseprite/TexturePacker JSON + Pillow alpha 격자) + Gemma 애니메이션 라벨링 + `suggest_animation_frames` 18번째 MCP 도구 + 와이드/리스트 카드 🎞 N frames 배지** 추가.

## 1. 자동 검증 결과: ✅ N/N + 2/2 mcp_integration

`pytest -q` 전체 — M0~M5 회귀 (796) + M6 신규 (~73) = **869 active**.

(Phase 별 신규 카운트 표 — verification 시점에 확정)

`pytest -m mcp_integration -v` — `tools/list` 응답 17 → **18** 도구.

## 2. 자동 검증 한계

- **실 시트 PNG + Aseprite JSON 인테이크** — fixture JSON 으로 단위 검증만. 실 Aseprite export 입력은 §4 수동 검증.
- **Gemma 응답 품질** — animation_hint 정확도는 모델 의존, 자동 검증 불가.

## 3. 의도적으로 미룬 항목 (M7+ v2)

§spec §8 동일.

## 4. 사용자 수동 시각 검증 항목 (~6 단계)

1. 실 Aseprite 시트 + JSON 드롭 → 카드에 `🎞 N frames` 배지 노출.
2. JSON 없는 균일 시트 드롭 → grid 검출 → 카드 배지 노출.
3. 단일 스프라이트 드롭 → 배지 미노출 (sprite 유지).
4. Claude `suggest_animation_frames` 호출 → frame_indices + fps_hint 응답.
5. 존재 안 하는 animation → 404 메시지에 available 목록.
6. 다크 모드 / 라이트 모드 배지 색 정상.
```

- [ ] **Step 2**: 커밋 — `docs(m6): M6_verification 작성`.

#### Task 5.4 — CLAUDE.md / HANDOFF.md 갱신

**Files:**
- Modify: `CLAUDE.md`
- Modify: `HANDOFF.md`

- [ ] **Step 1**: CLAUDE.md §2 진행 현황 표 — M6 행 (`대기 → ✅ 완료`). §8 다음 작업 — M7 (Unity Asset Store) 로 갱신.

- [ ] **Step 2**: HANDOFF.md — M6 완료 인계 (자동 테스트 카운트 + 4 시나리오 + 다음 작업 M7).

- [ ] **Step 3**: 커밋 — `docs(m6): CLAUDE.md + HANDOFF.md M6 완료 표시 + 다음 작업 M7`.

---

## 5. 회귀 + 인계 (M6 종료)

| 단계 | 명령 | 기대 결과 |
|---|---|---|
| 1 | `git status` | `On branch feat/m6-sheet-animation` clean |
| 2 | `pytest -q` | `869 passed, 1 skipped, 4 deselected` (대략) |
| 3 | `pytest -m mcp_integration -v` | 2/2 passed (18 도구 확인) |
| 4 | `git log --oneline -20` | M6 phase 별 커밋 ~15 개 + spec 1 + plan 1 |
| 5 | (선택) `python -m gah --tray` + 시트 자산 드롭 | 카드 배지 + Claude pick 시나리오 동작 |

## 6. 메모리 갱신

M6 종료 시 다음 memory entry 작성:
- `project_m6_complete.md` (project) — feat/m6-sheet-animation 브랜치 main 머지 대기, ~73 신규 테스트, 18 MCP 도구.

## 7. 다음 마일스톤 (M7)

[`DESIGN.md`](../DESIGN.md) §11 Milestone 7 — Unity Asset Store 임포트 (1주). 다음 세션이 [`HANDOFF.md`](../HANDOFF.md) 갱신본을 보고 M7 spec/plan 작성부터 시작.
