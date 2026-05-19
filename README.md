# AssetCacheMCP

Unity 게임 개발 중 Claude Code가 보유 에셋(2D 스프라이트, 스프라이트 시트, 사운드)을 자연어로 요청하면 가장 적합한 후보를 돌려주는 **MCP 서버 + 윈도우즈 트레이 상주 앱**.

- 사용자가 `library/<pack>/...` 형태로 에셋 팩 폴더를 통째로 드롭하면 자동 인덱싱
- Ollama로 도는 **Gemma 4**(`gemma4:e4b`)가 이미지·오디오를 직접 보고 의미 라벨 생성
- 한 프로젝트에서 한 번 채택한 팩을 이후 검색에서 우선시해 **통일성 유지**
- 트레이 부팅 → **브라우저 자동 진입** (`http://127.0.0.1:9874`) — FastAPI + HTMX + Alpine.js 기반 웹 UI
- Unity Asset Store 로컬 캐시(`.unitypackage`)도 자동 임포트
- 시트 분할 + 애니메이션 프레임 추론 (`suggest_animation_frames`)
- **PyPI 1차 배포** (`pipx install assetcache-mcp`) — Windows + Mac + Linux 지원, 단일 `.exe` 도 2차로 제공
- 한국어/영어 i18n + 다크모드 + Windows 자동 시작 + PyPI 신버전 알림

전체 설계는 [`DESIGN.md`](./DESIGN.md). 웹 UI 상세 사용법은 [`docs/WEB_UI_GUIDE.md`](./docs/WEB_UI_GUIDE.md).

(스크린샷: 라이브러리 페이지 — 추후 추가)

## 주요 기능

| 기능 | 설명 |
|---|---|
| **에셋 라이브러리 검색** | 자연어 쿼리 + 300ms 디바운스. 의미/키워드/라벨/통일성 6채널 하이브리드 검색 |
| **라이브러리 페이지** (`/library`) | 카드 그리드/리스트 + 사이드 패널 (B/C/D 탭) + 상세 모달 + 사운드 인라인 재생 |
| **팩 관리 페이지** (`/packs`) | 등록된 팩 카드 그리드 + 활성/비활성 토글 |
| **라벨 admin 페이지** (`/labels/admin`) | 24 axis 탭 + 라벨 CRUD + JSON import/export |
| **Claude pick 인터랙션** | MCP 도구 `request_user_pick` — Claude가 후보를 고르면 브라우저에 보라색 선택 카드 출현 |
| **통일성 가중 검색** | 프로젝트별 사용 이력 추적 → 같은 팩·벤더 우선 추천 |
| **MCP 20 도구** | `find_asset`, `suggest_packs`, `record_asset_use`, `request_user_pick`, `suggest_animation_frames`, `import_unity_package` 등 |
| **다크 모드** | OS `prefers-color-scheme` 자동 반영 |
| **PyPI 신버전 알림** | 부팅 시 PyPI JSON API 조회 → 신버전 시 웹 배너 + 트레이 메뉴 안내 |

## 진행 현황

| 마일스톤 | 상태 | 비고 |
|---|---|---|
| M0 — 뼈대 | ✅ 완료 | 트레이 셸·설정·로깅·단일 인스턴스 |
| M1 — 워처 + Pack Manager + DB | ✅ 완료 | watchdog, SQLite 4테이블, 부팅 풀스캔 |
| M2 — 분석 파이프라인 + CLIP | ✅ 완료 | Pillow/librosa/Gemma 4/CLIP, 24 axis 라벨 시드 |
| M2.1 — 병렬화 패치 | ✅ 완료 | 동시성 1→3, Ollama semaphore |
| M3 — 검색 백엔드 + 통일성 + MCP | ✅ 완료 | HybridSearcher, 12 MCP 도구 |
| M4 — 검색 UX 풍부화 | ✅ 완료 (main 머지) | label_query AND/OR/NOT, 16 MCP 도구 |
| M5 — 웹 GUI 전환 + Claude pick | ✅ 완료 (main 머지) | FastAPI 웹 UI + Qt 폐기, 17 MCP 도구 |
| M6 — 시트 분석 + 애니메이션 | ✅ 완료 (main 머지) | 격자 분할, `suggest_animation_frames` (18 MCP) |
| M7 — Unity Asset Store 임포트 | ✅ 완료 (main 머지) | `.unitypackage` 파서 + 활성 프로젝트 (20 MCP) |
| M8 — 패키징 + i18n | ✅ 완료 (main 머지) | PyInstaller `--onefile` + ko/en i18n + 다크모드 + autostart |
| **M10 — PyPI + AssetCacheMCP rename** | **🚧 in-flight** | `pipx install assetcache-mcp` + 마이그레이션 helper + PyPI 신버전 알림 |

