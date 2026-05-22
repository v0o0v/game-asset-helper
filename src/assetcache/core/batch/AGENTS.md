<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# batch

## Purpose
M11.1+ — backend batch API 제출 / 폴링 / 결과 persist. 1차 backend 는 Gemini Batch API (50% 비용). hybrid 정책 (임계값 30) 이 작은 작업은 sync 로, 큰 작업은 batch 로 라우팅.

## Key Files
| File | Description |
|------|-------------|
| `manager.py` | `BatchManager` — submit / status / cancel + `_BoundedLRUCache(OrderedDict)` `_detection_cache` (max 1024 LRU, M11.3). `classify_image_assets` 호출 시 sprite_meta enrich+save 자동 |
| `poller.py` | `BatchPoller` — 큰 작업 폴링 + label parsing + meta filling. `_try_enrich_with_sheet` 가 `store.get_sprite_meta` 우선 확인 후 cache hit 시 `detect_sheet` 우회 (M11.3). registry + library_dir 주입 받음 |
| `sheet_classifier.py` | `classify_image_assets` — sprite vs spritesheet 분류 + cache 인자 + save_sprite_meta 인자 (M11.3 시트 hit 시 자동 enrich+save) |
| `types.py` | `BatchJob` / `BatchItem` / `BatchStatus` dataclass + 직렬화 helper |

## For AI Agents

### Working In This Directory
- **Detection cache** — `BatchManager._detection_cache` (max 1024 OrderedDict LRU). 메모리 누수 회피용 bounded.
- **sync ↔ batch parity** — `BatchPoller` 의 label parsing 은 `analyzer/payload_parser.py` 의 헬퍼를 그대로 재사용. 새 axis 추가 시 양쪽 동시.
- **silent fail 의심 시** — `BatchPoller` polling 이 silent crash 가능 (HANDOFF backlog B). thread-local SQLite connection 가능성. 디버깅 시 trace + logging level DEBUG.
- **registry 주입** — `BatchPoller` 가 graceful fallback (registry 미주입 시 default `LabelRegistry()` 생성). 다만 dynamic guidance 가 빠지므로 운영 환경에선 항상 주입.
- **modality 분기** — M11.2 에서 `chat_spritesheet` modality 신설. `classify_image_assets` 가 시트 hit 시 grid detect 후 batch 호출 modality 를 `chat_spritesheet` 로 전환 (`messages.BATCH_SPRITESHEET_PROMPT` 적용).

### Testing Requirements
- `tests/test_batch_manager.py` — submit/status.
- `tests/test_batch_manager_detection_cache.py` — LRU cache.
- `tests/test_batch_manager_spritesheet.py` — 시트 분기.
- `tests/test_batch_poller*.py` — polling + label parsing + meta filling + spritesheet modality + sprite_meta cache.
- `tests/test_batch_sheet_classifier*.py` — sprite/sheet 분류 + cache.
- `tests/test_batch_end_to_end.py` — concurrency=0 + 직접 instantiate + try_submit + foreground poll 패턴 (project memory `project_batch_path_drive_pattern`).
- `tests/test_batch_spritesheet_prompt_palette.py` — palette tone group 검증.

### Common Patterns
- LIVE 검증 — `scripts/drive_live_batch.py` 가 마일스톤마다 재사용. concurrency=0 + 직접 instantiate + `try_submit` + foreground poll.
- store 의존 — `get_sprite_meta` / `save_sprite_meta` / `save_label` 가 cache hit 의 source of truth.

## Dependencies

### Internal
- `../analyzer/messages.py` (BATCH_* 프롬프트).
- `../analyzer/payload_parser.py` (응답 검증).
- `../analyzer/tech_meta.py` + `analyzer/spritesheet_meta.py` (메타 enrich).
- `../sheet/detect.py` (sheet hit 판정).
- `../store.py` (sprite_meta cache).
- `../labels.py` (`LabelRegistry`).
- `../llm/registry.py` + `../llm/backends/gemini.py` (Gemini Batch API).

### External
- `google-genai` (Gemini Batch API).

<!-- MANUAL: BatchPoller silent fail (HANDOFF backlog B) 는 미해결. polling 안 되는 사례 발생 시 thread-local SQLite connection 의심. -->
