<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# src

## Purpose
Python 패키지 소스 루트. `pyproject.toml` 의 `[tool.setuptools] package-dir = { "" = "src" }` 로 매핑돼 `src/assetcache/` 가 `import assetcache` 로 임포트된다.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `assetcache/` | 본 패키지 (M10 에서 `gah/` → `assetcache/` rename) (see `assetcache/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `src/` layout — 새 모듈 추가는 `assetcache/` 하위에. `src/` 직접 아래엔 패키지 외 파일 두지 않는다.
- `src/assetcache_mcp.egg-info/` / `src/game_asset_helper.egg-info/` 는 build 산출물 (전자는 현재 패키지명, 후자는 M10 이전 패키지명 잔존). git ignore 되어야 함.
- `tests/conftest.py` 의 `pythonpath = ["src"]` 가 pytest 의 import 경로 매핑.

### Common Patterns
- 모든 import 는 `from assetcache.{...}` 형태. 상대 import (`from .config import ...`) 는 패키지 내부에서만.
- M10 rename 자취: `assetcache` 가 현재 정식 명칭. `gah` / `game_asset_helper` 잔존 식별자는 모두 정리됨 (잔존 검출 시 갱신 대상).

## Dependencies

### Internal
- `pyproject.toml` — 패키지 매핑 + entry script.
- `tests/conftest.py` — pythonpath 매핑.

<!-- MANUAL: -->