마일스톤 사이클(plan → todo → 테스트 → 구현 → verification) 상세는 [`milestones/README.md`](./milestones/README.md).

## 설치 (PyPI — 1차 권장)

가장 간편한 설치는 [`pipx`](https://pipx.pypa.io/) 또는 [`uv`](https://docs.astral.sh/uv/) 도구를 사용한다.

```powershell
pipx install assetcache-mcp
```

또는:

```powershell
uv tool install assetcache-mcp
```

설치 후 PowerShell 어디서든 다음 명령으로 트레이 부팅:

```powershell
assetcache --tray
```

## 설치 (PyInstaller exe — 2차)

PyPI 가 차단된 환경(폐쇄망)이거나 Python 이 설치되지 않은 PC 라면 GitHub Releases 에서 단일 `.exe` 를 받는다.

- [Releases 페이지](https://github.com/v0o0v/game-asset-helper/releases) → 최신 빌드의 `AssetCacheMCP.exe` 다운로드
- 실행 시 SmartScreen 경고 → "추가 정보" → "실행" (코드 서명 미적용)

## 이전 v0.0.1 사용자 — 마이그레이션

v0.0.1 (`Game Asset Helper`) 를 이미 사용 중이었다면 데이터 폴더가 `%APPDATA%\GameAssetHelper\` 에 있다. AssetCacheMCP 는 `%APPDATA%\AssetCacheMCP\` 로 이전된다.

**옵션 A — 웹 UI 배너** (권장): 부팅 후 라이브러리 페이지 상단에 노란 배너가 뜬다. `[복사]` 또는 `[이동]` 클릭.

**옵션 B — CLI**: 헤드리스 환경에서는 다음 명령으로 수동 마이그레이션:

```powershell
assetcache --migrate=copy
```

또는 이동 (구 폴더 삭제):

```powershell
assetcache --migrate=move
```

## 개발 환경 셋업

> Windows 10 + python.org 정식 Python 3.12 기준. Microsoft Store Python은 `%APPDATA%` 가상화 이슈로 권장하지 않는다.

venv는 작업 폴더 바깥(사용자 홈)에 만든다.

```powershell
python -m venv $env:USERPROFILE\.venvs\gah
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

editable 설치 (이 디렉터리에서):

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

테스트:

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `1103 passed, 1 skipped, 40 deselected` 가 나오면 준비 완료 (M10 Phase 0~3 기준).

## 실행

```powershell
python -m assetcache --tray
```

→ 시스템 트레이에 아이콘이 뜨고, 기본 브라우저에서 `http://127.0.0.1:9874/library` 가 자동으로 열린다. 트레이 우클릭 → **종료**.

브라우저가 자동으로 열리지 않으면 트레이 아이콘 우클릭 → **메인 창 열기**.

(스크린샷: 라이브러리 페이지 — 추후 추가)

**웹 UI 주요 페이지**

| URL | 설명 |
|---|---|
| `http://127.0.0.1:9874/library` | 에셋 검색 · 결과 · 사이드 패널 (기본 진입점) |
| `http://127.0.0.1:9874/packs` | 등록된 팩 관리 |
| `http://127.0.0.1:9874/labels/admin` | 라벨 어휘 관리 (24 axis) |

포트 9874가 점유된 경우 9875~9883 사이에서 자동으로 빈 포트를 선택한다.

MCP 서버 모드:

```powershell
python -m assetcache --mcp
```

버전 확인:

```powershell
python -m assetcache --version
```

## Claude Desktop 연동

Claude Desktop 의 설정 파일 (`%APPDATA%\Claude\claude_desktop_config.json`) 에 다음 추가:

```json
{
  "mcpServers": {
    "assetcache": {
      "command": "python",
      "args": ["-m", "assetcache", "--mcp"]
    }
  }
}
```

PyPI 설치 환경에서는 `python -m assetcache --mcp` 대신 entry point 가 가능한 경우 `"command": "assetcache-mcp"` 도 사용 가능 (M10 Phase 4 PyPI 배포 후).

## 런타임 데이터 위치

- `%APPDATA%\AssetCacheMCP\library\` — 에셋 팩(사용자가 직접 드롭)
- `%APPDATA%\AssetCacheMCP\cache\` — 썸네일·스펙트로그램
- `%APPDATA%\AssetCacheMCP\metadata.db` — SQLite (M1부터)
- `%APPDATA%\AssetCacheMCP\config.toml`
- `%APPDATA%\AssetCacheMCP\logs\assetcache.log`

## 문서 맵

| 문서 | 누가 보는가 |
|---|---|
| [`README.md`](./README.md) | 처음 들어오는 사람 |
| [`docs/WEB_UI_GUIDE.md`](./docs/WEB_UI_GUIDE.md) | 웹 UI 사용자 — 라이브러리/팩/라벨/pick 카드 사용법 |
| [`docs/MCP_USAGE_GUIDE.md`](./docs/MCP_USAGE_GUIDE.md) | Claude Code — MCP 20 도구 사용 예시 |
| [`CLAUDE.md`](./CLAUDE.md) | Claude(코드 에이전트)가 작업 시작할 때 |
| [`HANDOFF.md`](./HANDOFF.md) | 다음 세션으로 인계할 때의 현재 스냅샷 |
| [`DESIGN.md`](./DESIGN.md) | 아키텍처·MCP 도구·데이터 스키마 |
| [`milestones/`](./milestones/) | 마일스톤별 plan·todo·verification |

## 개발 규칙

- 모든 문서는 한글, 폴더·파일 이름은 영어
- 마일스톤마다 plan → todo → 테스트 먼저 → 구현 → verification 순서
- 최신 모델·API·버전은 추측 말고 1차 출처 확인 후 반영
- 자세한 건 [`CLAUDE.md §4`](./CLAUDE.md)

## 배포 — 단일 exe 빌드 (M8)

일반 사용자에게 배포할 단일 `.exe` 를 만든다 (PyPI 가 1차 배포지만, exe 2차 배포 옵션 유지).

```powershell
# 1. dev 의존성 설치 (Babel, pyinstaller 포함)
pip install -e .[dev]
```

```powershell
# 2. 번역 카탈로그 컴파일 (.po → .mo)
pybabel compile -d src/assetcache/web/locale
```

```powershell
# 3. 트레이 아이콘 ICO 생성 (런타임 QPixmap → assets/tray.ico)
python scripts/generate_tray_ico.py
```

```powershell
# 4. exe 빌드 (10분 내외, dist/AssetCacheMCP.exe ≈ 308 MB)
pyinstaller assetcache.spec
```

빌드된 exe 는 단일 파일로 배포 가능. 첫 실행 시 CLIP 모델 가중치 (~600 MB) 가
`%APPDATA%\AssetCacheMCP\cache\clip\` 로 자동 다운로드된다.

## 배포 — PyPI publish 자동화 (M10)

PyPI 가 1차 배포 채널. `git tag v0.1.1 ; git push origin v0.1.1` 로 자동 publish 되도록
GitHub Actions workflow (`.github/workflows/publish.yml`) 가 구성되어 있다.

**인증 방식 — Trusted Publishing (OIDC)**:
- API token 없이 GitHub OIDC 만으로 PyPI 인증. 평문 secret 노출 위험 없음
- 사전 셋업: https://pypi.org/manage/account/publishing/ 에서 trusted publisher 등록:
  - PyPI Project Name: `assetcache-mcp`
  - Owner: `v0o0v`, Repository name: `assetcache-mcp`, Workflow name: `publish.yml`
- workflow 의 `permissions.id-token: write` 가 OIDC 토큰 발행 권한 부여
- v0.1.0 은 첫 publish (TestPyPI → 정식 PyPI 순) 수동 수행 완료, 이후 모든 tag push 가 자동
- `skip-existing: true` 설정으로 같은 version 재업로드 시 silent skip (workflow 재실행해도 안전)

수동 빌드 + 업로드 흐름 (참고):

```powershell
# 1. 빌드 (dist/assetcache_mcp-*.whl + .tar.gz 생성)
python -m build
```

```powershell
# 2. TestPyPI 업로드 (선택)
python -m twine upload --repository testpypi dist/*
```

```powershell
# 3. 정식 PyPI 업로드
python -m twine upload dist/*
```

## 번역 추가 (M8)

신규 언어 추가 시:

```powershell
# 1. 소스에서 msgid 추출
pybabel extract -F babel.cfg -k _ -k _t -o src/assetcache/web/locale/messages.pot .
```

```powershell
# 2. 새 언어 카탈로그 생성 (예: 일본어)
pybabel init -i src/assetcache/web/locale/messages.pot -d src/assetcache/web/locale -l ja
```

3. `src/assetcache/web/locale/ja/LC_MESSAGES/messages.po` 의 msgstr 채우기

```powershell
# 4. 컴파일
pybabel compile -d src/assetcache/web/locale
```

추가로 `src/assetcache/web/i18n.py` 의 `SUPPORTED_LOCALES` 튜플
(`locale_middleware.py` 가 같은 값을 alias import) 과
`Config` 의 `_VALID_UI_LANGUAGES` 에 새 언어 코드를 추가.

## 라이선스

MIT (변경될 수 있음).
