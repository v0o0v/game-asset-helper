<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# workflows

## Purpose
GitHub Actions workflow 정의. 현재는 PyPI Trusted Publishing 단 한 개 — git tag(`v*`) push 시 자동으로 `python -m build` → OIDC 인증 → PyPI upload 까지 진행.

## Key Files
| File | Description |
|------|-------------|
| `publish.yml` | tag push 트리거 PyPI publish workflow (Trusted Publishing OIDC, 5회 검증, 평균 30초) |

## For AI Agents

### Working In This Directory
- `publish.yml` 의 `on: push: tags:` 패턴을 깨면 자동 publish 가 통째로 죽는다.
- 검증된 패턴: tag `v0.2.x` push → workflow → PyPI 에 ~30초 후 등록. CDN lag ~15초 추가.
- workflow 가 사용하는 액션 버전 (`actions/checkout`, `actions/setup-python`, `pypa/gh-action-pypi-publish`) 은 Node.js 24 호환 버전으로 고정 (M10 후속 fix).
- 보안 — PyPI publisher 등록(Trusted Publishing)이 secret 없이 publish 를 가능하게 한다. PyPI 측 publisher 설정과 workflow 파일명(`publish.yml`) 이 일치해야 한다.

### Testing Requirements
- local dry run 불가 — 실제 tag push 로만 검증.
- publish 실패 시 GitHub Actions 의 run log 와 PyPI 의 publisher 설정 양쪽을 확인.

### Common Patterns
- version bump → `pyproject.toml` + `src/assetcache/__init__.py` 두 곳을 같은 값으로 → tag → push tag.
- v0.2.x patches 누적 패턴: M11.4~M11.7 에서 v0.2.3~v0.2.6 publish 보류 후 M11.8 머지 시점에 v0.2.7 한 번에 bump 권장 (HANDOFF.md).

## Dependencies

### Internal
- `pyproject.toml` — `[project].name` + `[project].version` 이 publish target.
- `src/assetcache/__init__.py` — `__version__` 이 동기화돼야 함.

### External
- `pypa/gh-action-pypi-publish` — OIDC publish 액션.
- PyPI Trusted Publishing 등록.

<!-- MANUAL: -->
