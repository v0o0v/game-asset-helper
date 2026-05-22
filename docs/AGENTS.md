<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# docs

## Purpose
사용자/개발자용 가이드 + 마일스톤별 spec/plan 아카이브 (`superpowers/`). 루트의 `CLAUDE.md` / `DESIGN.md` / `HANDOFF.md` 가 살아있는 문서라면, 여기는 **특정 시점의 결정**을 보존하는 정지된 문서가 들어간다.

## Key Files
| File | Description |
|------|-------------|
| `SETUP.md` | 새 PC 셋업 절차, `pytest -q` baseline, 자주 쓰는 명령 (tray/mcp/version), 옵트인 마커 안내 |
| `MCP_USAGE_GUIDE.md` | MCP 20 도구 사용 가이드 (Claude Code 측 워크플로 + label_query 문법 + diversity 옵션) |
| `WEB_UI_GUIDE.md` | 웹 GUI 상세 사용법 (라이브러리/팩/라벨 admin/Claude pick) |
| `RELEASE_NOTES_v0.0.1.md` | v0.0.1 릴리스 노트 (historical) |
| `M5_PR_BODY.md` | M5 PR description draft (historical) |
| `M5_PR_DESCRIPTION_DRAFT.md` | M5 PR description draft (historical) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `superpowers/` | `/superpowers` 워크플로의 spec/plan 아카이브 (see `superpowers/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- 사용자 가이드 (`SETUP.md` / `MCP_USAGE_GUIDE.md` / `WEB_UI_GUIDE.md`) 는 살아있는 문서 — 마일스톤마다 갱신 (예: MCP 도구 수 / 회귀 baseline).
- `M5_*` / `RELEASE_NOTES_*` 처럼 마일스톤 PR 시점에 생성된 draft 는 **historical 보존**. 갱신 X.
- 새 마일스톤 design 은 `superpowers/specs/YYYY-MM-DD-...-design.md` 로 신규 작성. 기존 spec 수정 X.

### Testing Requirements
- 문서 변경은 별도 테스트 없음. 다만 코드와 어긋나는 사실이 있으면 update.

### Common Patterns
- 파일명은 영어, 본문은 한글 (CLAUDE.md §4.1).
- spec / plan 은 `superpowers/` 아래 날짜 prefix (`YYYY-MM-DD-*.md`).
- 마일스톤 verification 은 `docs/` 가 아닌 `milestones/M{N}_verification.md` 에 둔다.

## Dependencies

### Internal
- 루트 `CLAUDE.md` / `DESIGN.md` / `README.md` — 사용자 가이드의 권위 있는 출처.
- `milestones/` — design 결정의 verification.

### External
- GitHub 마크다운 렌더러 (PyPI 페이지는 README.md 만 렌더).

<!-- MANUAL: -->
