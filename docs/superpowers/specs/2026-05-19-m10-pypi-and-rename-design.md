# M10 — PyPI 배포 + AssetCacheMCP rename design

**작성일**: 2026-05-19
**대상 마일스톤**: M10 (v2 첫 마일스톤, M0~M8 + 보류된 M9 다음)
**선행 마일스톤**: M8 (패키징 + i18n, v0.0.1 release published). M9 (코드 서명 + 자동 업데이트) 는 `feat/m9-code-signing-and-auto-update` 브랜치에 implementation 완료 (1111 tests) 되어 있으나 path pivot 으로 **main 머지 보류**. 일부 모듈은 본 M10 에서 cherry-pick.
**예상 일정**: ~6일 (~1.2주)
**예상 신규 테스트**: +35 (1047 → ~1082)
**예상 신규 의존성**: 1건 (`respx>=0.20` dev — M9 에서 추가, M10 에 그대로 보존)

---

## 1. 동기

v0.0.1 (PyInstaller `GameAssetHelper.exe` 323MB GitHub release) publish 직후 사용자 onboarding 마찰 두 가지가 명확해짐:

1. **Windows SmartScreen 경고** — 코드 서명 인증서 없음 → "Windows에서 PC 보호" 경고. release notes 의 우회 안내가 있어도 신뢰도 ↓.
2. **Mac/Linux 미지원** — PyInstaller 는 빌드 시점 OS 종속. Mac `.app` 만들려면 Mac 머신 필요. Cowork 환경상 Windows 만 있음.

M9 (SignPath OSS 무료 서명 + 자동 업데이트) implementation 완료 후 path 재고:
- SignPath 신청 = 인적 심사 (수일~수주) + ongoing policy 관리 부담
- **PyPI** (`pipx install assetcache-mcp`) = 즉시 + 무료 + cross-platform + SmartScreen 우회 불필요
- 사용자 base = Unity 개발자 (Python 익숙) → 터미널 한 줄 install 부담 작음

이에 따라 **PyPI 1순위, SignPath option B** 로 결정 (자세한 결정 컨텍스트는 [memory `project-v2-distribution-strategy`](../../memory/project_v2_distribution_strategy.md)). 동시에 사용자가 PyPI 검색 시 "MCP 지원" 정보를 이름에 노출하길 원해 앱 이름 rename 도 결합 ([memory `project-v2-rename-to-assetcachemcp`](../../memory/project_v2_rename_to_assetcachemcp.md)).

M10 은 이 두 변화를 한 마일스톤에 묶는다. **Mac/Linux 풀 지원은 M11 별도 마일스톤** (sys.platform 가드 + autostart Mac/Linux 구현 + CI 매트릭스).

## 2. 핵심 결정사항 요약

