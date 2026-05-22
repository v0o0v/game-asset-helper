<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# plans

## Purpose
`/superpowers` 의 plan 산출물 — 한 마일스톤을 phase 단위로 분해한 실행 계획. 짝 spec 은 `../specs/` 에 있다.

## Key Files
| File | Description |
|------|-------------|
| `2026-05-19-m8-packaging-and-i18n.md` | M8 패키징 + i18n |
| `2026-05-19-m9-code-signing-and-auto-update.md` | M9 코드 서명 + 자동 업데이트 (path pivot 됨, historical) |
| `2026-05-19-m10-pypi-and-rename.md` | M10 PyPI 배포 + AssetCacheMCP rename |
| `2026-05-20-backend-help-cards.md` | /settings 의 backend 별 help card |
| `2026-05-20-gemini-batch-api.md` | M11.1 Gemini Batch API (50% 비용) |
| `2026-05-20-m11-multi-backend-llm.md` | M11 multi-backend LLM 아키텍처 |
| `2026-05-20-v011-yagni-clean-v001-compat.md` | v0.1.1 yagni-clean (v0.0.1 호환 제거) |
| `2026-05-21-m11-2-batch-spritesheet-modality.md` | M11.2 batch spritesheet modality |

## For AI Agents

### Working In This Directory
- 새 plan 은 spec 작성 이후 발급. 파일명은 spec 과 같은 슬러그, 끝의 `-design` 없음.
- plan 은 phase 단위 (Phase 1 / 2 / ...) + 각 phase 의 산출물 + TDD 전략 + 검증 기준 명시.
- 한 번 발급한 plan 은 수정 X. 변경은 새 plan 으로.

### Common Patterns
- Phase 분해: 보통 4 phase (TDD red → green → 회귀 검증 → PR).
- LIVE 검증이 필요한 마일스톤은 별도 phase 로 묶음.

## Dependencies

### Internal
- `../specs/{같은 slug}-design.md` — plan 의 design 근거.
- `milestones/M{N}_plan.md` — plan 의 마일스톤화.

<!-- MANUAL: -->
