<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# superpowers

## Purpose
`/superpowers` 워크플로 (브레인스토밍 → spec → plan → implement) 의 산출물 아카이브. `specs/` 는 design 결정, `plans/` 는 phase 별 실행 계획. 둘 다 **특정 시점**의 결정이며 갱신 X (변경이 필요하면 새 날짜 prefix 로 신규 작성).

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `plans/` | 마일스톤별 phase 실행 계획 (see `plans/AGENTS.md`) |
| `specs/` | 마일스톤별 design 결정 (see `specs/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- 파일명 패턴: `YYYY-MM-DD-{slug}.md` (plans) / `YYYY-MM-DD-{slug}-design.md` (specs). 같은 슬러그 짝지어서 쓴다.
- spec 수정이 아니라 새 spec 발급 — 결정이 바뀌면 새 날짜로.
- `.superpowers/` (저장소 루트 hidden) 은 워크플로 런타임 state — git ignore 됨, 여기와 무관.

### Common Patterns
- spec 우선 작성 → plan → milestones/M{N}_plan.md 로 phase 분해 → TDD red→green → milestones/M{N}_verification.md.

## Dependencies

### Internal
- `milestones/M{N}_plan.md` — spec 의 phase 분해.
- 루트 `DESIGN.md` — spec 이 design 으로 승격되면 반영.

### External
- 없음.

<!-- MANUAL: -->
