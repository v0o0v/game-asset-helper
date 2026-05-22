<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# updater

## Purpose
M10 Phase 2 — PyPI 신버전 알림. PyPI JSON API + ETag 캐시 + 24h PollingLoop 로 신버전 감지 → 트레이 메뉴 + 웹 배너 안내. **자동 설치는 안 함** — `pipx upgrade` / `uv tool upgrade` 명령을 사용자에게 안내만 한다.

> M9 의 코드 서명 + 자동 업데이트 (PyPI 가 아닌 GitHub release 기반) 는 path pivot 됐다. feat/m9 브랜치 deleted, spec/plan 만 보존 (`docs/superpowers/specs/2026-05-19-m9-*.md`).

## Key Files
| File | Description |
|------|-------------|
| `version.py` | `Version` semver dataclass + classmethod (`parse`, `from_tag`) + ordering (`__lt__` / `__gt__`) |
| `checker.py` | `PyPIChecker` — PyPI JSON API (`https://pypi.org/pypi/assetcache-mcp/json`) + ETag 캐시 + 24h PollingLoop |
| `pip_command.py` | `format_upgrade_command(installer)` — pipx / uv / pip 분기. 트레이 메뉴 + 배너에 표시 |

## For AI Agents

### Working In This Directory
- **자동 설치 안 함** — 사용자가 명령 복사해서 실행. 안전성 + 권한 회피.
- **24h 폴링** — `Config.update_check_interval_hours=24` 기본. PollingLoop 는 별도 스레드.
- **ETag 캐시** — PyPI 가 304 반환하면 body 파싱 skip (네트워크/CPU 절약).
- **신버전 표기** — 트레이 메뉴 (red dot) + 웹 페이지 상단 `_pypi_update_banner.html`. 두 곳 모두 사용자가 dismiss 가능.
- **patch publish 평균 30초 패턴** — tag push → workflow 자동. PyPI CDN lag ~15초 (project memory `project_trusted_publishing_pattern`).

### Testing Requirements
- `tests/test_updater_version.py` — semver parse + ordering.
- `tests/test_updater_checker_pypi.py` — PyPI JSON API + ETag.
- `tests/test_pip_command.py` — installer 분기.
- `tests/test_tray_pypi_notification.py` — 트레이 알림.
- `tests/test_updates_router_simplified.py` — 웹 배너 라우터.

### Common Patterns
- installer 탐지 — `sys.executable` 경로 패턴 + `os.environ` 검사 (`PIPX_LOCAL_VENVS` / `UV_PYTHON` 등).
- `Version.parse` 는 strict semver. PyPI prerelease (`0.2.0a1`) 도 지원.

## Dependencies

### Internal
- `../../config.py` (`Config.update_check_*`).
- `../../tray.py` (TrayController 메뉴 추가).
- `../../web/routers/updates.py` (배너 라우터).

### External
- `httpx` (PyPI JSON API).

<!-- MANUAL: 자동 설치는 의도적으로 미지원. 사용자가 명령 복사 후 실행. -->