| 결정 | 선택 | 근거 |
|---|---|---|
| 1순위 배포 채널 | **PyPI** (`pipx install assetcache-mcp`) | cross-platform 무료, SmartScreen 우회 불필요, Unity 개발자 친화 |
| SignPath 활성화 | **보류 (Option B)** | feat/m9 의 신청 docs 보존, future 결정 |
| 앱 이름 | **AssetCacheMCP** (display) / **assetcache-mcp** (PyPI) / **assetcache** (CLI) / **src/assetcache/** | PyPI 점유 가능 확인 (404), MCP suffix 로 검색 가시성 |
| 데이터 폴더 | **%APPDATA%\AssetCacheMCP\** (구 `GameAssetHelper\` 에서 마이그레이션) | platformdirs 가 APP_NAME 만 보면 자동 변경 |
| v0.0.1 데이터 마이그레이션 | **첫 부팅 자동 detect + 웹 GUI 배너 안내** | 안전 + 사용자 인지 명확. CLI `--migrate=copy\|move` 도 헤드리스용 제공 |
| M9 cherry-pick 범위 | **version.py + checker.py(PyPI JSON API 전환) + 단순화 banner + tray notification** | downloader/installer/swap 패턴은 drop (PyPI `pip install -U` 가 대체) |
| Mac/Linux 풀 지원 | **M11 별도 마일스톤** | sys.platform 가드 + autostart + CI 매트릭스, M10 scope 분리 |
| GitHub repo | **v0o0v/game-asset-helper → v0o0v/assetcache-mcp 린네임** | GitHub 자동 301 redirect 보장 |
| Python 지원 매트릭스 | **3.12 only** (`requires-python = ">=3.12"`) | baseline 동일, 검증 부담 제거 |
| CI 자동 publish | **GitHub Actions workflow 포함** | tag v\* push 시 자동 build + twine upload (PYPI_TOKEN secret) |
| TestPyPI 단계 | **포함** | 첫 release 의 metadata/wheel 검증 안전망 |
| Phase 구조 | **Phase 0 rename → 1 마이그레이션 → 2 M9 cherry-pick → 3 문서 → 4 PyPI 업로드 (마지막)** | PyPI 업로드 = irreversible action, 다른 작업 후 마지막 |

**비채택**:
- 단일 console script (`assetcache --mcp` 만) → Claude Desktop config 두 줄. `assetcache-mcp` 별도 entry 가 한 줄 등록 가능
- v0.0.1 사용자 자동 마이그레이션 silent 복사 → 사용자가 데이터 이동을 모르는 사이 일어남, 예상치 못한 동작 위험
- CLI subcommand 만 (`assetcache migrate`) → 일반 사용자 터미널 어려움
- Mac/Linux 풀 M10 포함 → scope 1주 초과 + Mac 머신 검증 불가
- M9 의 다운로드/swap 모듈 cherry-pick → PyPI `pip install -U` 가 대체, 코드 단순화

## 3. 아키텍처

```
assetcache-mcp  (PyPI package, installed via pipx/uv tool)
│
├─ Console scripts (entry points)
│   ├─ assetcache         → main()         (--tray | --mcp | --version | --data-dir | --migrate=copy|move)
│   └─ assetcache-mcp     → main_mcp()     (직접 MCP stdio 진입, Claude Desktop config 한 줄용)
│
├─ src/assetcache/         (구 src/gah/, 통째 이동)
│   ├─ __init__.py
│   ├─ __main__.py         dispatcher
│   ├─ config.py           APP_NAME = "AssetCacheMCP"
│   ├─ core/
│   │   ├─ migration.py    (신규) v0.0.1 → AssetCacheMCP 데이터 폴더 마이그레이션
│   │   └─ updater/        (M9 cherry-pick)
│   │       ├─ __init__.py
│   │       ├─ version.py       (그대로) semver-lite
│   │       ├─ checker.py       (수정) PyPI JSON API 폴링
│   │       └─ pip_command.py   (신규) pipx/uv/pip 환경 검출 + 명령 반환
│   ├─ web/
│   │   ├─ routers/
│   │   │   ├─ migration.py   (신규) /api/migration/{status,run,progress}
│   │   │   └─ updates.py     (단순화) /api/updates/check 만 유지
│   │   └─ templates/
│   │       ├─ _migration_banner.html  (신규) Alpine + HTMX
│   │       └─ _pypi_update_banner.html (단순화) "v0.2.0 사용 가능: <copyable cmd>"
│   ├─ tray.py            (수정) 동적 메뉴 + Qt Signal cross-thread (M9 패턴 보존)
│   ├─ platform/
│   │   └─ single_instance.py    (Windows-only 그대로, M11 가드)
│   ├─ ... (M0~M8 의 다른 모듈 모두 동일)
│   └─ locale/
│       ├─ ko/LC_MESSAGES/assetcache.po
│       └─ en/LC_MESSAGES/assetcache.po
│
└─ pyproject.toml
    [project]
    name = "assetcache-mcp"
    version = "0.1.0"
    requires-python = ">=3.12"
    [project.scripts]
    assetcache = "assetcache.__main__:main"
    assetcache-mcp = "assetcache.__main__:main_mcp"
    [project.urls]
    Homepage = "https://github.com/v0o0v/assetcache-mcp"
    Issues = "https://github.com/v0o0v/assetcache-mcp/issues"
```

**핵심 데이터 플로우 — 첫 부팅 마이그레이션**:

```
사용자가 pipx install assetcache-mcp 후 첫 실행
   │
   │ (1) assetcache --tray
   ▼
core/migration.detect_v001_candidate()
   │ 새 폴더 %APPDATA%\AssetCacheMCP\ 비어있고 구 폴더 %APPDATA%\GameAssetHelper\ 에
   │ metadata.db 또는 library/ 존재 → MigrationCandidate 반환
   ▼
웹 UI 접속 시 base.html 의 _migration_banner.html partial
   │ Alpine x-show + htmx /api/migration/status 폴링
   │ 배너: "v0.0.1 데이터 발견. AssetCacheMCP 로 이주?"
   │ 버튼: [복사] [이동] [나중에]
   ▼
사용자 클릭 → POST /api/migration/run { mode: copy|move }
   │ 백그라운드 asyncio task. SSE /api/migration/progress 로 진행률
   │ shutil.copytree (or os.rename)
   ▼
완료 → path rewrite
   │ - config.toml 의 library_root 갱신
   │ - metadata.db 의 assets.path 중 구 base 시작 행만 rewrite
   │ - unity_imports.unitypackage_path 무손상 (Asset Store cache, 사용자 폴더 외부)
   │ - projects.path 무손상 (Unity 프로젝트 외부 경로)
   ▼
%APPDATA%\AssetCacheMCP\.migrated_from_v001 마커 생성 → 다음 부팅 시 배너 안 뜸
```

**핵심 데이터 플로우 — PyPI 업데이트 알림**:

```
24h 폴링 (PollingLoop) → checker.UpdateChecker.check_once
   │ GET https://pypi.org/pypi/assetcache-mcp/json (ETag/If-Modified-Since)
   ▼
response.info.version 추출 → version.compare 로 현재 vs 비교
   │ available = True 이면
   ▼
pip_command.recommended_upgrade_command()
   │ shutil.which("pipx") → "pipx upgrade assetcache-mcp"
   │ shutil.which("uv")   → "uv tool upgrade assetcache-mcp"
   │ else                  → "pip install -U assetcache-mcp"
   ▼
웹 UI: _pypi_update_banner.html
   │ "v0.2.0 사용 가능. 업그레이드: [copyable cmd]"
   │ 버튼: [복사] [Release notes] [나중에]
트레이: tray.py 동적 메뉴
   │ "v0.2.0 업데이트 가능 →" 항목 추가
   │ 클릭 → 클립보드 명령 복사 + 시스템 trayMessage
```

## 4. 모듈 / 컴포넌트

### 4.1 src/assetcache/core/migration.py (신규)

```python
@dataclass(frozen=True)
class MigrationCandidate:
    source: Path           # %APPDATA%\GameAssetHelper\
    target: Path           # %APPDATA%\AssetCacheMCP\
    total_files: int
    total_bytes: int
    has_db: bool           # metadata.db 존재
    has_library: bool      # library/ 존재

def detect_v001_candidate(paths: AppPaths) -> Optional[MigrationCandidate]:
    """새 폴더 비어있고 구 폴더에 데이터가 있으면 candidate 반환. 아니면 None."""

def is_already_migrated(target: Path) -> bool:
    """target / '.migrated_from_v001' 마커 검사."""

class MigrationRunner:
    """asyncio task 로 실행, 진행 상태는 self.state (pending/running/done/failed)"""

    async def run(self, candidate: MigrationCandidate, mode: Literal["copy", "move"]) -> None:
        # 1. 디스크 공간 사전 검사 (target 볼륨의 free space >= candidate.total_bytes * 1.1)
        # 2. shutil.copytree (skip-if-exists) 또는 os.rename
        # 3. path rewrite (config.toml + metadata.db)
        # 4. 마커 파일 생성
        # 5. 실패 시 새 폴더 partial 파일 정리 + state = failed
```

### 4.2 src/assetcache/web/routers/migration.py (신규)

- `GET /api/migration/status` → `MigrationCandidate | null` JSON
- `POST /api/migration/run { mode }` → 202 Accepted, body `{ task_id }`
- `GET /api/migration/progress?task_id=...` → SSE (`progress`, `done`, `error` 이벤트)
- `GET /api/migration/dismiss` → 이 세션만 배너 닫기 (cookie 기반)

### 4.3 src/assetcache/web/templates/_migration_banner.html (신규)

- Alpine x-show + htmx polling `/api/migration/status` (10초 1회, 마이그레이션 완료 시 stop)
- 진행 중일 때 SSE `/api/migration/progress` 로 progress bar 갱신

### 4.4 src/assetcache/core/updater/checker.py (M9 cherry-pick + 수정)

```python
class UpdateChecker:
    def __init__(self, package_name: str = "assetcache-mcp", current: Version = None):
        self.package_name = package_name
        self.current = current or get_current_version()
        self.cache: Optional[CachedResponse] = None  # ETag + Last-Modified

    async def check_once(self) -> CheckResult:
        # GET https://pypi.org/pypi/{package_name}/json
        # If-Modified-Since / If-None-Match 헤더로 304 응답 활용
        # response.info.version → version.compare
        # CheckResult(current, latest, available, release_notes_url)
```

### 4.5 src/assetcache/core/updater/pip_command.py (신규)

```python
def recommended_upgrade_command(package: str = "assetcache-mcp") -> str:
    if shutil.which("pipx"):
        return f"pipx upgrade {package}"
    if shutil.which("uv"):
        return f"uv tool upgrade {package}"
    return f"pip install -U {package}"
```

### 4.6 src/assetcache/web/routers/updates.py (단순화)

- `GET /api/updates/check` → `{ current, latest, available, command, release_notes_url }`
- M9 의 `start`, `status`, `install` endpoint 모두 **drop**

### 4.7 src/assetcache/web/templates/_pypi_update_banner.html (단순화)

- 표시: "v0.2.0 사용 가능. 업그레이드 명령: `<copyable>`"
- 버튼: 복사 (Alpine clipboard) / Release notes (GitHub 링크) / 나중에
- M9 의 다운로드 SSE 진행률 모두 제거

### 4.8 src/assetcache/tray.py (M9 패턴 보존)

- 동적 메뉴 + Qt Signal cross-thread 마샬링 그대로
- "v0.2.0 업데이트 가능 →" 메뉴 클릭 → 클립보드에 명령 복사 + 시스템 trayMessage 표시

### 4.9 pyproject.toml

```toml
[project]
name = "assetcache-mcp"
version = "0.1.0"
description = "MCP server + tray app for indexing and retrieving 2D sprites, sheets, sounds, and Unity packages via natural language."
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.12"
authors = [{ name = "v0o0v", email = "v0o0v2@gmail.com" }]
keywords = ["mcp", "unity", "asset", "game-development", "claude"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Environment :: Win32 (MS Windows)",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: Microsoft :: Windows",
    "Programming Language :: Python :: 3.12",
    "Topic :: Multimedia :: Graphics",
    "Topic :: Software Development :: Libraries",
]

[project.scripts]
assetcache = "assetcache.__main__:main"
assetcache-mcp = "assetcache.__main__:main_mcp"

[project.urls]
Homepage = "https://github.com/v0o0v/assetcache-mcp"
Issues = "https://github.com/v0o0v/assetcache-mcp/issues"
Documentation = "https://github.com/v0o0v/assetcache-mcp/blob/main/README.md"

[project.optional-dependencies]
# 기존 M0~M9 dev 의존성 그대로 + respx (M9 에서 이미 추가됨)
dev = [
    "pytest>=7",
    "pytest-asyncio",
    "respx>=0.20",
    "babel>=2.14",
    "pyinstaller>=6",
    "build",
    "twine",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
package-dir = { "" = "src" }

[tool.setuptools.packages.find]
where = ["src"]
namespaces = false
```

### 4.10 .github/workflows/publish.yml (신규)

- on: `push: tags: 'v*'`
- jobs: build → twine upload --repository pypi (PYPI_TOKEN secret 사용)
- v0.1.0 manual upload 후 v0.1.1+ 부터 자동화

### 4.11 변경 영향 모듈 (rename 만 — 동작 동일)

`src/gah/` 안의 모든 모듈 (~150 파일) — import path / logger name / 사용자 facing 문자열 갱신만. 동작 동일.

## 5. Phase 구조 + 일정

| Phase | 내용 | 신규 테스트 | 추정 |
|---|---|---:|---:|
| **Phase 0** | rename mechanical — git mv src/gah → src/assetcache, import 전수 교체, APP_NAME, .po, tests, docs (historical 표기 보존), GitHub repo 린네임 | 0 | 1.5일 |
| **Phase 1** | 데이터 폴더 마이그레이션 helper — detect + GUI 배너 + asyncio runner + SSE progress + path rewrite + CLI `--migrate` | +15 | 1일 |
| **Phase 2** | M9 cherry-pick — version.py + checker.py PyPI API + pip_command.py + 단순화 banner + tray notification + i18n msgid | +15 | 1.5일 |
| **Phase 3** | 문서 갱신 + i18n catalog 정합성 검사 + verification — README, CLAUDE.md, HANDOFF.md, DESIGN.md, milestones/M10_*.md (Phase 1/2 에서 추가된 msgid 의 ko/en .po 누락 검증) | +5 | 1일 |
| **Phase 4** | PyPI 패키지 + entry point + 빌드 + TestPyPI 검증 + 정식 업로드 + GitHub Actions workflow + v0.1.0 release | 0 | 1일 |
| **합계** | | **+35** | **6일 (~1.2주)** |

**Phase 의존성**:
- Phase 0 → 1, 2, 3, 4 (다른 phase 모두 새 import path 위에서 빌드)
- Phase 1 ↔ Phase 2 (독립, 병렬 가능 — 단 [project-m5-subagent-workflow](../../memory/project_m5_subagent_workflow.md) 의 phase 순차 진행 권장)
- Phase 3 → Phase 4 (문서 + version bump 후 PyPI 업로드)

**Subagent 모델 선택** ([project-m5-subagent-workflow](../../memory/project_m5_subagent_workflow.md) 적용):
- Phase 0 = haiku 충분 (mechanical grep+replace)
- Phase 1, 2 = sonnet (로직 복잡)
- Phase 3 = haiku (문서 작업)
- Phase 4 = 사용자 직접 (PyPI 업로드 = manual/irreversible)

## 6. 외부 인터페이스 호환성

### 6.1 MCP 도구 (20개)

- 도구 **이름 변경 X** — `search_assets`, `suggest_packs`, `request_user_pick` 등 모두 그대로
- Claude Desktop 의 도구 권한/사용 이력 보존
- Tool description 의 "Game Asset Helper" → "AssetCacheMCP" 표기만 갱신

### 6.2 Claude Desktop config 변경 안내

```json
// 구 (v0.0.1):
{
  "mcpServers": {
    "gah": {
      "command": "python",
      "args": ["-m", "gah", "--mcp"]
    }
  }
}

// 새 (v0.1.0):
{
  "mcpServers": {
    "assetcache": {
      "command": "assetcache-mcp"
    }
  }
}
```

release notes 에 위 비교 명시. 자동 마이그레이션 안 함 (Claude Desktop config 위치 OS 별 + json 편집 위험).

### 6.3 Web UI

- 포트 **9874 유지** (사용자 bookmark 호환)
- URL path 유지 (`/`, `/library`, `/packs`, `/labels`, `/asset/...`, `/project/...`)
- HTML title + 브랜딩만 변경

### 6.4 CLI 옵션

- 기존 유지: `--tray`, `--mcp`, `--version`, `--data-dir`
- 신규: `--migrate=copy|move`
- 진입점 변경: `python -m gah` → `python -m assetcache` (또는 console script `assetcache`)

### 6.5 PyInstaller exe

- `pyinstaller` dev 의존 보존. exe 빌드 옵션 유지 (`pyinstaller --onefile -n AssetCacheMCP src/assetcache/__main__.py`)
- 단 v0.1.0 release 의 primary 배포 = PyPI. exe 는 backlog

## 7. 에러 처리 + Rollback + 안전성

### 7.1 rename Phase 0 회귀 안전망

- `git mv src/gah src/assetcache` 후 `pytest -q` = 1047 passed 유지 못 하면 phase fail
- 검출: `Grep` 으로 `from gah\|import gah` = 0 hits 가 phase exit criteria
- rollback: `git checkout main` 으로 즉시 (브랜치 `feat/m10-pypi-and-rename` 격리)

### 7.2 마이그레이션 실패

- 디스크 공간 부족 → 새 폴더 partial 파일 정리 + 사용자 에러 표시 ("디스크 공간 X MB 필요")
- 권한 부족 → "관리자 권한으로 재시도" 안내
- 중간 종료 (사용자 강제 종료 / 앱 크래시) → `.migrated_from_v001` 마커 없음 → 다음 부팅 시 재시도 (skip-if-exists 옵션)
- DB path rewrite 중 실패 → `.bak` 백업 사전 생성, 실패 시 복구

### 7.3 checker.py PyPI 폴링 실패

- PyPI 서버 다운 / 네트워크 끊김 → silently skip, 다음 24h 폴링 재시도
- ETag 캐시 손상 → 캐시 무시하고 200 응답 처리
- 응답 schema 변경 (version key 없음) → unknown, 배너 표시 X

### 7.4 PyPI 업로드 실패 (Phase 4)

- twine upload 실패 (네트워크, 인증, 동일 버전 충돌) → 수동 재시도. PyPI 는 immutable 이라 동일 버전 재업로드 거부
- TestPyPI 검증에서 wheel 깨졌으면 → 정식 PyPI 업로드 안 함, dist/ 재빌드

### 7.5 GitHub repo 리네임 후 영향

- old URL (`v0o0v/game-asset-helper`) → GitHub 자동 301 redirect 보장
- v0.0.1 release URL 자동 redirect
- M9 checker (`feat/m9` 보존) 가 GitHub Releases API 가리키지만 — feat/m9 는 main 머지 안 되므로 영향 X

## 8. 테스트 전략

### 8.1 회귀 (Phase 0 후)

- `pytest -q` = **1047 passed + 1 skipped + 40 deselected** 유지 (모듈 이름만 변경, 동작 동일)
- `pytest -m mcp_integration` = MCP 20 도구 그대로 응답
- import 누락 검출: `Grep "from gah\|import gah" src/ tests/` = 0 hits

### 8.2 신규 테스트 (Phase 1~4)

| Phase | 테스트 |
|---|---|
| Phase 1 | `test_migration_detect.py` — candidate 감지 (4 케이스: 신규/v0.0.1 데이터/이미 마이그레이션됨/일부 데이터) |
| Phase 1 | `test_migration_runner.py` — copy/move/실패/path rewrite (8 케이스) |
| Phase 1 | `test_migration_router.py` — /api/migration/{status,run,progress,dismiss} (3 케이스) |
| Phase 2 | `test_updater_checker_pypi.py` — PyPI JSON API 모킹 (respx), available/up-to-date/304/timeout (6 케이스) |
| Phase 2 | `test_pip_command.py` — pipx/uv/pip 환경 분기 (3 케이스) |
| Phase 2 | `test_updates_router_simplified.py` — /api/updates/check 만 (2 케이스) |
| Phase 2 | `test_tray_pypi_notification.py` — 동적 메뉴 항목 + 클립보드 복사 (4 케이스) |
| Phase 3 | `test_locale_assetcache_msgid.py` — 신규 msgid 5개 ko/en 둘 다 존재 (5 케이스) |

**합계: +35** (1047 → ~1082)

### 8.3 Wheel smoke (Phase 4)

- 별도 venv 에 `pip install dist/assetcache_mcp-0.1.0-py3-none-any.whl`
- `assetcache --version` → `AssetCacheMCP 0.1.0` 출력 확인
- `assetcache-mcp` → MCP stdio JSON-RPC handshake `tools/list` 응답 20 도구 확인
- `pipx install --index-url https://test.pypi.org/simple/ assetcache-mcp` 으로 TestPyPI 부터 검증

### 8.4 수동 검증 (사용자)

- `assetcache --tray` 부팅 → 트레이 아이콘 노출, 우클릭 메뉴 정상
- 웹 GUI 접속 (http://localhost:9874) → 한글/영어 i18n 갱신 확인
- v0.0.1 데이터 마이그레이션 배너 노출 → 복사/이동/나중에 모두 동작
- PyPI 신버전 시뮬레이션 (checker 의 cache 파일 조작) → 트레이 + 웹 배너 둘 다 알림 표시

## 9. Non-Goals

| 항목 | 비고 |
|---|---|
| Mac/Linux 풀 지원 (autostart/single_instance 가드 + 실 구현) | **M11 별도 마일스톤** |
| 신규 MCP 도구 | 20 도구 그대로, M10 신규 0 |
| 신규 분석/검색/UX 기능 | M10 = packaging + rename + 마이그레이션 + 알림 |
| 자동 업데이트 swap/installer | M9 의 swap 패턴 drop. PyPI `pip install -U` 가 대체 |
| Claude Desktop config 자동 편집 | 위험, 사용자 수동 (release notes 안내) |
| i18n 신규 언어 (ja/zh) | backlog |
| SignPath 신청 활성화 | Option B 유지, feat/m9 의 신청 docs 보존만 |
| 다른 배포 채널 (Homebrew, Chocolatey, Winget) | PyPI 단일. future |
| GUI 마이그레이션 multi-step wizard | 배너 + 버튼 한 번 클릭만 |
| Wheel signing / PyPI 2FA hardware key | future |
| PyInstaller exe 의 v0.1.0 동시 release | exe 는 backlog, M10 primary = PyPI |
| sys.platform 가드 (Windows-only 모듈) | M11 |

## 10. 의존성

### 10.1 신규 의존성

| 패키지 | 종류 | 출처 | 용도 |
|---|---|---|---|
| `respx>=0.20` | dev | M9 에서 추가, M10 그대로 보존 | httpx mock (PyPI JSON API 테스트) |

런타임 의존성 0 추가. Babel/PyInstaller/pytest 등 모두 그대로.

### 10.2 빌드 도구

| 도구 | 사용 시점 |
|---|---|
| `build` | `python -m build` (sdist + wheel 생성) — venv 에 pip install build |
| `twine` | `twine upload` — venv 에 pip install twine |
| GitHub Actions `pypa/gh-action-pypi-publish` | tag v\* push 시 자동 publish workflow |

## 11. 검증 기준 (M10 완료 조건)

자동:
- `pytest -q` = **~1082 passed + 1 skipped + 40 deselected**
- `pytest -m mcp_integration` = MCP 20 도구 응답
- `Grep "from gah\|import gah" src/ tests/` = 0 hits
- `python -m build` 성공, dist/assetcache_mcp-0.1.0-py3-none-any.whl 생성
- 별도 venv 에 `pip install dist/*.whl` 후 `assetcache --version` 0.1.0 출력

수동 (사용자):
- v0.0.1 데이터 마이그레이션 배너 노출 + 복사/이동 둘 다 동작
- 트레이 + 웹 UI 모두 AssetCacheMCP 브랜딩 적용
- PyPI 신버전 알림 (시뮬레이션) 동작
- TestPyPI 에서 `pipx install --index-url ... assetcache-mcp` 설치 후 정상 부팅
- PyPI 정식 업로드 후 `pipx install assetcache-mcp` 일반 사용자 흐름 검증
- GitHub repo `v0o0v/assetcache-mcp` 린네임 + redirect 동작
- v0.1.0 GitHub release 노출 + release notes 마이그레이션 안내 명확

## 12. 후속 마일스톤 / Open Questions

### 12.1 후속 마일스톤 (M11+)

| # | 이름 | 비고 |
|---:|---|---|
| **M11** | Mac/Linux 풀 지원 + CI 매트릭스 | sys.platform 가드, autostart Mac (~/Library/LaunchAgents/) + Linux (~/.config/autostart/), GitHub Actions runner macos-latest + ubuntu-latest |
| **M12+** | future — SignPath option B 활성화 / installer (Windows MSI) / 추가 언어 / 분석 정확도 / pack UX | backlog 우선순위 재정렬 |

### 12.2 Open questions

1. **v0.0.1 사용자 base 규모** — 마이그레이션 helper 의 robustness 어디까지 투자할지 결정 영향. release 직후라 사용자 수 미파악. → Phase 1 후 release 보면서 결정
2. **PyPI 패키지 size** — 첫 sdist + wheel 크기. torch wheel 자동 매칭이라 0.x MB 예상, 검증 필요
3. **release cadence** — v0.1.0 후 v0.1.1 / v0.2.0 등 cadence 미정. CI publish workflow 가 자동화하면 부담 작음

## 13. 참고

- [memory `project-v2-distribution-strategy`](../../memory/project_v2_distribution_strategy.md) — PyPI 1순위 결정 + Mac 지원 의도 + 비용 분석
- [memory `project-v2-rename-to-assetcachemcp`](../../memory/project_v2_rename_to_assetcachemcp.md) — AssetCacheMCP rename 범위 + 마이그레이션
- [memory `project-m9-pivot-state`](../../memory/project_m9_pivot_state.md) — M9 implementation 완료 + 어느 모듈 재사용 가능한지
- [memory `project-m5-subagent-workflow`](../../memory/project_m5_subagent_workflow.md) — phase 단위 subagent 분할 패턴 (Phase 0~4 에 적용)
- M9 spec: [`docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md`](./2026-05-19-m9-code-signing-and-auto-update-design.md)
- v0.0.1 release: [v0.0.1 on GitHub](https://github.com/v0o0v/game-asset-helper/releases/tag/v0.0.1)
- PyPI JSON API 명세: <https://warehouse.pypa.io/api-reference/json.html>
- GitHub Actions `pypa/gh-action-pypi-publish`: <https://github.com/marketplace/actions/pypi-publish>
