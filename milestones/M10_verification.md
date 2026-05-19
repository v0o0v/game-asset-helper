# M10 — PyPI + AssetCacheMCP rename 검증

본 문서는 M10 의 자동 검증(테스트 결과)과 사용자 수동 검증 시나리오를 모은다.
Phase 4 (PyPI 빌드 + 배포) 이후 시나리오 6/7 의 실제 결과까지 채우면 완료된다.

## 1. 자동 검증

### 1.1 회귀 (Phase 0~3 누적)

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ **1103 passed + 1 skipped + 40 deselected** (baseline 1046 + M10 Phase 0 회귀 + Phase 1 +37 + Phase 2 +10 + Phase 3 +10).

내역:

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — rename mechanical | `src/gah/` → `src/assetcache/` + 모든 import / config / babel.cfg / spec / docs 경로 | 0 (회귀만) |
| 1 — 마이그레이션 helper | `migration/detect.py` + `migration/migrate.py` (copy/move + `.migrated_from_v001` 마커) + 웹 배너 + SSE 진행률 + CLI `--migrate=copy\|move` + i18n msgid 10건 | +37 |
| 2 — PyPI 알림 (M9 cherry-pick) | `updater/version.py` + `updater/checker.py` + `updater/pip_command.py` + `web/routers/updates.py` 단순화 + `_pypi_update_banner.html` + tray Signal + i18n msgid 4건 | +10 |
| 3 — docs + i18n catalog + verification | docs 4 파일 일괄 갱신 + `tests/test_locale_assetcache_msgid.py` (5 × 2 = 10 instance) + 본 문서 | +10 |
| **M10 Phase 0~3 전체** | **MCP 20 도구 그대로, 신규 의존성 0** | **+57** |

### 1.2 MCP integration (옵트인)

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -m mcp_integration -v
```

→ **2 passed** (`python -m assetcache --mcp` subprocess 가 정상 stdio JSON-RPC 응답 + tools/list 가 **20 도구** 반환).

### 1.3 Phase 4 빌드 / 설치 (자동 가능 부분)

자동 가능 항목 (Task 4.1~4.4, 2026-05-19 검증):

- `python -m build` 결과: ✅ `dist/assetcache_mcp-0.1.0-py3-none-any.whl` (298 KB) + `dist/assetcache_mcp-0.1.0.tar.gz` (385 KB) 정상 빌드
- 별도 venv (`$env:TEMP\smoke-venv`) wheel install: ✅ assetcache-mcp 0.1.0 + 모든 의존성 (torch 2.12.0, PySide6 6.11.1, mcp 1.27.1, fastapi 0.136.1, librosa 0.11.0 등) 설치 성공
- `assetcache.exe --version`: ✅ `assetcache-mcp 0.1.0` 출력
- `main_mcp()` 함수 dispatch 검증: ✅ monkeypatched run_stdio 1회 호출 + rc 0 + log `version=0.1.0` 확인 (실제 `assetcache-mcp.exe` 는 stdio 서버이므로 `--version`/`--help` 무관 — `main(["--mcp"])` 진입만 검증 가능)

자동 가능 항목 (Task 4.5, 2026-05-20 검증):

- TestPyPI 업로드: ✅ `twine upload --repository testpypi dist\*` 성공 — https://test.pypi.org/project/assetcache-mcp/0.1.0/
- 별도 venv (`$env:TEMP\tpypi-smoke-venv`) 에서 `pip install --no-deps --index-url https://test.pypi.org/simple/ assetcache-mcp`: ✅ `Successfully installed assetcache-mcp-0.1.0`
- module import: ✅ `python -c "import assetcache; print(assetcache.__version__)"` → `0.1.0`
- `pip show assetcache-mcp` 메타데이터: ✅ Name/Version/Summary/Home-page/Author-email/License/Requires(22 deps) 모두 정상
- ⚠️ 의존성 resolve 검증 (`--index-url ... --extra-index-url https://pypi.org/simple/`) 은 TestPyPI 의 `--index-url` 우선 매칭으로 일부 sdist build 실패 (FileNotFoundError: DESCRIPTION.txt) — 정식 PyPI 업로드 후 시나리오 7 의 두 번째 단계에서 본격 검증 예정

수동 가능 항목 (Task 4.6, 사용자 직접):

- 정식 PyPI 업로드 후 `pipx install assetcache-mcp` 결과 (시나리오 7 마지막 두 체크박스)
- GitHub Actions workflow tag push 자동 빌드 결과 (`PYPI_API_TOKEN` secret 등록 후)

## 2. 수동 검증 (사용자 직접)

수동 검증은 Phase 4 이전에도 시나리오 1~5 까지는 가능. 시나리오 6/7 은 Phase 4 (PyPI 배포) 이후.

### 시나리오 1 — Phase 0 rename 회귀 (mechanical 검증)

