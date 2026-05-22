<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# .github

## Purpose
GitHub 플랫폼 자동화 (Actions workflows). 현재는 PyPI Trusted Publishing 자동 publish workflow 만 들어 있다 — git tag push → OIDC 인증 → PyPI publish 가 평균 30초 안에 끝난다 (5회 검증).

## Key Files
이 디렉터리에는 파일이 없다. workflow 는 `workflows/` 하위에 있다.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `workflows/` | GitHub Actions YAML (see `workflows/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- workflow 수정은 main 으로 머지된 직후 효과 발생 (PR 단위에선 PR 의 workflow 가 아닌 main 의 workflow 가 실행).
- Node.js runner 버전 호환에 주의 — M10 후속 fix 로 `actions/checkout@v6` + `actions/setup-python@v6` 로 한 차례 끌어올림 (PR #12).
- Trusted Publishing 은 PyPI 에서 publisher 등록되어야 동작 (저장소 owner + workflow filename 매칭).

### Testing Requirements
- workflow 변경은 실제 tag push 로 검증 — local 검증 도구 없음.

### Common Patterns
- workflow trigger 는 `on: push: tags: ['v*']` 패턴.
- 비밀값은 `secrets.*` 가 아닌 OIDC ID token 으로 PyPI 인증 (Trusted Publishing).

## Dependencies

### Internal
- `pyproject.toml` — version·name 이 tag/package 와 일치해야 publish 성공.

### External
- GitHub Actions runner — Node.js 24 호환 액션만.
- PyPI publisher 등록 (`v0o0v/assetcache-mcp` + `publish.yml`).

<!-- MANUAL: -->
