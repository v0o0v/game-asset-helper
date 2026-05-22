<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# sheet

## Purpose
M6 — 스프라이트 시트 검출 / 격자 추정 / JSON 사이드카 파서 / 미리보기 합성. JSON 사이드카(Aseprite/TexturePacker) 우선, 격자 추정 폴백, 8칸 그리드 미리보기 합성을 책임진다. M6 spec §4.1~§4.9 참고.

## Key Files
| File | Description |
|------|-------------|
| `detect.py` | `detect_sheet(path, config)` — JSON 사이드카 → grid detect → 시트 여부 판정. `FrameSpec.w/h` 가 `stride_x/y` (slot 크기) 사용 (M11.3 D-2 patch) |
| `grid_detect.py` | M11.4 강화 — 2-path: alpha valley + color-edge fallback. `Config.grid_detect_alpha_color_weight=0.5` 전파 wiring (`detect_sheet` → `BatchManager` → `BatchPoller` → `SpritesheetAnalyzer`) |
| `json_parser.py` | Aseprite Array/Hash + TexturePacker 자동 형식 판별 |
| `preview.py` | 8칸 그리드 미리보기 합성 — 8 이하 그대로, 그 이상 선형 stride 샘플링 |
| `types.py` | `FrameSpec` / `SheetSpec` / `Animation` dataclass |

## For AI Agents

### Working In This Directory
- **2-path grid detect (M11.4)** — alpha 채널 valley 가 1차, color-edge fallback 이 2차. `Config.grid_detect_alpha_color_weight` (default 0.5) 가 두 path 가중치 결합.
- **`FrameSpec.w/h = stride_x/y` (M11.3 D-2)** — 이전엔 frame 자체 크기였는데 slot 크기 (gap 포함) 가 정답. spec/animator 가 stride 로 frame index 계산.
- **JSON 사이드카 우선** — 동명 `.json` 이 있으면 grid_detect 우회. 새 형식 추가 시 `json_parser.py` 의 detect 함수에 시그니처 추가.
- **8칸 합성 한계** — frame 9개 이상 시트는 stride 샘플링 (선형). 짧은 애니메이션 frame 디테일은 보존되지만 긴 BGM-style 시트는 정보 손실.
- **시트 폴백** — grid detect 실패 시 일반 `sprite` 로 폴백 (사용자 frame size 입력 GUI 는 M7+ v2 후속).

### Testing Requirements
- `tests/test_sheet_detect.py` — 시트 vs 단일 분류.
- `tests/test_sheet_detect_alpha_color_weight_wiring.py` — M11.4 wiring.
- `tests/test_sheet_grid_detect.py` + `test_sheet_grid_detect_color_edge.py` — 2-path grid detect.
- `tests/test_sheet_json_parser.py` — Aseprite/TexturePacker 파서.
- `tests/test_sheet_preview.py` — 미리보기 합성.
- `tests/test_sheet_types.py` — dataclass.

### Common Patterns
- fixture: `tests/fixtures/sheets/` 의 Aseprite Array / Hash + TexturePacker 샘플 + `make_complex_sheets.py` 로 생성한 합성 시트.
- detect 호출 카운트 측정은 monkeypatch (project memory `project_batch_path_drive_pattern`).

## Dependencies

### Internal
- `../analyzer/spritesheet.py` (분석기 호출).
- `../analyzer/spritesheet_meta.py` (meta 빌더).
- `../batch/sheet_classifier.py` (sprite vs sheet 분류).
- `../batch/manager.py` (detection cache).

### External
- Pillow (alpha 채널 + 색상 분석).
- numpy (격자 valley 검출).

<!-- MANUAL: frame size 사용자 입력 GUI 는 M7+ v2 후속 (미구현). 자동 grid 실패 시 일반 sprite 폴백. -->