기존 v0.0.1 사용자 데이터에 영향을 주지 않으면서 새 패키지명으로 부팅되는지 확인.

- [ ] PowerShell venv 활성화

  ```powershell
  & "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
  ```

- [ ] 작업 폴더로 이동

  ```powershell
  cd D:\ClaudeCowork\game-asset-helper\game-asset-helper\.claude\worktrees\brave-tesla-80fb0e
  ```

- [ ] 트레이 모드 부팅

  ```powershell
  python -m assetcache --tray
  ```

  → 기대: 트레이 아이콘 정상 등장 + 브라우저 `http://127.0.0.1:9874/library` 자동 열림 + 라이브러리 페이지의 title/header 가 "AssetCacheMCP" 로 표시.

- [ ] MCP stdio 모드 부팅

  ```powershell
  python -m assetcache --mcp
  ```

  → 기대: stdio 가 열린 채 대기. 외부 stdin 으로 JSON-RPC `tools/list` 보냈을 때 **20 도구** 응답.

- [ ] 버전 확인

  ```powershell
  python -m assetcache --version
  ```

  → 기대: `assetcache-mcp 0.1.0` 출력 (Phase 4 Task 4.1 에서 version 0.1.0 확정).

### 시나리오 2 — 마이그레이션 copy (v0.0.1 → AssetCacheMCP)

- [ ] 가짜 v0.0.1 데이터 준비

  ```powershell
  New-Item -ItemType Directory -Force -Path "$env:APPDATA\GameAssetHelper\library\test_pack"
  ```

  ```powershell
  Set-Content -Path "$env:APPDATA\GameAssetHelper\library\test_pack\dummy.png" -Value "dummy"
  ```

- [ ] `%APPDATA%\AssetCacheMCP\` 가 비어있음 확인

  ```powershell
  Test-Path "$env:APPDATA\AssetCacheMCP"
  ```

  → False 또는 비어있으면 OK. 존재하면 백업 후 삭제:

  ```powershell
  Remove-Item -Recurse -Force "$env:APPDATA\AssetCacheMCP"
  ```

- [ ] 트레이 부팅 + 웹 UI 열기 → 라이브러리 페이지 상단에 노란 마이그레이션 배너가 떠야 함 (파일 수 + 크기 표시)
- [ ] 배너의 `[복사]` 버튼 클릭 → SSE progress 바 진행 → 완료 알림
- [ ] 새 폴더 데이터 확인

  ```powershell
  Get-ChildItem -Recurse "$env:APPDATA\AssetCacheMCP\library"
  ```

  → `test_pack/dummy.png` 가 보여야 함

- [ ] 구 폴더 보존 확인 (copy 이므로)

  ```powershell
  Test-Path "$env:APPDATA\GameAssetHelper\library\test_pack\dummy.png"
  ```

  → True

- [ ] `.migrated_from_v001` 마커 확인

  ```powershell
  Test-Path "$env:APPDATA\AssetCacheMCP\.migrated_from_v001"
  ```

  → True

- [ ] 재부팅 (트레이 종료 후 다시 `python -m assetcache --tray`) → 배너 안 뜸 (마커 효과)

### 시나리오 3 — 마이그레이션 move

- [ ] `%APPDATA%\AssetCacheMCP` 삭제 (시나리오 2 재시작)

  ```powershell
  Remove-Item -Recurse -Force "$env:APPDATA\AssetCacheMCP"
  ```

- [ ] 트레이 부팅 → 배너 다시 노출
- [ ] `[이동]` 버튼 클릭 → progress → 완료
- [ ] 구 폴더가 사라졌는지 확인

  ```powershell
  Test-Path "$env:APPDATA\GameAssetHelper\library"
  ```

  → False (또는 `.migrated_to_assetcachemcp` 마커만 남음)

- [ ] 새 폴더에 데이터 확인

  ```powershell
  Get-ChildItem -Recurse "$env:APPDATA\AssetCacheMCP\library"
  ```

  → `test_pack/dummy.png` 가 보여야 함

### 시나리오 4 — PyPI 알림 (배너 + tray)

- [ ] checker 의 cache 조작 또는 `pyproject.toml` 의 version 을 `0.0.0` 으로 한 번만 일시 변경
- [ ] 트레이 부팅 → 라이브러리 페이지 상단에 파란 PyPI 업데이트 배너 노출 (`v{version} update available →`)
- [ ] 배너의 `[복사]` 클릭 → 클립보드에 `pipx upgrade assetcache-mcp` (또는 환경에 따라 `uv tool upgrade assetcache-mcp` / `pip install -U assetcache-mcp`) 가 복사됨
- [ ] 트레이 아이콘 우클릭 → 동적 업데이트 메뉴 항목 노출
- [ ] 메뉴 클릭 → 시스템 트레이 알림 + 클립보드 복사

### 시나리오 5 — CLI `--migrate=copy`

헤드리스 환경 또는 GUI 부팅 없이 마이그레이션:

- [ ] `%APPDATA%\AssetCacheMCP` 삭제 (시나리오 재시작)

  ```powershell
  Remove-Item -Recurse -Force "$env:APPDATA\AssetCacheMCP"
  ```

- [ ] CLI 실행

  ```powershell
  python -m assetcache --migrate=copy
  ```

  → 기대: exit 0 + stdout 에 "Migration complete" 또는 동등한 메시지 + 새 폴더에 데이터 복사 + 구 폴더 보존

- [ ] move 도 동일하게

  ```powershell
  python -m assetcache --migrate=move
  ```

### 시나리오 6 — wheel local smoke (Phase 4 후)

- [ ] Phase 4 의 `python -m build` 로 dist/ 생성

  ```powershell
  python -m build
  ```

- [ ] 별도 새 venv 생성

  ```powershell
  python -m venv $env:USERPROFILE\.venvs\assetcache-smoke
  ```

  ```powershell
  & "$env:USERPROFILE\.venvs\assetcache-smoke\Scripts\Activate.ps1"
  ```

- [ ] wheel 설치

  ```powershell
  pip install (Get-ChildItem dist\assetcache_mcp-*-py3-none-any.whl | Select-Object -First 1).FullName
  ```

- [ ] CLI 동작 확인

  ```powershell
  assetcache --version
  ```

  → 기대: `0.1.0` 출력

  ```powershell
  assetcache --tray
  ```

  → 기대: 트레이 정상 부팅 + 웹 UI 열림

### 시나리오 7 — TestPyPI + 정식 PyPI install (Phase 4 후)

- [x] TestPyPI 업로드 (2026-05-20)

  ```powershell
  python -m twine upload --repository testpypi --non-interactive --disable-progress-bar dist\*
  ```

  → 결과: ✅ `Uploading assetcache_mcp-0.1.0-py3-none-any.whl` + `Uploading assetcache_mcp-0.1.0.tar.gz` + `View at: https://test.pypi.org/project/assetcache-mcp/0.1.0/`

