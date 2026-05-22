<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# analyzer

## Purpose
M2 분석 파이프라인. 파일 종류별 (sprite / sound / spritesheet) 다른 파이프라인을 타고, 결과는 동일한 JSON 스키마. **sync 경로** 와 **batch 경로** 가 같은 메시지/페이로드 헬퍼를 공유해 parity 유지.

## Key Files
| File | Description |
|------|-------------|
| `base.py` | `AnalyzerBase` (Protocol) + 공통 메타 dataclass (`AssetMeta` / `AnalysisState`) |
| `sprite.py` | `SpriteAnalyzer` — Pillow 열기 + 도미넌트 컬러 + 픽셀아트 휴리스틱 + Gemma 4 멀티모달 호출 + JSON 검증 (registry 라벨 enum + hex 금지). M11.4 에서 sync `_build_system_prompt` 가 batch 메시지와 parity (registry 라벨 enabled 일 때만 동적 inclusion) |
| `sound.py` | `SoundAnalyzer` — librosa / soundfile 기술 특성 + 30초 청크 + 네이티브 오디오 1차 / 멜 스펙트로그램 비전 2차 / 휴리스틱 3차 폴백 |
| `spritesheet.py` | `SpritesheetAnalyzer` — JSON 사이드카 → grid detect → 8칸 미리보기 → Gemma 4 → `animation_hint` |
| `messages.py` | `BATCH_IMAGE_PROMPT` / `BATCH_SPRITESHEET_PROMPT` / `BATCH_AUDIO_PROMPT` — batch API 용 system + user 프롬프트. M11.6 palette tone group enum + M11.7 mood OPTIONAL + category 별 mood 차단. "do NOT use 'other'" 가이드 |
| `payload_parser.py` | LLM JSON 응답 검증 — `_coerce_to_dict` (list/None graceful) + `_PAYLOAD_HEX_RE` (palette/mood/animation 모두 `{axis}_hex={value}` violation 검출) |
| `tech_meta.py` | sync/batch 공유 — Pillow + librosa 로 해상도/길이/RMS/spectral 메타 추출 |
| `spritesheet_meta.py` | sync/batch 공유 — frame range + frameTags + animation 메타. `animations_json_to_specs` helper |

## For AI Agents

### Working In This Directory
- **sync ↔ batch parity 가 핵심** — `sprite.py._build_system_prompt` 변경 시 `messages.BATCH_IMAGE_PROMPT` 도 같이 갱신. M11.4 회귀 (`tests/test_prompt_*` + `tests/test_batch_*_prompt_*`) 가 둘을 묶어 검증.
- **메시지 프롬프트 가이드 (M11.6+M11.7)**:
  - palette: tone group enum (warm / cool / muted / neutral / vibrant / high_contrast) 강제.
  - "do NOT use 'other'" 가이드 (M11.6).
  - mood: OPTIONAL — 라벨이 명확하지 않으면 출력 X (M11.7).
  - category 별 mood 차단 — 일부 category (inventory_item, ui_icon 등) 에선 mood 출력 금지 (M11.7).
- **hex 금지** — 모든 axis (palette/mood/animation) 에서 `{axis}_hex=#RRGGBB` 같은 값은 violation. `_PAYLOAD_HEX_RE` 가 검출.
- **registry 가이드 동적화 (M11.4)** — guidance 는 registry 의 해당 라벨이 enabled 일 때만 system prompt 에 포함. `LabelRegistry.is_enabled()` 의존.
- **sound 폴백 3 단계** — 네이티브 → 멜 스펙트로그램 → 휴리스틱. `analysis_state='partial'` 마킹.

### Testing Requirements
- `tests/test_analyzer_*.py` — 모듈별.
- `tests/test_prompt_no_other_fallback.py` — 'other' 금지.
- `tests/test_prompt_mood_optional.py` — mood OPTIONAL (M11.7).
- `tests/test_prompt_category_mood_exclusion.py` — category 별 mood 차단 (M11.7).
- `tests/test_batch_spritesheet_prompt_palette.py` — palette tone group (M11.6).

### Common Patterns
- LLM JSON 응답은 항상 `payload_parser._coerce_to_dict` 통과 — list / None / wrapped JSON 흡수.
- `analysis_state` = `complete` / `partial` / `failed`. partial 은 휴리스틱 마킹용.

## Dependencies

### Internal
- `../labels.py` (`LabelRegistry` enum + enabled 여부).
- `../ollama_client.py` (HTTP 래퍼).
- `../llm/chain.py` (BackendChain — backend abstraction).
- `../batch/manager.py` (batch 측 호출).

### External
- Pillow, librosa, soundfile, numpy, httpx, matplotlib (멜 스펙트로그램 폴백).

<!-- MANUAL: sync ↔ batch parity 는 M11.4 회귀의 핵심. 프롬프트 한쪽만 갱신 X. -->
