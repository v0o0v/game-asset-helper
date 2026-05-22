<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# specs

## Purpose
`/superpowers` 의 spec(design) 산출물 — 한 마일스톤의 **design 결정** 스냅샷. 짝 plan 은 `../plans/` 에 있다. 날짜 prefix 가 결정 시점을 박제한다.

## Key Files
| File | Description |
|------|-------------|
| `2026-05-17-m5-web-gui-and-library-redesign.md` | M5 — Qt → FastAPI 웹 GUI 전환 |
| `2026-05-17-mcp-search-success-rate-design.md` | MCP 검색 성공률 측정 design |
| `2026-05-18-m6-sheet-and-animation-design.md` | M6 — 시트 분석 + 애니메이션 프레임 |
| `2026-05-18-m7-unity-asset-store-import-design.md` | M7 — Unity Asset Store .unitypackage 임포트 |
| `2026-05-19-m8-packaging-and-i18n-design.md` | M8 — PyInstaller + ko/en i18n |
| `2026-05-19-m9-code-signing-and-auto-update-design.md` | M9 — 코드 서명 + 자동 업데이트 (path pivot, historical) |
| `2026-05-19-m10-pypi-and-rename-design.md` | M10 — PyPI 배포 + rename |
| `2026-05-20-backend-help-cards-design.md` | /settings backend help card |
| `2026-05-20-gemini-batch-api-design.md` | M11.1 — Gemini Batch API (50% 비용 + /analyzing dashboard) |
| `2026-05-20-m11-multi-backend-llm-design.md` | M11 — multi-backend LLM 아키텍처 |
| `2026-05-20-roadmap-design.md` | M11~M18 전체 로드맵 |
| `2026-05-20-v011-yagni-clean-v001-compat-design.md` | v0.1.1 yagni-clean |
| `2026-05-21-m11-2-batch-spritesheet-modality.md` | M11.2 — batch spritesheet modality (`chat_spritesheet` 신설) |
| `2026-05-21-m11-3-detection-cache.md` | M11.3 — Detection Cache + 부수 patch |
| `2026-05-21-m11-4-grid-detect-strengthen-llm-accuracy.md` | M11.4 — grid_detect 강화 + LLM 분류 정확도 |
| `2026-05-21-m11-5-live-validation-and-tuning.md` | M11.5 — LIVE validation + acceptable set strict |
| `2026-05-22-m11-6-spritesheet-palette-and-other-cleanup.md` | M11.6 — BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 |
| `2026-05-22-m11-7-mood-noise-cleanup.md` | M11.7 — mood OPTIONAL + category 별 mood 차단 |
| `2026-05-22-m11-8-mood-seed-disable.md` | **M11.8 — mood 시드 `neutral`/`minimalist` 비활성화** (다음 implement 대상, v0.2.7 candidate) |

## For AI Agents

### Working In This Directory
- spec 은 design 결정 스냅샷이다. **수정 X**. 변경은 새 날짜 prefix 로 신규 spec.
- 짝 plan 은 `../plans/` 같은 슬러그 (끝의 `-design` 없음). plan-only 마일스톤 (M11.1, M11.2) 도 있고, spec-only 마일스톤 (M11.3~M11.8) 도 있다 — 짝이 한쪽만 있는 경우 정상.
- ⚠️ **M11.8 작업 시 핵심 주의**: `palette.neutral` 은 절대 비활성화 X (M11.6 tone group enum 핵심 토큰). `mood.neutral` + `mood.minimalist` 만 대상.

### Common Patterns
- design 섹션: 문제 정의 → 옵션 비교 → 결정 + 근거 → 영향 범위 → out-of-scope.
- 자주 등장: ADR (Architectural Decision Record), 8 phase 분해, TDD 전략.

## Dependencies

### Internal
- `../plans/{같은 slug}.md` — spec 의 phase 실행 계획.
- `milestones/HISTORY.md` — 머지 완료 마일스톤의 PR/회귀 결과.
- 루트 `DESIGN.md` — spec → design 승격 시 반영.

<!-- MANUAL: M11.8 작업 시 palette.neutral 절대 유지. mood.neutral + mood.minimalist 만 비활성화. -->