- [x] 새 환경에서 TestPyPI 설치 (2026-05-20, `--no-deps` 모드)

  ```powershell
  pip install --no-deps --index-url https://test.pypi.org/simple/ assetcache-mcp
  ```

  → 결과: ✅ `Successfully installed assetcache-mcp-0.1.0` + `python -c "import assetcache; print(assetcache.__version__)"` → `0.1.0`

  ⚠️ `--extra-index-url=https://pypi.org/simple/` 로 의존성 정상 resolve 는 TestPyPI 의 `--index-url` 우선 매칭으로 fail (일부 의존성이 TestPyPI 의 sdist 만 받아져서 `DESCRIPTION.txt` build error). 의존성 resolve 검증은 정식 PyPI 업로드 후 가능.

- [ ] 정식 PyPI 업로드

  ```powershell
  python -m twine upload dist\*
  ```

- [ ] 정식 PyPI 설치

  ```powershell
  pipx install assetcache-mcp
  ```

  → 기대: `assetcache --tray` 정상 + Claude Desktop config 의 `python -m assetcache --mcp` 또는 `assetcache-mcp` console_script 동작

## 3. 알려진 한계

- **Claude Desktop config 자동 마이그레이션 X** — v0.0.1 사용자가 Claude Desktop 의 `mcpServers` 설정에서 `python -m gah --mcp` 를 직접 `python -m assetcache --mcp` 로 갱신해야 한다. release notes 와 README 의 마이그레이션 섹션에 명시.
- **Mac / Linux 검증 X** — M10 은 Windows 10 환경에서만 검증. cross-platform 동작은 PyPI 흐름에서 가능하지만 별도 마일스톤 (M11+) 에서 정식 검증.
- **마이그레이션 idempotency** — `.migrated_from_v001` 마커로 1회만 동작. 사용자가 마커를 수동 삭제하면 재실행 가능.
- **`%APPDATA%\GameAssetHelper\` 의 비표준 파일** — 마이그레이션은 알려진 디렉터리 (library, cache, metadata.db, config.toml, logs) 만 옮긴다. 사용자가 임의로 둔 파일은 별도 안내 없음.
- **트레이 PyPI 알림의 환경 감지** — pipx / uv / pip 구분은 `sys.argv[0]` + `os.environ` 기반 휴리스틱. 비표준 설치 (예: editable install in venv) 는 `pip install -U` 로 폴백.
- **PyPI checker 의 cache TTL** — 24h 캐시. 사용자가 즉시 재확인을 원하면 `%APPDATA%\AssetCacheMCP\update_cache.json` 수동 삭제.
- **SignPath 코드 서명 X** — Option B 로 보류. PyPI 배포에는 코드 서명이 불필요하지만 exe 2차 배포는 SmartScreen 차단 잔존. release notes 의 차단 해제 안내 유지.
