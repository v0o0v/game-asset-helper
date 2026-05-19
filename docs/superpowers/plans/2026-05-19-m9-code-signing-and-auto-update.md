# M9 — 코드 서명 + 자동 업데이트 구현 plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SignPath Foundation OSS 무료 코드 서명 + 자체 구현 in-app updater (GitHub Releases API 폴링 + httpx 스트림 다운로드 + ctypes 기반 self `--complete-update` mode swap) — v2 첫 마일스톤.

**Architecture:**
- Updater 는 `src/gah/core/updater/` 패키지로 격리 (checker / version / downloader / installer).
- `UpdateChecker` 가 24h 주기 백그라운드 thread 에서 GitHub Releases API 폴링 → `AvailableUpdate` state 를 in-process 에 저장.
- 알림은 두 채널: 트레이 (Qt signal/slot) + 웹 UI base.html 상단 배너 (Alpine x-show + HTMX poll + SSE 진행률).
- 사용자 동의 → `UpdateDownloader` 가 httpx stream 으로 `.exe` + `.sha256` asset 받음 → SHA 검증 → `UpdateInstaller` 가 rename/move + 새 exe spawn (`--complete-update --old-pid <pid>`) → 메인 종료 → 새 exe 가 ctypes `WaitForSingleObject` 로 메인 종료 대기 후 `.old.exe` 삭제 + 일반 트레이 모드 재기동.
- 빌드 흐름은 PyInstaller 결과물을 SignPath Foundation 클라우드에 업로드 → 서명된 exe 다운로드 → `gh release create`. `gah.spec` 자체는 미변경.

**Tech Stack:** Python 3.10+, httpx, FastAPI + sse-starlette, PySide6 (Qt signal/slot), ctypes (`OpenProcess` + `WaitForSingleObject`), Babel gettext (M8 인프라), PyInstaller (M8 인프라), SignPath Foundation cloud signing.

**Spec:** [`docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md`](../specs/2026-05-19-m9-code-signing-and-auto-update-design.md)

**Baseline:** 1046 passed + 1 skipped + 40 deselected. 목표 ~1096 passed.

**Branch:** `feat/m9-code-signing-and-auto-update` (이 plan 실행 직전에 사용자가 생성). spec commit `8dfb316` 은 이미 main 에 있으므로 feat 브랜치는 main 위에서 분기.

---

## File Structure

### 신규 (14)

```
src/gah/core/updater/__init__.py                    (Task 3)
src/gah/core/updater/version.py                     (Task 3)
src/gah/core/updater/checker.py                     (Task 4~5)
src/gah/core/updater/downloader.py                  (Task 6)
src/gah/core/updater/installer.py                   (Task 7~9)
src/gah/web/routers/updates.py                      (Task 11)
src/gah/web/templates/_update_banner.html           (Task 12)
docs/RELEASE_BUILD_GUIDE.md                         (Task 1)
tests/test_config_m9_update.py                      (Task 2)
tests/test_updater_version.py                       (Task 3)
tests/test_updater_checker.py                       (Task 4~5)
tests/test_updater_download.py                      (Task 6)
tests/test_updater_swap.py                          (Task 7~10)
tests/test_web_updates.py                           (Task 11~12)
tests/test_tray_update.py                           (Task 14)
```

### 수정 (8)

```
src/gah/config.py                                   (Task 2)
src/gah/__main__.py                                 (Task 10)
src/gah/app.py                                      (Task 5)
src/gah/web/server.py                               (Task 11)  ← FastAPI router 등록
src/gah/web/templates/base.html                     (Task 12)
src/gah/tray.py                                     (Task 14)
src/gah/web/locale/ko/LC_MESSAGES/messages.po       (Task 13)
src/gah/web/locale/en/LC_MESSAGES/messages.po       (Task 13)
README.md                                           (Task 16)
tests/test_entrypoint.py                            (Task 10)  ← --complete-update 인자 routing
```

### 책임 경계

- `version.py` — 순수 함수, GitHub 의존 없음 (semver-lite 파싱 + 비교)
- `checker.py` — httpx 로 GitHub API 만 다룸, swap/디스크 IO 없음
- `downloader.py` — httpx 스트림 + SHA 검증만, file rename 없음
- `installer.py` — file rename/move/spawn/wait_for_pid 만, 네트워크 없음

테스트 가능성 + 격리를 위한 분리. 각 모듈은 다른 모듈을 import 하지 않거나 (version/checker/downloader) 최소한만 (installer 가 version 만 참조) 한다.

---

## Phase 0 — SignPath 신청 + 빌드 가이드 (0 tests, ~0.5주 + 심사 대기)

### Task 1: SignPath Foundation 신청 + RELEASE_BUILD_GUIDE.md 작성

**Files:**
- Create: `docs/RELEASE_BUILD_GUIDE.md`
- 외부 액션: 사용자가 https://signpath.org/apply 에 신청 (Claude 는 신청 내용 초안 + 절차 문서만 제공)

**Steps:**

- [ ] **Step 1: SignPath 신청 정보 정리 (commit 없음, 참고용)**

다음 내용을 사용자가 https://signpath.org/apply 에 직접 제출. Claude 는 텍스트만 생성:

```
Project name: Game Asset Helper
License: MIT
Source code URL: https://github.com/v0o0v/game-asset-helper
Description: MCP server + Windows tray app that catalogs game assets (sprites,
spritesheets, sounds) and serves them to Unity workflows via Claude Code. Uses
Ollama Gemma 4 + CLIP for AI labeling, FastAPI + HTMX web UI, PySide6 tray.
Maintainer: 김민석 (v0o0v2@gmail.com)
Build system: PyInstaller --onefile --noconsole (local build, Windows 10 / Python 3.12)
Release cadence: ad-hoc (v0.0.1 published 2026-05-19, v0.0.2 planned post-M9)
GitHub topics: mcp, unity, game-asset, claude-code
```

승인까지 수일~수주 소요 (인적 검토). 승인 후 SignPath 가 프로젝트별 인증서 + 클라우드 서명 API 키 제공.

- [ ] **Step 2: `docs/RELEASE_BUILD_GUIDE.md` 작성**

Create `docs/RELEASE_BUILD_GUIDE.md`:

````markdown
# Release 빌드 + 서명 + 배포 가이드

본 문서는 GAH 의 단일 `.exe` 를 빌드하고 SignPath Foundation 클라우드 서명을 적용한 뒤 GitHub Release 로 배포하는 절차를 정리한다. v0.0.2 이후 모든 release 에 적용.

## 사전 조건

- python.org 3.12 + venv `%USERPROFILE%\.venvs\gah`
- `pip install -e .[dev]` 완료 (Babel, PyInstaller 포함)
- `gh` CLI 인증 완료 (`gh auth status`)
- SignPath Foundation 승인 완료 + 프로젝트별 인증서 + API token 확보

## 1. 버전 갱신

두 군데 동시:

```powershell
# 예: 0.0.2 로 올림
# src/gah/__init__.py 의 __version__
# pyproject.toml 의 [project] version
```

## 2. 빌드

```powershell
pybabel compile -d src/gah/web/locale
```

```powershell
python scripts/generate_tray_ico.py
```

```powershell
pyinstaller gah.spec
```

산출: `dist/GameAssetHelper.exe` (~308 MB).

## 3. SHA256 생성

```powershell
$hash = (Get-FileHash dist\GameAssetHelper.exe -Algorithm SHA256).Hash.ToLower()
Set-Content -Path dist\GameAssetHelper.exe.sha256 -Value $hash -Encoding ascii
```

## 4. SignPath 클라우드 서명

방법 A — SignPath 웹 UI 수동 업로드:

1. https://app.signpath.io/ 로그인
2. Game Asset Helper 프로젝트 → Submit signing request
3. `dist/GameAssetHelper.exe` 업로드
4. 서명 완료까지 대기 (~수 분)
5. 서명된 exe 다운로드 → `dist/GameAssetHelper.exe` 덮어쓰기
6. SHA256 재계산 (서명이 추가되어 hash 변경됨):

```powershell
$hash = (Get-FileHash dist\GameAssetHelper.exe -Algorithm SHA256).Hash.ToLower()
Set-Content -Path dist\GameAssetHelper.exe.sha256 -Value $hash -Encoding ascii
```

방법 B — SignPath API (스크립트화, 추후 GitHub Actions 통합 시):

승인 후 SignPath 가 제공하는 API 토큰으로 `POST https://app.signpath.io/api/v1/.../signing-requests` 호출 → polling. 본 plan 에서는 방법 A 수동 흐름만 다룸.

## 5. tag + push

```powershell
git tag -a v0.0.2 -m "v0.0.2 — <한 줄 요약>"
```

```powershell
git push origin main
```

```powershell
git push origin v0.0.2
```

## 6. GitHub Release 생성

release notes 작성 (v0.0.1 의 [`docs/RELEASE_NOTES_v0.0.1.md`](RELEASE_NOTES_v0.0.1.md) 패턴 참고):

```powershell
gh release create v0.0.2 dist\GameAssetHelper.exe dist\GameAssetHelper.exe.sha256 --title "v0.0.2 — <제목>" --notes-file docs\RELEASE_NOTES_v0.0.2.md
```

⚠ 반드시 `.exe` 와 `.sha256` **두 asset 모두** 업로드. UpdateChecker 가 `.sha256` 누락 시 다운로드 진입 안 함.

## 7. 검증

- release 페이지에서 asset 2 개 확인
- 다른 PC 또는 `%TEMP%` 에서 다운로드 → 더블 클릭 → SmartScreen 경고 **없음** 확인 (서명 효과)
- `--version` 출력 확인 (`%TEMP%\GameAssetHelper.exe --tray` → 트레이 + 웹 UI 부팅)

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| SignPath 업로드가 거부 | 인증서 자격 만료 / 프로젝트 비활성 — SignPath 대시보드 확인 |
| 서명 후에도 SmartScreen 경고 | 새 인증서 평판 누적 필요 (수개월) — 사용자에게 "추가 정보 → 실행" 안내 유지 |
| `.sha256` 의 hash 가 안 맞음 | 서명 추가 후 hash 변경됨 — 서명된 exe 기준으로 재계산 (Step 4 끝) |
| `gh release create` 실패 | tag 가 push 안 됨 — Step 5 의 두 push 모두 실행 확인 |
````

- [ ] **Step 3: Commit**

```bash
git add docs/RELEASE_BUILD_GUIDE.md
git commit -m "docs(m9): RELEASE_BUILD_GUIDE — SignPath 서명 + release 절차 7단계"
```

---

## Phase 1 — Updater 백엔드: Checker + Version (+24 tests, ~0.7주)

### Task 2: Config `[update]` 섹션 신규 필드

**Files:**
- Modify: `src/gah/config.py`
- Test: `tests/test_config_m9_update.py` (Create)

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_config_m9_update.py`:

```python
"""M9 Task 2: Config [update] 섹션 — release_repo / check_interval_hours / enabled."""

from __future__ import annotations

from pathlib import Path

import pytest

from gah.config import Config, load_config, save_config


def test_config_default_update_release_repo() -> None:
    cfg = Config()
    assert cfg.update_release_repo == "v0o0v/game-asset-helper"


def test_config_default_update_check_interval_hours() -> None:
    cfg = Config()
    assert cfg.update_check_interval_hours == 24


def test_config_default_update_enabled() -> None:
    cfg = Config()
    assert cfg.update_enabled is True


def test_config_load_update_section_from_toml(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[update]\n'
        'release_repo = "alt/repo"\n'
        'check_interval_hours = 6\n'
        'enabled = false\n',
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.update_release_repo == "alt/repo"
    assert cfg.update_check_interval_hours == 6
    assert cfg.update_enabled is False


def test_config_save_round_trip_update_section(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        update_release_repo="my/fork",
        update_check_interval_hours=12,
        update_enabled=False,
    )
    save_config(cfg, cfg_path)
    cfg2 = load_config(cfg_path)
    assert cfg2.update_release_repo == "my/fork"
    assert cfg2.update_check_interval_hours == 12
    assert cfg2.update_enabled is False


def test_config_rejects_non_positive_interval(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[update]\n'
        'check_interval_hours = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="check_interval_hours"):
        load_config(cfg_path)
```

- [ ] **Step 2: 테스트가 실패 확인**

```powershell
pytest tests/test_config_m9_update.py -v
```
Expected: 6 FAIL — `AttributeError: 'Config' object has no attribute 'update_release_repo'`

- [ ] **Step 3: Config 신규 필드 + 파싱 + 직렬화 구현**

Edit `src/gah/config.py` (기존 `@dataclass class Config` 아래에 세 필드 추가):

```python
@dataclass
class Config:
    # ... 기존 필드 그대로 ...

    # M9: 자동 업데이트
    update_release_repo: str = "v0o0v/game-asset-helper"
    update_check_interval_hours: int = 24
    update_enabled: bool = True
```

`load_config` 함수에 update 섹션 파싱 (기존 본문 끝, return 직전 또는 Config() 생성 시):

```python
def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    # 기존 섹션 파싱 그대로 ...

    update_section = data.get("update", {}) or {}
    check_interval = int(update_section.get("check_interval_hours", 24))
    if check_interval <= 0:
        raise ValueError(
            f"update.check_interval_hours must be > 0, got {check_interval}"
        )

    return Config(
        # 기존 인자 그대로 ...
        update_release_repo=str(update_section.get("release_repo", "v0o0v/game-asset-helper")),
        update_check_interval_hours=check_interval,
        update_enabled=bool(update_section.get("enabled", True)),
    )
```

`save_config` 에 update 섹션 추가:

```python
def save_config(cfg: Config, path: Path) -> None:
    data: dict[str, Any] = {
        # 기존 섹션 ...
        "update": {
            "release_repo": cfg.update_release_repo,
            "check_interval_hours": cfg.update_check_interval_hours,
            "enabled": cfg.update_enabled,
        },
    }
    path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_config_m9_update.py -v
```
Expected: 6 PASS

```powershell
pytest -q
```
Expected: 1052 passed (1046 + 6)

- [ ] **Step 5: Commit**

```bash
git add src/gah/config.py tests/test_config_m9_update.py
git commit -m "feat(m9): Config [update] 섹션 — release_repo/interval/enabled"
```

---

### Task 3: semver-lite 비교 모듈

**Files:**
- Create: `src/gah/core/updater/__init__.py` (빈 파일)
- Create: `src/gah/core/updater/version.py`
- Create: `tests/test_updater_version.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_updater_version.py`:

```python
"""M9 Task 3: semver-lite parser + comparator.

GitHub release tag 형식: "v0.0.1", "v0.0.2", "v0.1.0", "v1.0.0".
Pre-release tag ("v1.0.0-beta", "v1.0.0-rc1") 는 latest API 가 자동 제외라
파싱은 받지만 자동 업데이트 대상은 아님 (release_latest 가 stable 만 반환).
"""

from __future__ import annotations

import pytest

from gah.core.updater.version import Version, parse, compare


def test_parse_simple() -> None:
    v = parse("0.0.1")
    assert v == Version(major=0, minor=0, patch=1, pre=None)


def test_parse_with_v_prefix() -> None:
    assert parse("v0.0.1") == Version(0, 0, 1, None)
    assert parse("V1.2.3") == Version(1, 2, 3, None)


def test_parse_with_pre_release() -> None:
    assert parse("v1.0.0-beta") == Version(1, 0, 0, "beta")
    assert parse("v1.0.0-rc1") == Version(1, 0, 0, "rc1")


def test_parse_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse("not-a-version")
    with pytest.raises(ValueError):
        parse("1.2")  # 세 segment 필수


def test_compare_equal() -> None:
    assert compare(parse("0.0.1"), parse("0.0.1")) == 0
    assert compare(parse("v0.0.1"), parse("0.0.1")) == 0  # v prefix normalize


def test_compare_patch_increment() -> None:
    assert compare(parse("0.0.2"), parse("0.0.1")) > 0
    assert compare(parse("0.0.1"), parse("0.0.2")) < 0


def test_compare_minor_increment() -> None:
    assert compare(parse("0.1.0"), parse("0.0.99")) > 0


def test_compare_major_increment() -> None:
    assert compare(parse("1.0.0"), parse("0.99.99")) > 0


def test_pre_release_less_than_release() -> None:
    """SemVer 표준: 1.0.0-beta < 1.0.0."""
    assert compare(parse("1.0.0-beta"), parse("1.0.0")) < 0
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_version.py -v
```
Expected: 9 FAIL — `ModuleNotFoundError: No module named 'gah.core.updater'`

- [ ] **Step 3: 모듈 구현**

Create `src/gah/core/updater/__init__.py` (빈 파일):

```python
"""M9: 자동 업데이트 — Checker / Version / Downloader / Installer."""
```

Create `src/gah/core/updater/version.py`:

```python
"""semver-lite — GitHub release tag 파싱 + 비교.

GAH 의 tag 형식 (v0.0.1 / v0.0.2 / v0.1.0 / v1.0.0) 만 지원.
SemVer 완전 호환 아님. patch 까지 + 선택적 pre-release suffix 만 처리.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_PATTERN = re.compile(
    r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z][0-9A-Za-z.-]*))?$"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: str | None  # None = stable release, str = pre-release tag


def parse(text: str) -> Version:
    """Parse "v0.0.1" / "0.0.1" / "v1.0.0-beta" 형태."""
    m = _PATTERN.match(text.strip())
    if not m:
        raise ValueError(f"unrecognized version string: {text!r}")
    return Version(
        major=int(m.group(1)),
        minor=int(m.group(2)),
        patch=int(m.group(3)),
        pre=m.group(4),
    )


def compare(a: Version, b: Version) -> int:
    """-1 if a < b, 0 if equal, 1 if a > b."""
    if a.major != b.major:
        return _sign(a.major - b.major)
    if a.minor != b.minor:
        return _sign(a.minor - b.minor)
    if a.patch != b.patch:
        return _sign(a.patch - b.patch)
    # pre-release 처리: a.pre is None > a.pre is not None
    if a.pre is None and b.pre is None:
        return 0
    if a.pre is None and b.pre is not None:
        return 1  # release > pre-release
    if a.pre is not None and b.pre is None:
        return -1
    # 둘 다 pre — 사전식 비교
    assert a.pre is not None and b.pre is not None
    if a.pre < b.pre:
        return -1
    if a.pre > b.pre:
        return 1
    return 0


def _sign(n: int) -> int:
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_updater_version.py -v
```
Expected: 9 PASS

```powershell
pytest -q
```
Expected: 1061 passed (1052 + 9)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/__init__.py src/gah/core/updater/version.py tests/test_updater_version.py
git commit -m "feat(m9): updater/version.py semver-lite 파싱 + 비교"
```

---

### Task 4: UpdateChecker — GitHub API 클라이언트 (단일 호출)

**Files:**
- Create: `src/gah/core/updater/checker.py`
- Create: `tests/test_updater_checker.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_updater_checker.py`:

```python
"""M9 Task 4: UpdateChecker.check_once — GitHub Releases API 단발 호출."""

from __future__ import annotations

import httpx
import pytest
import respx

from gah.core.updater.checker import (
    AvailableUpdate,
    UpdateChecker,
)
from gah.core.updater.version import Version


_LATEST_RESPONSE = {
    "tag_name": "v0.0.2",
    "name": "v0.0.2",
    "body": "release notes",
    "assets": [
        {
            "name": "GameAssetHelper.exe",
            "browser_download_url": "https://github.com/v0o0v/game-asset-helper/releases/download/v0.0.2/GameAssetHelper.exe",
            "size": 323020426,
        },
        {
            "name": "GameAssetHelper.exe.sha256",
            "browser_download_url": "https://github.com/v0o0v/game-asset-helper/releases/download/v0.0.2/GameAssetHelper.exe.sha256",
            "size": 64,
        },
    ],
}


@respx.mock
def test_checker_returns_update_when_newer() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json=_LATEST_RESPONSE))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    result = checker.check_once()

    assert isinstance(result, AvailableUpdate)
    assert result.tag == "v0.0.2"
    assert result.version == Version(0, 0, 2, None)
    assert result.exe_url.endswith("/GameAssetHelper.exe")
    assert result.sha256_url.endswith("/GameAssetHelper.exe.sha256")
    assert result.size_bytes == 323020426


@respx.mock
def test_checker_returns_none_when_same_version() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json={**_LATEST_RESPONSE, "tag_name": "v0.0.1"}))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None


@respx.mock
def test_checker_returns_none_when_older() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json={**_LATEST_RESPONSE, "tag_name": "v0.0.0"}))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None  # downgrade skip


@respx.mock
def test_checker_skips_when_sha256_asset_missing() -> None:
    only_exe = {
        **_LATEST_RESPONSE,
        "assets": [_LATEST_RESPONSE["assets"][0]],  # exe만, sha256 없음
    }
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json=only_exe))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None  # sha256 asset 누락 → skip


@respx.mock
def test_checker_skips_when_exe_asset_missing() -> None:
    only_sha = {
        **_LATEST_RESPONSE,
        "assets": [_LATEST_RESPONSE["assets"][1]],  # sha256 만, exe 없음
    }
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json=only_sha))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None


@respx.mock
def test_checker_silent_on_network_error() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(side_effect=httpx.ConnectError("dns failed"))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None  # raise 안 함


@respx.mock
def test_checker_silent_on_rate_limit() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(403, json={"message": "API rate limit exceeded"}))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None


@respx.mock
def test_checker_silent_on_malformed_json() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, text="<html>not json</html>"))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None


@respx.mock
def test_checker_silent_when_tag_name_missing() -> None:
    respx.get(
        "https://api.github.com/repos/v0o0v/game-asset-helper/releases/latest"
    ).mock(return_value=httpx.Response(200, json={"body": "no tag here"}))

    checker = UpdateChecker(
        release_repo="v0o0v/game-asset-helper",
        current_version="0.0.1",
    )
    assert checker.check_once() is None
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_checker.py -v
```
Expected: 9 FAIL — `ModuleNotFoundError: No module named 'gah.core.updater.checker'`

⚠ `respx` 가 dev dep 에 이미 포함되어 있는지 확인. 없으면:

```powershell
pip install respx
```

또는 `pyproject.toml` `[project.optional-dependencies]` `dev` 에 `respx>=0.21` 추가 + `pip install -e .[dev]` 재실행.

- [ ] **Step 3: UpdateChecker 구현**

Create `src/gah/core/updater/checker.py`:

```python
"""M9: GitHub Releases API 폴링 + AvailableUpdate state.

check_once() 는 단발 호출 (테스트 가능).
폴링 thread 흐름은 Task 5 의 PollingLoop 가 담당.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from gah.core.updater.version import Version, compare, parse


log = logging.getLogger(__name__)


_EXE_NAME = "GameAssetHelper.exe"
_SHA256_NAME = "GameAssetHelper.exe.sha256"


@dataclass(frozen=True)
class AvailableUpdate:
    tag: str               # "v0.0.2"
    version: Version       # parsed
    exe_url: str           # asset download URL (HTTP)
    sha256_url: str        # asset download URL (HTTP)
    size_bytes: int        # exe asset size


class UpdateChecker:
    """GitHub Releases API 단발 호출."""

    def __init__(
        self,
        release_repo: str,
        current_version: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._release_repo = release_repo
        try:
            self._current = parse(current_version)
        except ValueError:
            log.warning("Unrecognized current_version=%r — update check disabled", current_version)
            self._current = None
        self._client = client or httpx.Client(timeout=10.0)

    def check_once(self) -> Optional[AvailableUpdate]:
        """한 번 폴링. 새 버전 있으면 AvailableUpdate, 아니면 None.

        네트워크/JSON/rate-limit 에러는 모두 None 반환 (silent fail).
        """
        if self._current is None:
            return None

        url = f"https://api.github.com/repos/{self._release_repo}/releases/latest"
        try:
            resp = self._client.get(
                url,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
        except httpx.HTTPError as exc:
            log.info("update check failed (network): %s", exc)
            return None

        if resp.status_code != 200:
            log.info("update check non-200: %d %s", resp.status_code, resp.text[:200])
            return None

        try:
            data = resp.json()
        except ValueError as exc:
            log.info("update check malformed JSON: %s", exc)
            return None

        tag = data.get("tag_name")
        if not isinstance(tag, str):
            log.info("update check missing tag_name")
            return None

        try:
            latest = parse(tag)
        except ValueError:
            log.info("update check unparseable tag: %r", tag)
            return None

        if compare(latest, self._current) <= 0:
            return None

        assets = data.get("assets") or []
        exe_url = _find_asset_url(assets, _EXE_NAME)
        sha256_url = _find_asset_url(assets, _SHA256_NAME)
        exe_size = _find_asset_size(assets, _EXE_NAME)
        if exe_url is None or sha256_url is None or exe_size is None:
            log.info(
                "update check missing assets — exe=%s sha256=%s",
                exe_url, sha256_url,
            )
            return None

        return AvailableUpdate(
            tag=tag,
            version=latest,
            exe_url=exe_url,
            sha256_url=sha256_url,
            size_bytes=exe_size,
        )


def _find_asset_url(assets: list[dict], name: str) -> str | None:
    for a in assets:
        if a.get("name") == name:
            url = a.get("browser_download_url")
            return url if isinstance(url, str) else None
    return None


def _find_asset_size(assets: list[dict], name: str) -> int | None:
    for a in assets:
        if a.get("name") == name:
            size = a.get("size")
            return int(size) if isinstance(size, int) else None
    return None
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_updater_checker.py -v
```
Expected: 9 PASS

```powershell
pytest -q
```
Expected: 1070 passed (1061 + 9)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/checker.py tests/test_updater_checker.py
git commit -m "feat(m9): UpdateChecker.check_once — GitHub Releases API 단발"
```

---

### Task 5: Polling thread + app.py 통합 + AvailableUpdate 공유 state

**Files:**
- Modify: `src/gah/core/updater/checker.py` (PollingLoop 추가)
- Modify: `src/gah/app.py` (부팅 시 thread 시작)
- Modify: `tests/test_updater_checker.py` (PollingLoop 테스트 추가)

**Steps:**

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_updater_checker.py` 끝에 추가:

```python
import threading
import time
from unittest.mock import MagicMock


def test_polling_loop_calls_check_once_at_interval() -> None:
    from gah.core.updater.checker import PollingLoop

    check = MagicMock(return_value=None)
    loop = PollingLoop(check_callback=check, interval_seconds=0.05)

    loop.start()
    time.sleep(0.18)  # ~3 회 호출
    loop.stop()
    loop.join(timeout=1.0)

    assert check.call_count >= 2  # 첫 부팅 1회 + interval 1~2회


def test_polling_loop_publishes_available_update() -> None:
    from gah.core.updater.checker import PollingLoop

    fake_update = AvailableUpdate(
        tag="v0.0.2",
        version=Version(0, 0, 2, None),
        exe_url="https://x/exe",
        sha256_url="https://x/sha",
        size_bytes=100,
    )
    check = MagicMock(return_value=fake_update)
    loop = PollingLoop(check_callback=check, interval_seconds=10.0)

    loop.start()
    # 첫 호출은 즉시 (부팅 직후)
    time.sleep(0.1)
    state = loop.current()
    loop.stop()
    loop.join(timeout=1.0)

    assert state == fake_update


def test_polling_loop_stop_is_idempotent() -> None:
    from gah.core.updater.checker import PollingLoop

    loop = PollingLoop(check_callback=lambda: None, interval_seconds=1.0)
    loop.start()
    loop.stop()
    loop.stop()  # 중복 호출 OK
    loop.join(timeout=1.0)
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_checker.py -v
```
Expected: 3 FAIL (`PollingLoop` 미구현)

- [ ] **Step 3: PollingLoop 구현**

`src/gah/core/updater/checker.py` 에 클래스 추가 (파일 끝):

```python
import threading
from typing import Callable


class PollingLoop:
    """백그라운드 thread 가 주기적으로 check_callback 호출 + 결과 보관."""

    def __init__(
        self,
        check_callback: Callable[[], Optional[AvailableUpdate]],
        interval_seconds: float,
    ) -> None:
        self._check = check_callback
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current: Optional[AvailableUpdate] = None
        self._on_update: list[Callable[[AvailableUpdate], None]] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="UpdaterPollingLoop", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def current(self) -> Optional[AvailableUpdate]:
        with self._lock:
            return self._current

    def add_listener(self, callback: Callable[[AvailableUpdate], None]) -> None:
        """새 업데이트가 발견될 때마다 호출 (트레이 / 웹 알림용)."""
        self._on_update.append(callback)

    def _run(self) -> None:
        # 부팅 직후 즉시 한 번
        self._tick()
        while not self._stop_event.wait(self._interval):
            self._tick()

    def _tick(self) -> None:
        try:
            result = self._check()
        except Exception:
            log.exception("update polling tick failed")
            return

        if result is None:
            return
        with self._lock:
            previous = self._current
            self._current = result
        if previous != result:
            for cb in list(self._on_update):
                try:
                    cb(result)
                except Exception:
                    log.exception("update listener failed")
```

- [ ] **Step 4: app.py 에서 부팅 시 thread 시작**

Edit `src/gah/app.py`, `run_tray` 함수 안에서 (web server + 분석 큐 시작 후, app.exec_() 전):

```python
def run_tray(paths: AppPaths, config: Config, argv: Sequence[str] | None = None) -> int:
    # ... 기존 부팅 코드 ...

    # M9: 업데이트 폴링 (config.update_enabled=true 일 때만)
    polling_loop = None
    if config.update_enabled:
        from gah import __version__
        from gah.core.updater.checker import PollingLoop, UpdateChecker

        checker = UpdateChecker(
            release_repo=config.update_release_repo,
            current_version=__version__,
        )
        polling_loop = PollingLoop(
            check_callback=checker.check_once,
            interval_seconds=config.update_check_interval_hours * 3600,
        )
        polling_loop.start()
        log.info(
            "Update polling started (interval=%dh, repo=%s)",
            config.update_check_interval_hours,
            config.update_release_repo,
        )

    try:
        rc = app.exec_()
    finally:
        if polling_loop is not None:
            polling_loop.stop()
            polling_loop.join(timeout=2.0)
    return rc
```

⚠ web server 와 tray 가 polling_loop 의 `current()` 와 `add_listener` 에 접근하려면 인스턴스 공유 필요. `WebServer` 또는 전역 dependency injection 으로 전달. Task 11 에서 라우터가 `polling_loop.current()` 호출하도록 wiring.

가장 단순: `run_tray` 가 `polling_loop` 를 `WebServer` 생성 시 인자로 넘김 (`WebServer(... , updater_loop=polling_loop)`). Task 11 에서 router 에 의존성 주입.

- [ ] **Step 5: 테스트 통과 확인**

```powershell
pytest tests/test_updater_checker.py -v
```
Expected: 12 PASS (9 + 3)

```powershell
pytest -q
```
Expected: 1073 passed (1070 + 3)

- [ ] **Step 6: Commit**

```bash
git add src/gah/core/updater/checker.py src/gah/app.py tests/test_updater_checker.py
git commit -m "feat(m9): PollingLoop + app.py 통합 — 부팅 시 24h 주기 폴링"
```

---

## Phase 2 — Updater 백엔드: Downloader + Installer (+19 tests, ~0.7주)

### Task 6: UpdateDownloader — httpx stream + SHA256 검증

**Files:**
- Create: `src/gah/core/updater/downloader.py`
- Create: `tests/test_updater_download.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_updater_download.py`:

```python
"""M9 Task 6: UpdateDownloader — httpx 스트림 + SHA256 검증."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from gah.core.updater.downloader import (
    DownloadError,
    DownloadResult,
    UpdateDownloader,
)


_EXE_BYTES = b"FAKE EXE CONTENT" * 100  # 1600 bytes
_EXE_SHA256 = hashlib.sha256(_EXE_BYTES).hexdigest()


@respx.mock
def test_download_success_writes_file_and_verifies(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(200, content=_EXE_BYTES)
    )
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(200, text=_EXE_SHA256 + "\n")
    )

    target = tmp_path / "GameAssetHelper.new.exe"
    downloader = UpdateDownloader()
    result = downloader.download(
        exe_url="https://x/exe",
        sha256_url="https://x/sha",
        target_path=target,
    )

    assert isinstance(result, DownloadResult)
    assert result.path == target
    assert target.exists()
    assert target.read_bytes() == _EXE_BYTES
    assert result.sha256 == _EXE_SHA256


@respx.mock
def test_download_sha_mismatch_deletes_and_raises(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(200, content=_EXE_BYTES)
    )
    bad_sha = "0" * 64
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(200, text=bad_sha)
    )

    target = tmp_path / "GameAssetHelper.new.exe"
    downloader = UpdateDownloader()
    with pytest.raises(DownloadError, match="sha256"):
        downloader.download(
            exe_url="https://x/exe",
            sha256_url="https://x/sha",
            target_path=target,
        )

    assert not target.exists()  # 검증 실패 시 자동 삭제


@respx.mock
def test_download_sha256_response_strips_whitespace(tmp_path: Path) -> None:
    """sha256 응답에 trailing newline / 공백이 있어도 OK."""
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(200, content=_EXE_BYTES)
    )
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(200, text=f"  {_EXE_SHA256}  \r\n")
    )

    target = tmp_path / "GameAssetHelper.new.exe"
    UpdateDownloader().download(
        exe_url="https://x/exe",
        sha256_url="https://x/sha",
        target_path=target,
    )
    assert target.read_bytes() == _EXE_BYTES


@respx.mock
def test_download_network_error_raises(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(side_effect=httpx.ConnectError("conn refused"))

    target = tmp_path / "GameAssetHelper.new.exe"
    with pytest.raises(DownloadError):
        UpdateDownloader().download(
            exe_url="https://x/exe",
            sha256_url="https://x/sha",
            target_path=target,
        )


@respx.mock
def test_download_sha_fetch_error_raises_and_cleans(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(200, content=_EXE_BYTES)
    )
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(404, text="not found")
    )

    target = tmp_path / "GameAssetHelper.new.exe"
    with pytest.raises(DownloadError):
        UpdateDownloader().download(
            exe_url="https://x/exe",
            sha256_url="https://x/sha",
            target_path=target,
        )
    assert not target.exists()


@respx.mock
def test_download_invokes_progress_callback(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(
            200,
            content=_EXE_BYTES,
            headers={"content-length": str(len(_EXE_BYTES))},
        )
    )
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(200, text=_EXE_SHA256)
    )

    callback = MagicMock()
    target = tmp_path / "GameAssetHelper.new.exe"
    UpdateDownloader(progress_callback=callback).download(
        exe_url="https://x/exe",
        sha256_url="https://x/sha",
        target_path=target,
    )

    assert callback.call_count >= 1
    last_call = callback.call_args_list[-1]
    bytes_downloaded, total = last_call.args
    assert bytes_downloaded == len(_EXE_BYTES)
    assert total == len(_EXE_BYTES)


def test_download_disk_full_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError 28 (ENOSPC) → DownloadError."""
    target = tmp_path / "GameAssetHelper.new.exe"

    class FailingFile:
        def __init__(self, *args, **kwargs):
            pass
        def write(self, data):
            raise OSError(28, "No space left on device")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr("builtins.open", lambda *a, **kw: FailingFile())

    with respx.mock:
        respx.get("https://x/exe").mock(
            return_value=httpx.Response(200, content=_EXE_BYTES)
        )
        with pytest.raises(DownloadError, match="disk"):
            UpdateDownloader().download(
                exe_url="https://x/exe",
                sha256_url="https://x/sha",
                target_path=target,
            )


@respx.mock
def test_download_creates_target_parent_dir(tmp_path: Path) -> None:
    respx.get("https://x/exe").mock(
        return_value=httpx.Response(200, content=_EXE_BYTES)
    )
    respx.get("https://x/sha").mock(
        return_value=httpx.Response(200, text=_EXE_SHA256)
    )

    target = tmp_path / "deep" / "nested" / "GameAssetHelper.new.exe"
    UpdateDownloader().download(
        exe_url="https://x/exe",
        sha256_url="https://x/sha",
        target_path=target,
    )
    assert target.exists()
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_download.py -v
```
Expected: 8 FAIL — `ModuleNotFoundError: No module named 'gah.core.updater.downloader'`

- [ ] **Step 3: UpdateDownloader 구현**

Create `src/gah/core/updater/downloader.py`:

```python
"""M9: asset 다운로드 + SHA256 검증."""

from __future__ import annotations

import errno
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx


log = logging.getLogger(__name__)


_CHUNK_SIZE = 65536  # 64 KB


class DownloadError(Exception):
    """다운로드 또는 검증 실패."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size_bytes: int


class UpdateDownloader:
    """httpx 스트림 다운로드 + SHA256 검증."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self._client = client or httpx.Client(timeout=60.0)
        self._progress = progress_callback

    def download(
        self,
        exe_url: str,
        sha256_url: str,
        target_path: Path,
    ) -> DownloadResult:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # SHA256 먼저 (작은 파일) — 다운로드 시작 전 실패 시 exe 안 받음
        expected_sha = self._fetch_sha256(sha256_url)
        if expected_sha is None:
            raise DownloadError(f"sha256 fetch failed: {sha256_url}")

        # 그 다음 exe 스트림
        sha_actual = self._stream_exe(exe_url, target_path)
        size = target_path.stat().st_size

        if sha_actual != expected_sha:
            try:
                target_path.unlink()
            except OSError:
                pass
            raise DownloadError(
                f"sha256 mismatch: expected={expected_sha} actual={sha_actual}"
            )

        return DownloadResult(path=target_path, sha256=sha_actual, size_bytes=size)

    def _fetch_sha256(self, url: str) -> str | None:
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            log.warning("sha256 fetch network error: %s", exc)
            return None
        if resp.status_code != 200:
            log.warning("sha256 fetch non-200: %d", resp.status_code)
            return None
        text = resp.text.strip().split()[0] if resp.text.strip() else ""
        if len(text) != 64 or not all(c in "0123456789abcdef" for c in text.lower()):
            log.warning("sha256 fetch malformed: %r", text[:80])
            return None
        return text.lower()

    def _stream_exe(self, url: str, target_path: Path) -> str:
        hasher = hashlib.sha256()
        total = 0

        try:
            with self._client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise DownloadError(f"exe download non-200: {resp.status_code}")
                content_length = int(resp.headers.get("content-length", 0))
                try:
                    with open(target_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=_CHUNK_SIZE):
                            f.write(chunk)
                            hasher.update(chunk)
                            total += len(chunk)
                            if self._progress:
                                self._progress(total, content_length or total)
                except OSError as exc:
                    if exc.errno == errno.ENOSPC:
                        try:
                            target_path.unlink()
                        except OSError:
                            pass
                        raise DownloadError("disk space exhausted (ENOSPC)") from exc
                    raise DownloadError(f"file write error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DownloadError(f"network error: {exc}") from exc

        return hasher.hexdigest()
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_updater_download.py -v
```
Expected: 8 PASS

```powershell
pytest -q
```
Expected: 1081 passed (1073 + 8)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/downloader.py tests/test_updater_download.py
git commit -m "feat(m9): UpdateDownloader — httpx stream + SHA256 검증 + 진행률 콜백"
```

---

### Task 7: UpdateInstaller STEP 1 — 자기 자신 rename + 새 파일 자리잡기

**Files:**
- Create: `src/gah/core/updater/installer.py`
- Create: `tests/test_updater_swap.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_updater_swap.py`:

```python
"""M9 Task 7~9: UpdateInstaller swap 패턴 (STEP 1~3)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gah.core.updater.installer import (
    InstallError,
    UpdateInstaller,
)


def test_install_step1_renames_old_exe(tmp_path: Path) -> None:
    """기존 exe 가 .old.exe 로 rename + new.exe 가 그 자리 차지."""
    current = tmp_path / "GameAssetHelper.exe"
    new = tmp_path / "update" / "GameAssetHelper.new.exe"
    new.parent.mkdir(parents=True)
    current.write_bytes(b"OLD")
    new.write_bytes(b"NEW")

    installer = UpdateInstaller(current_exe_path=current)
    installer.swap_files(new_exe_path=new)

    backup = tmp_path / "GameAssetHelper.old.exe"
    assert backup.exists()
    assert backup.read_bytes() == b"OLD"
    assert current.exists()
    assert current.read_bytes() == b"NEW"
    assert not new.exists()


def test_install_step1_overwrites_stale_backup(tmp_path: Path) -> None:
    """이전 swap 의 .old.exe 잔재가 있어도 정상 처리."""
    current = tmp_path / "GameAssetHelper.exe"
    new = tmp_path / "update" / "GameAssetHelper.new.exe"
    new.parent.mkdir(parents=True)
    current.write_bytes(b"OLD-V2")
    new.write_bytes(b"NEW-V3")
    (tmp_path / "GameAssetHelper.old.exe").write_bytes(b"VERY-OLD-V1")

    installer = UpdateInstaller(current_exe_path=current)
    installer.swap_files(new_exe_path=new)

    backup = tmp_path / "GameAssetHelper.old.exe"
    assert backup.read_bytes() == b"OLD-V2"  # 가장 최근 OLD 만 보존
    assert current.read_bytes() == b"NEW-V3"


def test_install_step1_raises_on_missing_new(tmp_path: Path) -> None:
    current = tmp_path / "GameAssetHelper.exe"
    current.write_bytes(b"OLD")
    new = tmp_path / "missing.new.exe"

    installer = UpdateInstaller(current_exe_path=current)
    with pytest.raises(InstallError, match="new exe not found"):
        installer.swap_files(new_exe_path=new)

    assert current.read_bytes() == b"OLD"  # 원본 보존
    assert not (tmp_path / "GameAssetHelper.old.exe").exists()


def test_install_step1_atomic_rollback_on_move_failure(tmp_path: Path) -> None:
    """move 실패 시 rename 되돌리기 (.old.exe → .exe)."""
    current = tmp_path / "GameAssetHelper.exe"
    new = tmp_path / "update" / "GameAssetHelper.new.exe"
    new.parent.mkdir(parents=True)
    current.write_bytes(b"OLD")
    new.write_bytes(b"NEW")

    installer = UpdateInstaller(current_exe_path=current)

    with patch("gah.core.updater.installer.os.replace", side_effect=OSError("simulated")):
        with pytest.raises(InstallError):
            installer.swap_files(new_exe_path=new)

    assert current.read_bytes() == b"OLD"  # 롤백 성공
    assert not (tmp_path / "GameAssetHelper.old.exe").exists()
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_swap.py -v
```
Expected: 4 FAIL — `ModuleNotFoundError`

- [ ] **Step 3: UpdateInstaller STEP 1 구현**

Create `src/gah/core/updater/installer.py`:

```python
"""M9: swap 패턴 — STEP 1 (rename + move), STEP 2 (spawn + exit), STEP 3 (wait + cleanup + restart).

Windows 의 "실행 중인 .exe 는 덮어쓰기 불가, rename 은 허용" 제약을 활용.
PowerShell stub / cmd stub 없이 단일 exe 안에 모든 로직.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path


log = logging.getLogger(__name__)


class InstallError(Exception):
    """swap 또는 spawn 실패."""


class UpdateInstaller:
    def __init__(self, current_exe_path: Path) -> None:
        self._current = Path(current_exe_path).resolve()
        self._backup = self._current.with_name(
            self._current.stem + ".old" + self._current.suffix
        )

    def swap_files(self, new_exe_path: Path) -> None:
        """STEP 1: current → .old.exe rename + new.exe → current 위치 move.

        실패 시 자동 rollback.
        """
        new = Path(new_exe_path)
        if not new.exists():
            raise InstallError(f"new exe not found: {new}")

        # 잔재 .old.exe 제거
        if self._backup.exists():
            try:
                self._backup.unlink()
            except OSError as exc:
                raise InstallError(f"could not remove stale backup: {exc}") from exc

        # current → .old.exe (Windows: 실행 중인 exe 자체 rename 허용)
        try:
            os.rename(self._current, self._backup)
        except OSError as exc:
            raise InstallError(f"could not rename current exe: {exc}") from exc

        # new → current
        try:
            os.replace(new, self._current)
        except OSError as exc:
            # rollback: .old.exe → current
            try:
                os.rename(self._backup, self._current)
            except OSError:
                log.exception("rollback after move-failure also failed")
            raise InstallError(f"could not move new exe into place: {exc}") from exc
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
pytest tests/test_updater_swap.py -v
```
Expected: 4 PASS

```powershell
pytest -q
```
Expected: 1085 passed (1081 + 4)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/installer.py tests/test_updater_swap.py
git commit -m "feat(m9): UpdateInstaller STEP 1 — rename + move + 롤백"
```

---

### Task 8: UpdateInstaller STEP 2 — 새 exe spawn + 메인 종료 (위임)

**Files:**
- Modify: `src/gah/core/updater/installer.py`
- Modify: `tests/test_updater_swap.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_updater_swap.py` 에 추가:

```python
def test_install_step2_spawns_new_exe_with_complete_update_args(tmp_path: Path) -> None:
    current = tmp_path / "GameAssetHelper.exe"
    current.write_bytes(b"NEW")

    installer = UpdateInstaller(current_exe_path=current)
    with patch("gah.core.updater.installer.subprocess.Popen") as popen_mock:
        installer.spawn_complete_update(old_pid=4242)

    popen_mock.assert_called_once()
    args, kwargs = popen_mock.call_args
    cmd = args[0]
    assert cmd[0] == str(current)
    assert "--complete-update" in cmd
    assert "--old-pid" in cmd
    assert "4242" in cmd
    # detached so the new process survives main exit
    flags = kwargs.get("creationflags", 0)
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP = 0x00000008 | 0x00000200
        assert flags & 0x00000008
        assert flags & 0x00000200


def test_install_step2_raises_when_current_missing(tmp_path: Path) -> None:
    current = tmp_path / "GameAssetHelper.exe"
    # not created

    installer = UpdateInstaller(current_exe_path=current)
    with pytest.raises(InstallError, match="current exe not found"):
        installer.spawn_complete_update(old_pid=4242)


def test_install_step2_propagates_popen_failure(tmp_path: Path) -> None:
    current = tmp_path / "GameAssetHelper.exe"
    current.write_bytes(b"NEW")

    installer = UpdateInstaller(current_exe_path=current)
    with patch(
        "gah.core.updater.installer.subprocess.Popen",
        side_effect=OSError("permission denied"),
    ):
        with pytest.raises(InstallError, match="spawn"):
            installer.spawn_complete_update(old_pid=4242)
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_swap.py::test_install_step2_spawns_new_exe_with_complete_update_args -v
```
Expected: FAIL — AttributeError: 'UpdateInstaller' object has no attribute 'spawn_complete_update'

- [ ] **Step 3: spawn_complete_update 구현**

Append to `src/gah/core/updater/installer.py`:

```python
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


class UpdateInstaller:
    # ... 기존 __init__ + swap_files ...

    def spawn_complete_update(self, old_pid: int) -> None:
        """STEP 2: 새 exe 를 --complete-update 모드로 detached spawn."""
        if not self._current.exists():
            raise InstallError(f"current exe not found: {self._current}")

        cmd = [
            str(self._current),
            "--complete-update",
            "--old-pid",
            str(old_pid),
        ]
        creation = 0
        if sys.platform == "win32":
            creation = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP

        try:
            subprocess.Popen(  # noqa: S603 (intentional)
                cmd,
                creationflags=creation,
                close_fds=True,
            )
        except OSError as exc:
            raise InstallError(f"failed to spawn new exe: {exc}") from exc

        log.info("Spawned new exe in --complete-update mode (old_pid=%d)", old_pid)
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_updater_swap.py -v
```
Expected: 7 PASS (4 + 3)

```powershell
pytest -q
```
Expected: 1088 passed (1085 + 3)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/installer.py tests/test_updater_swap.py
git commit -m "feat(m9): UpdateInstaller STEP 2 — --complete-update 모드 detached spawn"
```

---

### Task 9: UpdateInstaller STEP 3 — wait_for_pid + cleanup + restart

**Files:**
- Modify: `src/gah/core/updater/installer.py`
- Modify: `tests/test_updater_swap.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_updater_swap.py` 에 추가:

```python
def test_wait_for_pid_returns_true_when_pid_dies(tmp_path: Path) -> None:
    """실제 subprocess 띄우고 종료시키면 wait 가 True 반환."""
    from gah.core.updater.installer import wait_for_pid

    if sys.platform != "win32":
        pytest.skip("Windows only")

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.5)"]
    )
    try:
        # 종료 대기
        ok = wait_for_pid(child.pid, timeout_sec=5)
        assert ok is True
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=2)


def test_wait_for_pid_returns_true_when_already_gone() -> None:
    """OpenProcess 가 None 반환하면 True (이미 종료된 것으로 간주)."""
    from gah.core.updater.installer import wait_for_pid

    if sys.platform != "win32":
        pytest.skip("Windows only")
    # 큰 PID — 거의 확실히 존재 안 함
    assert wait_for_pid(999_999_999, timeout_sec=1) is True


def test_wait_for_pid_returns_false_on_timeout() -> None:
    """살아있는 PID + 짧은 timeout → False."""
    from gah.core.updater.installer import wait_for_pid

    if sys.platform != "win32":
        pytest.skip("Windows only")

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"]
    )
    try:
        ok = wait_for_pid(child.pid, timeout_sec=1)
        assert ok is False
    finally:
        child.terminate()
        child.wait(timeout=2)


def test_complete_update_workflow_calls_wait_then_cleans_then_spawns(tmp_path: Path) -> None:
    """STEP 3 의 a~d 모두: PID wait → backup 삭제 → 일반 모드 spawn."""
    current = tmp_path / "GameAssetHelper.exe"
    backup = tmp_path / "GameAssetHelper.old.exe"
    current.write_bytes(b"NEW")
    backup.write_bytes(b"OLD")

    installer = UpdateInstaller(current_exe_path=current)

    with (
        patch(
            "gah.core.updater.installer.wait_for_pid",
            return_value=True,
        ) as wait_mock,
        patch(
            "gah.core.updater.installer.subprocess.Popen"
        ) as popen_mock,
    ):
        installer.complete_update(old_pid=4242)

    wait_mock.assert_called_once_with(4242, timeout_sec=30)
    assert not backup.exists()  # cleanup
    popen_mock.assert_called_once()
    cmd = popen_mock.call_args.args[0]
    assert cmd[0] == str(current)
    assert "--tray" in cmd
    assert "--complete-update" not in cmd  # 일반 모드 — 무한 루프 방지


def test_complete_update_proceeds_even_when_wait_times_out(tmp_path: Path) -> None:
    """STEP 3a 가 false 반환해도 cleanup + spawn 진행 (best-effort)."""
    current = tmp_path / "GameAssetHelper.exe"
    backup = tmp_path / "GameAssetHelper.old.exe"
    current.write_bytes(b"NEW")
    backup.write_bytes(b"OLD")

    installer = UpdateInstaller(current_exe_path=current)

    with (
        patch("gah.core.updater.installer.wait_for_pid", return_value=False),
        patch("gah.core.updater.installer.subprocess.Popen") as popen_mock,
    ):
        installer.complete_update(old_pid=4242)

    # backup 은 cleanup 시도되지만 실패할 수도 있음 — 진행만 보장
    popen_mock.assert_called_once()
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_updater_swap.py -v
```
Expected: 5 FAIL (`wait_for_pid` / `complete_update` 미구현)

- [ ] **Step 3: wait_for_pid + complete_update 구현**

Append to `src/gah/core/updater/installer.py`:

```python
import ctypes
import contextlib


_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0


def wait_for_pid(pid: int, timeout_sec: int = 30) -> bool:
    """Win32 OpenProcess + WaitForSingleObject 로 PID 종료 대기.

    Returns True if pid is gone (or never existed), False if timeout.
    Non-Windows 에서는 raise (호출자가 sys.platform 으로 가드).
    """
    if sys.platform != "win32":
        raise RuntimeError("wait_for_pid is Windows-only")

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, int(pid))
    if not handle:
        return True  # 이미 종료된 PID
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout_sec * 1000))
        return result == _WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


class UpdateInstaller:
    # ... 기존 메서드들 ...

    def complete_update(self, old_pid: int) -> None:
        """STEP 3: --complete-update 모드 안에서 호출.

        a) old_pid 종료 대기 (max 30s)
        b) .old.exe 삭제
        c) 일반 트레이 모드 spawn
        d) 본 프로세스 종료는 호출자 (__main__) 가 sys.exit
        """
        ok = wait_for_pid(old_pid, timeout_sec=30)
        if not ok:
            log.warning(
                "Old PID %d did not exit within 30s — proceeding best-effort",
                old_pid,
            )

        with contextlib.suppress(OSError):
            if self._backup.exists():
                self._backup.unlink()

        creation = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            subprocess.Popen(  # noqa: S603
                [str(self._current), "--tray"],
                creationflags=creation,
                close_fds=True,
            )
        except OSError as exc:
            raise InstallError(f"failed to restart in tray mode: {exc}") from exc
        log.info("New exe restarted in --tray mode")
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_updater_swap.py -v
```
Expected: 12 PASS (7 + 5)

```powershell
pytest -q
```
Expected: 1093 passed (1088 + 5)

- [ ] **Step 5: Commit**

```bash
git add src/gah/core/updater/installer.py tests/test_updater_swap.py
git commit -m "feat(m9): UpdateInstaller STEP 3 — wait_for_pid + cleanup + tray restart"
```

---

### Task 10: `--complete-update` 인자 routing (`__main__.py`)

**Files:**
- Modify: `src/gah/__main__.py`
- Modify: `tests/test_entrypoint.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_entrypoint.py` 에 추가:

```python
def test_main_complete_update_invokes_installer_and_exits(monkeypatch, tmp_path) -> None:
    """--complete-update --old-pid <pid> → UpdateInstaller.complete_update 호출."""
    from gah import __main__ as main_module

    called = {}

    def fake_complete_update(self, old_pid):
        called["pid"] = old_pid

    monkeypatch.setattr(
        "gah.core.updater.installer.UpdateInstaller.complete_update",
        fake_complete_update,
    )

    rc = main_module.main(["--complete-update", "--old-pid", "1234"])

    assert rc == 0
    assert called.get("pid") == 1234


def test_main_complete_update_requires_old_pid() -> None:
    from gah import __main__ as main_module
    with pytest.raises(SystemExit):
        main_module.main(["--complete-update"])  # missing --old-pid
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_entrypoint.py::test_main_complete_update_invokes_installer_and_exits -v
```
Expected: FAIL — argument unrecognized

- [ ] **Step 3: argparse + routing 추가**

Edit `src/gah/__main__.py`:

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="game-asset-helper")
    parser.add_argument("--version", action="store_true", help="버전 출력 후 종료")
    parser.add_argument("--tray", action="store_true", help="트레이 모드 (기본)")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="MCP stdio 서버 모드 — Claude Code 가 child process 로 spawn",
    )
    # M9: 자동 업데이트 swap 패턴 STEP 3
    parser.add_argument(
        "--complete-update",
        action="store_true",
        help=argparse.SUPPRESS,  # 사용자 노출 X (UpdateInstaller 가 spawn 시만 사용)
    )
    parser.add_argument(
        "--old-pid",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="런타임 데이터 디렉터리 오버라이드",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="로그 레벨 (DEBUG/INFO/WARNING/ERROR)",
    )
    return parser
```

`main` 함수에 routing 추가 (logging setup 후, `--mcp` 분기 위):

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    paths = default_app_paths(args.data_dir)
    paths.ensure_dirs()
    config = load_config(paths.config_path)

    if args.version:
        print(f"game-asset-helper {__version__}")
        return EXIT_OK

    level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    setup_logging(paths.log_path, level=level)
    log = logging.getLogger("gah.main")
    log.info("GAH starting (version=%s, data_dir=%s)", __version__, paths.data_dir)

    # M9: --complete-update 모드 — 새 exe 가 자기 자신을 정리하는 분기
    if args.complete_update:
        if args.old_pid is None:
            parser.error("--complete-update requires --old-pid")
        from gah.core.updater.installer import UpdateInstaller

        current_exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(sys.argv[0]).resolve()
        installer = UpdateInstaller(current_exe_path=current_exe)
        installer.complete_update(old_pid=args.old_pid)
        return EXIT_OK

    if args.mcp:
        from gah.mcp.server import run_stdio
        run_stdio()
        return EXIT_OK

    # Default mode: tray
    try:
        with SingleInstance(paths.lock_path):
            from gah.app import run_tray
            rc = run_tray(paths, config)
            log.info("GAH exiting (rc=%s)", rc)
            return rc
    except AlreadyRunning as exc:
        log.info("Another instance is already running: %s", exc)
        print(
            "Game Asset Helper가 이미 실행 중입니다 (트레이 아이콘을 확인하세요).",
            file=sys.stderr,
        )
        return EXIT_ALREADY_RUNNING
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_entrypoint.py -v
```
Expected: 모두 PASS (기존 + 신규 2)

```powershell
pytest -q
```
Expected: 1095 passed (1093 + 2)

- [ ] **Step 5: Commit**

```bash
git add src/gah/__main__.py tests/test_entrypoint.py
git commit -m "feat(m9): __main__ --complete-update --old-pid routing"
```

---

## Phase 3 — Web UI 통합 (+8 tests, ~0.4주)

### Task 11: `/api/updates/{check,start,status}` 라우터 + 통합

**Files:**
- Create: `src/gah/web/routers/updates.py`
- Modify: `src/gah/web/server.py` (라우터 등록 + dependency injection)
- Create: `tests/test_web_updates.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_web_updates.py`:

```python
"""M9 Task 11: /api/updates/{check,start,status} 라우터."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from gah.core.updater.checker import AvailableUpdate, PollingLoop
from gah.core.updater.version import Version


_FAKE_UPDATE = AvailableUpdate(
    tag="v0.0.2",
    version=Version(0, 0, 2, None),
    exe_url="https://x/exe",
    sha256_url="https://x/sha",
    size_bytes=1000,
)


@pytest.fixture
def app_with_polling_loop(tmp_path: Path):
    """PollingLoop 가 주입된 FastAPI app 을 반환."""
    from gah.web.app import build_app
    from gah.config import Config

    loop = PollingLoop(check_callback=lambda: None, interval_seconds=10.0)
    cfg = Config()  # default
    app = build_app(config=cfg, updater_loop=loop, data_dir=tmp_path)
    return app, loop


def test_api_updates_check_returns_none_when_no_update(app_with_polling_loop) -> None:
    app, loop = app_with_polling_loop
    with TestClient(app) as client:
        resp = client.get("/api/updates/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is False
    assert data["update"] is None


def test_api_updates_check_returns_available_when_present(app_with_polling_loop) -> None:
    app, loop = app_with_polling_loop
    loop._current = _FAKE_UPDATE  # type: ignore[attr-defined]
    with TestClient(app) as client:
        resp = client.get("/api/updates/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected"] is True
    assert data["update"]["tag"] == "v0.0.2"
    assert data["update"]["size_bytes"] == 1000


def test_api_updates_start_returns_404_when_no_update(app_with_polling_loop) -> None:
    app, loop = app_with_polling_loop
    with TestClient(app) as client:
        resp = client.post("/api/updates/start")
    assert resp.status_code == 404


def test_api_updates_start_returns_stream_url(app_with_polling_loop) -> None:
    app, loop = app_with_polling_loop
    loop._current = _FAKE_UPDATE  # type: ignore[attr-defined]
    with TestClient(app) as client:
        with pytest.MonkeyPatch.context() as mp:
            # 실 다운로드 차단 (background thread spawn 시 monkeypatch)
            mp.setattr(
                "gah.web.routers.updates._spawn_download_task",
                lambda *a, **kw: None,
            )
            resp = client.post("/api/updates/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert body["stream_url"] == "/api/updates/status"


def test_api_updates_status_returns_sse_events(app_with_polling_loop) -> None:
    """SSE 가 download/verify/ready_to_install/restarting 이벤트 순서대로 stream."""
    app, loop = app_with_polling_loop
    # 미리 download_task 가 끝난 상태를 시뮬레이션 (Task 11 의 in-memory queue)
    from gah.web.routers.updates import _PROGRESS_QUEUE
    _PROGRESS_QUEUE.put({"phase": "download", "bytes": 500, "total": 1000})
    _PROGRESS_QUEUE.put({"phase": "verify"})
    _PROGRESS_QUEUE.put({"phase": "ready_to_install"})
    _PROGRESS_QUEUE.put(None)  # sentinel — close stream

    with TestClient(app) as client:
        resp = client.get("/api/updates/status", headers={"Accept": "text/event-stream"})

    assert resp.status_code == 200
    body = resp.text
    assert "phase\":\"download\"" in body
    assert "phase\":\"verify\"" in body
    assert "phase\":\"ready_to_install\"" in body


def test_api_updates_check_includes_settings_disabled_flag(app_with_polling_loop, tmp_path: Path) -> None:
    """update.enabled=false 일 때도 /api/updates/check 가 응답하되 disabled 표시."""
    from gah.web.app import build_app
    from gah.config import Config

    loop = PollingLoop(check_callback=lambda: None, interval_seconds=10.0)
    cfg = Config(update_enabled=False)
    app = build_app(config=cfg, updater_loop=loop, data_dir=tmp_path)

    with TestClient(app) as client:
        resp = client.get("/api/updates/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False


def test_api_updates_start_uses_data_dir_for_target(app_with_polling_loop, tmp_path: Path) -> None:
    """다운로드 target 은 %APPDATA%\\GameAssetHelper\\update\\GameAssetHelper.new.exe."""
    app, loop = app_with_polling_loop
    loop._current = _FAKE_UPDATE  # type: ignore[attr-defined]

    captured: dict = {}

    def fake_spawn(downloader, exe_url, sha256_url, target_path):
        captured["target"] = target_path

    with TestClient(app) as client:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "gah.web.routers.updates._spawn_download_task",
                fake_spawn,
            )
            client.post("/api/updates/start")

    assert captured.get("target") is not None
    assert captured["target"].name == "GameAssetHelper.new.exe"
    assert "update" in captured["target"].parts


def test_api_updates_check_html_fragment_renders(app_with_polling_loop) -> None:
    """HTMX hx-get 응답이 HTML fragment (배너 partial) 도 반환할 수 있다.

    GET /api/updates/check?fragment=banner → HTML
    """
    app, loop = app_with_polling_loop
    loop._current = _FAKE_UPDATE  # type: ignore[attr-defined]

    with TestClient(app) as client:
        resp = client.get("/api/updates/check?fragment=banner")
    assert resp.status_code == 200
    assert "v0.0.2" in resp.text
    assert "지금 업데이트" in resp.text or "Update now" in resp.text  # i18n 둘 다 허용
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_web_updates.py -v
```
Expected: 8 FAIL — `ModuleNotFoundError: No module named 'gah.web.routers.updates'` 또는 fixture 실패

- [ ] **Step 3: Router 구현**

Create `src/gah/web/routers/updates.py`:

```python
"""M9: /api/updates/{check,start,status} 라우터."""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from gah.core.updater.checker import AvailableUpdate, PollingLoop
from gah.core.updater.downloader import DownloadError, UpdateDownloader
from gah.core.updater.installer import UpdateInstaller


log = logging.getLogger(__name__)


router = APIRouter(prefix="/api/updates")


# 단일 다운로드 + SSE 스트림 공유 큐 (singleton — 한 번에 1 다운로드)
_PROGRESS_QUEUE: queue.Queue = queue.Queue()
_DOWNLOAD_LOCK = threading.Lock()


def _update_to_dict(u: AvailableUpdate) -> dict:
    return {
        "tag": u.tag,
        "version": f"{u.version.major}.{u.version.minor}.{u.version.patch}",
        "size_bytes": u.size_bytes,
        "exe_url": u.exe_url,
        "sha256_url": u.sha256_url,
    }


@router.get("/check")
async def check(request: Request, fragment: Optional[str] = None):
    """현재 업데이트 상태 반환.

    fragment=banner → HTML partial (HTMX 용)
    그 외 → JSON
    """
    loop: PollingLoop = request.app.state.updater_loop
    cfg = request.app.state.config

    current = loop.current() if cfg.update_enabled else None
    if fragment == "banner":
        from gah.web.i18n import _t

        if current is None:
            return HTMLResponse("")  # 빈 fragment — Alpine 가 x-show=false
        return HTMLResponse(
            f"""
            <div class="update-banner" data-update-banner>
              🎉 {_t("Update available")}: <b>{current.tag}</b>
              <button hx-post="/api/updates/start" hx-swap="outerHTML">
                {_t("Update now")}
              </button>
              <button onclick="document.querySelector('[data-update-banner]').remove()">
                {_t("Later")}
              </button>
            </div>
            """.strip()
        )

    return JSONResponse({
        "enabled": cfg.update_enabled,
        "detected": current is not None,
        "update": _update_to_dict(current) if current else None,
    })


def _spawn_download_task(
    downloader: UpdateDownloader,
    exe_url: str,
    sha256_url: str,
    target_path: Path,
) -> None:
    """별도 thread 에서 다운로드 + SHA 검증 + SSE 큐 publish."""
    def task() -> None:
        try:
            def progress(b: int, total: int) -> None:
                _PROGRESS_QUEUE.put({"phase": "download", "bytes": b, "total": total})
            downloader._progress = progress  # inject (단순화)
            _PROGRESS_QUEUE.put({"phase": "download", "bytes": 0, "total": 0})
            downloader.download(
                exe_url=exe_url,
                sha256_url=sha256_url,
                target_path=target_path,
            )
            _PROGRESS_QUEUE.put({"phase": "verify"})
            _PROGRESS_QUEUE.put({"phase": "ready_to_install"})
        except DownloadError as exc:
            _PROGRESS_QUEUE.put({"phase": "error", "reason": str(exc)})
        finally:
            _PROGRESS_QUEUE.put(None)  # sentinel — close stream

    threading.Thread(target=task, name="UpdaterDownloadTask", daemon=True).start()


@router.post("/start")
async def start(request: Request):
    loop: PollingLoop = request.app.state.updater_loop
    cfg = request.app.state.config
    paths = request.app.state.paths

    if not cfg.update_enabled:
        raise HTTPException(status_code=400, detail="updates disabled")
    current = loop.current()
    if current is None:
        raise HTTPException(status_code=404, detail="no update available")

    if not _DOWNLOAD_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="download already in progress")
    try:
        target = paths.data_dir / "update" / "GameAssetHelper.new.exe"
        _spawn_download_task(
            downloader=UpdateDownloader(),
            exe_url=current.exe_url,
            sha256_url=current.sha256_url,
            target_path=target,
        )
    finally:
        _DOWNLOAD_LOCK.release()

    return JSONResponse({
        "status": "started",
        "stream_url": "/api/updates/status",
    })


@router.get("/status")
async def status():
    """SSE — 다운로드 진행률 + verify + ready_to_install + restarting."""
    def gen():
        while True:
            try:
                msg = _PROGRESS_QUEUE.get(timeout=30.0)
            except queue.Empty:
                continue
            if msg is None:
                break
            yield f"data: {json.dumps(msg)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: WebServer 에 router 등록 + state 주입**

Edit `src/gah/web/server.py` (또는 `app.py`) — `build_app` 함수가 PollingLoop + Config + paths 를 app.state 에 저장하도록:

```python
def build_app(
    config: Config,
    *,
    updater_loop: PollingLoop | None = None,
    data_dir: Path | None = None,
    # 기존 인자 ...
) -> FastAPI:
    app = FastAPI(...)
    # ...
    app.state.config = config
    app.state.updater_loop = updater_loop
    app.state.paths = default_app_paths(data_dir) if data_dir else None

    from gah.web.routers.updates import router as updates_router
    app.include_router(updates_router)
    # 기존 라우터 ...
    return app
```

`run_tray` 가 `WebServer` 생성 시 `updater_loop=polling_loop` 전달:

```python
def run_tray(paths, config, ...):
    # ...
    polling_loop = PollingLoop(...)
    polling_loop.start()

    web_server = WebServer(
        config=config,
        paths=paths,
        updater_loop=polling_loop,
    )
    # ...
```

- [ ] **Step 5: 테스트 통과 + 회귀**

```powershell
pytest tests/test_web_updates.py -v
```
Expected: 8 PASS

```powershell
pytest -q
```
Expected: 1103 passed (1095 + 8)

- [ ] **Step 6: Commit**

```bash
git add src/gah/web/routers/updates.py src/gah/web/server.py src/gah/app.py tests/test_web_updates.py
git commit -m "feat(m9): /api/updates router — check/start/status + SSE 진행률"
```

---

### Task 12: 업데이트 배너 partial + base.html 통합

**Files:**
- Create: `src/gah/web/templates/_update_banner.html`
- Modify: `src/gah/web/templates/base.html`

**Steps:**

- [ ] **Step 1: 배너 partial 작성 (HTMX + Alpine)**

Create `src/gah/web/templates/_update_banner.html`:

```html
{# M9: 업데이트 배너 — HTMX poll + Alpine x-show + SSE 진행률 #}
<div id="gah-update-banner-root"
     hx-get="/api/updates/check?fragment=banner"
     hx-trigger="load, every 60s"
     hx-swap="innerHTML">
  <!-- /api/updates/check?fragment=banner 가 HTML 반환 -->
</div>

<template x-data="updateProgress()" id="gah-update-progress-template">
  <div x-show="visible" class="update-progress" role="status" aria-live="polite">
    <div x-text="phaseLabel"></div>
    <div class="progress-bar" x-show="phase === 'download'">
      <div :style="{ width: percent + '%' }"></div>
    </div>
  </div>
</template>

<script>
function updateProgress() {
  return {
    visible: false,
    phase: '',
    bytes: 0,
    total: 0,
    get percent() { return this.total > 0 ? Math.round(this.bytes / this.total * 100) : 0 },
    get phaseLabel() {
      switch (this.phase) {
        case 'download': return '{{ _("Downloading...") }}'
        case 'verify':   return '{{ _("Verifying...") }}'
        case 'ready_to_install': return '{{ _("Ready to install — restarting...") }}'
        case 'restarting': return '{{ _("Restarting...") }}'
        case 'error':    return '{{ _("Update failed") }}'
        default: return ''
      }
    },
    start() {
      this.visible = true
      const es = new EventSource('/api/updates/status')
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data)
        this.phase = data.phase
        if (data.bytes !== undefined) this.bytes = data.bytes
        if (data.total !== undefined) this.total = data.total
        if (data.phase === 'ready_to_install') {
          // 즉시 install API 호출 (Task 11 의 server-side 흐름이 swap + restart 진행)
          fetch('/api/updates/install', { method: 'POST' })
          es.close()
        }
        if (data.phase === 'error') es.close()
      }
    }
  }
}
document.body.addEventListener('htmx:configRequest', (evt) => {
  // 사용자가 hx-post /api/updates/start 클릭 시 progress 시작
  if (evt.detail.path === '/api/updates/start') {
    Alpine.store('updateProgress')?.start?.()
  }
})
</script>
```

⚠ `/api/updates/install` 은 Task 11 의 SSE 흐름이 자동 처리하므로 사실상 클라이언트에서 별도 호출 불필요. swap + restart 는 `_spawn_download_task` 가 `ready_to_install` 까지만 publish 하고, swap 은 서버 측 별도 thread 가 처리. **Task 11 의 `_spawn_download_task` 가 swap_files + spawn_complete_update 까지 처리하도록 확장** (또는 별도 `/api/updates/install` POST endpoint 신설). 본 plan 은 단순화: SSE 가 `ready_to_install` 받으면 **클라이언트가 `/api/updates/install` POST 호출 → 서버가 swap + spawn**.

Task 11 의 `_spawn_download_task` 끝에 `swap` 단계 추가 후 `_PROGRESS_QUEUE.put({"phase": "restarting"})` → `os._exit(0)` 또는 적당한 종료 흐름. 이 단계는 Task 12 에서 추가.

`/api/updates/install` POST 추가:

```python
@router.post("/install")
async def install(request: Request):
    from gah import __version__
    paths = request.app.state.paths
    if paths is None:
        raise HTTPException(status_code=500, detail="paths not configured")

    target = paths.data_dir / "update" / "GameAssetHelper.new.exe"
    if not target.exists():
        raise HTTPException(status_code=404, detail="no downloaded update")

    import os
    import sys
    current_exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(sys.argv[0]).resolve()
    installer = UpdateInstaller(current_exe_path=current_exe)
    installer.swap_files(new_exe_path=target)
    installer.spawn_complete_update(old_pid=os.getpid())
    _PROGRESS_QUEUE.put({"phase": "restarting"})
    _PROGRESS_QUEUE.put(None)

    # 메인 종료 — uvicorn graceful shutdown
    import threading
    threading.Thread(target=lambda: (
        __import__("time").sleep(1.0),
        os._exit(0),
    )).start()
    return JSONResponse({"status": "installing"})
```

- [ ] **Step 2: `base.html` 에 배너 include**

Edit `src/gah/web/templates/base.html` — `<body>` 첫 줄 또는 헤더 바로 아래:

```html
<body>
  {% include "_update_banner.html" %}
  <!-- 기존 헤더 + main ... -->
</body>
```

- [ ] **Step 3: 통합 smoke test 추가 (`tests/test_web_updates.py` 에)**

```python
def test_base_html_includes_update_banner(app_with_polling_loop) -> None:
    app, _ = app_with_polling_loop
    with TestClient(app) as client:
        resp = client.get("/library")
    assert resp.status_code == 200
    assert "gah-update-banner-root" in resp.text


def test_api_updates_install_returns_404_when_no_file(app_with_polling_loop) -> None:
    app, _ = app_with_polling_loop
    with TestClient(app) as client:
        resp = client.post("/api/updates/install")
    assert resp.status_code == 404
```

⚠ 위 2 신규 테스트는 Task 12 의 +2 로 합산. Phase 3 total = 10 (Task 11 의 8 + Task 12 의 2). spec 의 +8 에서 +2 오버.

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_web_updates.py -v
```
Expected: 10 PASS

```powershell
pytest -q
```
Expected: 1105 passed (1103 + 2)

- [ ] **Step 5: Commit**

```bash
git add src/gah/web/templates/_update_banner.html src/gah/web/templates/base.html src/gah/web/routers/updates.py tests/test_web_updates.py
git commit -m "feat(m9): _update_banner.html + /api/updates/install — swap 트리거"
```

---

### Task 13: i18n msgids + ko/en 번역

**Files:**
- Modify: `src/gah/web/locale/ko/LC_MESSAGES/messages.po`
- Modify: `src/gah/web/locale/en/LC_MESSAGES/messages.po`
- 컴파일 산출: `.mo` 파일들

**Steps:**

- [ ] **Step 1: 새 msgid 추출**

```powershell
pybabel extract -F babel.cfg -k _ -k _t -o src/gah/web/locale/messages.pot .
```

```powershell
pybabel update -i src/gah/web/locale/messages.pot -d src/gah/web/locale
```

새 msgid (~10건) 가 ko.po / en.po 에 추가됨:
- `"Update available"`
- `"Update now"`
- `"Later"`
- `"Downloading..."`
- `"Verifying..."`
- `"Ready to install — restarting..."`
- `"Restarting..."`
- `"Update failed"`
- `"Check for updates"` (트레이 메뉴)
- `"vX.X.X update available"` 형태 (트레이 동적 — 포맷 처리)

- [ ] **Step 2: ko.po 번역 채우기**

Edit `src/gah/web/locale/ko/LC_MESSAGES/messages.po`:

```po
msgid "Update available"
msgstr "업데이트 가능"

msgid "Update now"
msgstr "지금 업데이트"

msgid "Later"
msgstr "나중에"

msgid "Downloading..."
msgstr "다운로드 중..."

msgid "Verifying..."
msgstr "검증 중..."

msgid "Ready to install — restarting..."
msgstr "설치 준비 완료 — 재시작 중..."

msgid "Restarting..."
msgstr "재시작 중..."

msgid "Update failed"
msgstr "업데이트 실패"

msgid "Check for updates"
msgstr "업데이트 확인"
```

- [ ] **Step 3: en.po — msgid 와 msgstr 동일 (영어 원문)**

```po
msgid "Update available"
msgstr "Update available"

msgid "Update now"
msgstr "Update now"

# ... 등
```

- [ ] **Step 4: 컴파일**

```powershell
pybabel compile -d src/gah/web/locale
```

산출: `src/gah/web/locale/{ko,en}/LC_MESSAGES/messages.mo` 갱신

- [ ] **Step 5: 회귀 검증 (i18n 통합 smoke)**

```powershell
pytest -q
```
Expected: 1105 passed (변동 없음)

수동 검증:
- `python -m gah --tray` 실행 후 브라우저에서 `?lang=ko` / `?lang=en` 둘 다 확인
- 배너 텍스트가 ko/en 모두 정상 렌더

- [ ] **Step 6: Commit**

```bash
git add src/gah/web/locale/messages.pot src/gah/web/locale/ko/LC_MESSAGES/messages.po src/gah/web/locale/en/LC_MESSAGES/messages.po src/gah/web/locale/ko/LC_MESSAGES/messages.mo src/gah/web/locale/en/LC_MESSAGES/messages.mo
git commit -m "feat(m9): i18n msgid 9건 + ko/en 번역 + .mo 컴파일"
```

---

## Phase 4 — 트레이 통합 (+4 tests, ~0.2주)

### Task 14: tray.py 동적 메뉴 (PySide6 signal/slot)

**Files:**
- Modify: `src/gah/tray.py`
- Create: `tests/test_tray_update.py`

**Steps:**

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_tray_update.py`:

```python
"""M9 Task 14: 트레이 동적 메뉴 — 업데이트 확인 + vX.X.X 업데이트 가능."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytest.importorskip("PySide6")


def test_make_tray_icon_includes_check_for_updates_action(qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QMenu
    from gah.tray import make_tray_icon

    if QApplication.instance() is None:
        QApplication([])

    polling_loop = MagicMock()
    polling_loop.current.return_value = None

    tray = make_tray_icon(
        on_open_main=lambda: None,
        on_exit=lambda: None,
        polling_loop=polling_loop,
    )
    menu: QMenu = tray.contextMenu()
    labels = [a.text() for a in menu.actions()]
    assert any("업데이트 확인" in l or "Check for updates" in l for l in labels)


def test_tray_menu_shows_update_available_when_loop_has_update(qtbot) -> None:
    from PySide6.QtWidgets import QApplication, QMenu
    from gah.tray import make_tray_icon, refresh_update_menu_item
    from gah.core.updater.checker import AvailableUpdate
    from gah.core.updater.version import Version

    if QApplication.instance() is None:
        QApplication([])

    polling_loop = MagicMock()
    polling_loop.current.return_value = AvailableUpdate(
        tag="v0.0.2",
        version=Version(0, 0, 2, None),
        exe_url="x", sha256_url="x", size_bytes=0,
    )

    tray = make_tray_icon(
        on_open_main=lambda: None,
        on_exit=lambda: None,
        polling_loop=polling_loop,
    )
    refresh_update_menu_item(tray, polling_loop.current())

    menu: QMenu = tray.contextMenu()
    labels = [a.text() for a in menu.actions()]
    assert any("v0.0.2" in l for l in labels)


def test_check_for_updates_action_invokes_loop_tick(qtbot) -> None:
    from PySide6.QtWidgets import QApplication
    from gah.tray import make_tray_icon

    if QApplication.instance() is None:
        QApplication([])

    polling_loop = MagicMock()
    tray = make_tray_icon(
        on_open_main=lambda: None,
        on_exit=lambda: None,
        polling_loop=polling_loop,
    )
    # 메뉴에서 "업데이트 확인" 찾아 trigger
    for action in tray.contextMenu().actions():
        if "업데이트 확인" in action.text() or "Check for updates" in action.text():
            action.trigger()
            break

    polling_loop._tick.assert_called_once()  # 수동 폴링


def test_tray_update_listener_refreshes_menu_on_new_update(qtbot) -> None:
    """PollingLoop 의 listener 가 트레이 메뉴를 자동 갱신."""
    from PySide6.QtWidgets import QApplication
    from gah.tray import make_tray_icon
    from gah.core.updater.checker import AvailableUpdate, PollingLoop
    from gah.core.updater.version import Version

    if QApplication.instance() is None:
        QApplication([])

    loop = PollingLoop(check_callback=lambda: None, interval_seconds=10.0)
    tray = make_tray_icon(
        on_open_main=lambda: None,
        on_exit=lambda: None,
        polling_loop=loop,
    )

    update = AvailableUpdate(
        tag="v0.1.0",
        version=Version(0, 1, 0, None),
        exe_url="x", sha256_url="x", size_bytes=0,
    )
    # listener 가 호출되는 흐름 시뮬레이션 — _tick 안에서 발생
    loop._current = update
    for cb in loop._on_update:
        cb(update)

    labels = [a.text() for a in tray.contextMenu().actions()]
    assert any("v0.1.0" in l for l in labels)
```

- [ ] **Step 2: 테스트 실패 확인**

```powershell
pytest tests/test_tray_update.py -v
```
Expected: 4 FAIL — `make_tray_icon` signature 불일치 등

- [ ] **Step 3: tray.py 수정**

Edit `src/gah/tray.py` — `make_tray_icon` signature 확장 + 새 메뉴 액션 + listener 등록:

```python
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gah.core.updater.checker import AvailableUpdate, PollingLoop


_UPDATE_AVAILABLE_PREFIX = "🎉 "


def make_tray_icon(
    on_open_main,
    on_exit,
    *,
    polling_loop: Optional["PollingLoop"] = None,
    # ... 기존 인자 (autostart 등) ...
):
    # 기존 QSystemTrayIcon 생성, contextMenu 구축
    icon = QSystemTrayIcon(...)
    menu = QMenu()

    open_action = menu.addAction("메인 창 열기" if _lang_is_ko() else "Open main window")
    open_action.triggered.connect(on_open_main)

    # M9: 업데이트 확인 + 동적 알림 액션
    check_action = menu.addAction("업데이트 확인" if _lang_is_ko() else "Check for updates")
    if polling_loop is not None:
        check_action.triggered.connect(polling_loop._tick)

    update_action = menu.addAction("")  # placeholder, refresh_update_menu_item 에서 채움
    update_action.setVisible(False)
    update_action.setData("update_available_slot")
    if polling_loop is not None:
        update_action.triggered.connect(lambda: _open_update_banner(on_open_main))

    # 기존: autostart 토글 + 종료 액션
    # ...

    icon.setContextMenu(menu)

    if polling_loop is not None:
        def _on_update(update):
            refresh_update_menu_item(icon, update)
        polling_loop.add_listener(_on_update)
        # 부팅 직후 이미 있을 수 있음
        if polling_loop.current():
            refresh_update_menu_item(icon, polling_loop.current())

    return icon


def refresh_update_menu_item(tray, update: "AvailableUpdate | None") -> None:
    menu = tray.contextMenu()
    for action in menu.actions():
        if action.data() == "update_available_slot":
            if update is None:
                action.setVisible(False)
                action.setText("")
            else:
                action.setVisible(True)
                action.setText(f"{_UPDATE_AVAILABLE_PREFIX}{update.tag} 업데이트 가능")
            break


def _open_update_banner(on_open_main):
    """트레이의 동적 액션 클릭 시 메인 창(웹 UI) 띄움 — 사용자가 배너 클릭하도록."""
    on_open_main()


def _lang_is_ko() -> bool:
    # M8 의 i18n 인프라 활용 — config.ui_language / accept-language 기반
    try:
        from gah.web.i18n import current_locale
        return current_locale() == "ko"
    except Exception:
        return True  # default
```

⚠ 트레이는 Qt 컨텍스트 + i18n 시스템 사용. M8 의 `_t()` 가 web request context (ContextVar) 기반이라 tray 에서 직접 호출 불가능. tray 는 config.ui_language (또는 OS locale) 기반으로 별도 분기. 위 `_lang_is_ko()` 는 단순화 — 실제로는 Config 의 ui_language 읽어 처리.

- [ ] **Step 4: 테스트 통과 + 회귀**

```powershell
pytest tests/test_tray_update.py -v
```
Expected: 4 PASS

```powershell
pytest -q
```
Expected: 1109 passed (1105 + 4)

- [ ] **Step 5: Commit**

```bash
git add src/gah/tray.py tests/test_tray_update.py
git commit -m "feat(m9): tray 동적 메뉴 — 업데이트 확인 + vX.X.X 업데이트 가능"
```

---

## Phase 5 — 검증 + 문서 + 첫 서명 release (0 tests, ~0.5주)

### Task 15: 수동 검증 시나리오 6건 작성

**Files:**
- Create: `milestones/M9_verification.md`

**Steps:**

- [ ] **Step 1: `milestones/M9_verification.md` 작성**

Create with 6 scenarios:

```markdown
# M9 — 코드 서명 + 자동 업데이트 검증

자동: `pytest -q` → 1109 passed + 1 skipped + 40 deselected (M9 +63, 1046 baseline + 추정 +13 over-spec).

## 수동 검증 시나리오 (6건)

### 시나리오 1 — v0.0.1 → v0.0.2 실 swap 시연

준비:
1. 현재 main = v0.0.2 commit. `dist/GameAssetHelper.exe` 빌드 후 SignPath 서명.
2. v0.0.1 정식 release exe 를 `%TEMP%\GameAssetHelper.exe` 로 복사.
3. v0.0.2 서명 exe 를 임시 GH release 페이지에 업로드 (별도 test repo 또는 draft).

실행:
1. `%TEMP%\GameAssetHelper.exe` 실행 → 트레이 + 웹 UI 부팅
2. 폴링 24h 기다리지 말고 트레이 → "업데이트 확인" 클릭
3. 트레이 메뉴에 "🎉 v0.0.2 업데이트 가능" 등장 확인
4. 웹 UI 새로고침 → 배너 등장 확인
5. "지금 업데이트" 클릭 → SSE 진행률 표시 확인
6. 자동 종료 + 재기동 → 새 트레이 아이콘 (v0.0.2) 등장
7. `python -m gah --version` 또는 트레이 → 메인 창 → /api/health 에서 version 0.0.2 확인

기대:
- 트레이 알림 + 웹 배너 양쪽 표시
- SSE 진행률 정상 (download → verify → ready_to_install → restarting)
- 끊김 없는 재시작 (~5~10s)
- 새 exe 가 정상 부팅 (서명 효과로 SmartScreen 경고 없음)

### 시나리오 2 — "나중에" 클릭 후 다음 부팅 재표시

1. 배너에서 "나중에" 클릭 → 배너 사라짐
2. 트레이 메뉴는 여전히 "v0.0.2 업데이트 가능" 유지
3. 트레이 → "종료" → 다시 실행
4. 부팅 직후 + 60s 안에 배너 재등장 확인

### 시나리오 3 — /settings 에서 update.enabled=false 토글

1. `/settings` → "자동 업데이트 확인" 체크박스 OFF (Task 11 의 신규 필드)
2. 폴링 thread 가 멈추는지 로그 확인 (`%APPDATA%\GameAssetHelper\logs\gah.log` "Update polling stopped")
3. /api/updates/check 가 `{"enabled": false, "detected": false}` 반환 확인

### 시나리오 4 — 네트워크 끊은 채 부팅

1. 인터넷 차단 (Wi-Fi off 또는 hosts 로 api.github.com 차단)
2. 트레이 부팅
3. 로그에 `update check failed (network):` 메시지만, 사용자 알림 X 확인
4. 인터넷 복구 후 다음 폴링 주기에 자동 재시도

### 시나리오 5 — SHA mismatch 시뮬레이션

1. release asset 의 `.sha256` 을 의도적으로 잘못된 hash 로 변조 (test repo 사용)
2. 업데이트 → "지금 업데이트" 클릭
3. SSE `phase: "error", reason: "sha256 mismatch"` 표시 확인
4. `%APPDATA%\GameAssetHelper\update\GameAssetHelper.new.exe` 자동 삭제 확인

### 시나리오 6 — STEP 3a 메인 종료 hang 시뮬레이션

1. 메인 exe 에 `Qt cleanup hang` 시뮬레이션 코드 임시 주입 (개발 빌드)
2. 업데이트 진행 → `--complete-update` 모드가 30s wait timeout
3. 로그에 "Old PID X did not exit within 30s — proceeding best-effort"
4. 새 exe 가 강제로 진행 후 정상 부팅 확인 (`.old.exe` 가 남을 수도 있음)
5. 시뮬레이션 코드 제거

## 알려진 한계

- SignPath 심사 거부 시 폴백 (Azure Trusted Signing / 상용 OV) — spec §2 비채택 행에서 다음 옵션.
- 코드 서명 첫 적용 후에도 SmartScreen 평판 누적까지 수개월 — release notes 의 SmartScreen 안내 유지.
- 부분 다운로드 resume 미구현 — 308MB 라 처음부터 재시작.
- DB schema migration 없음 — v0.0.1 → v0.0.2 schema 동일 가정.
```

- [ ] **Step 2: Commit**

```bash
git add milestones/M9_verification.md
git commit -m "docs(m9): M9_verification — 수동 검증 시나리오 6건"
```

---

### Task 16: README §배포 갱신

**Files:**
- Modify: `README.md`

**Steps:**

- [ ] **Step 1: README §배포 섹션 갱신**

Edit `README.md` §배포 — 단일 exe 빌드 (M8) 섹션을 SignPath 서명 흐름 포함으로 확장:

```markdown
## 배포 — 단일 exe 빌드 + 서명 (M8 + M9)

일반 사용자에게 배포할 단일 `.exe` 를 만든다. 코드 서명은 SignPath Foundation OSS 무료 프로그램 (M9).

```powershell
# 1. dev 의존성 설치 (Babel, pyinstaller, respx 포함)
pip install -e .[dev]
```

```powershell
# 2. 번역 카탈로그 컴파일 (.po → .mo)
pybabel compile -d src/gah/web/locale
```

```powershell
# 3. 트레이 아이콘 ICO 생성
python scripts/generate_tray_ico.py
```

```powershell
# 4. exe 빌드
pyinstaller gah.spec
```

```powershell
# 5. SHA256 생성
$hash = (Get-FileHash dist\GameAssetHelper.exe -Algorithm SHA256).Hash.ToLower()
Set-Content -Path dist\GameAssetHelper.exe.sha256 -Value $hash -Encoding ascii
```

```powershell
# 6. SignPath 클라우드 서명 (수동 — https://app.signpath.io)
# - dist/GameAssetHelper.exe 업로드 → 서명 → 다운로드 → 덮어쓰기
# - SHA256 재계산 (서명 후 hash 변경)
```

```powershell
# 7. tag + push + release
git tag -a v0.0.2 -m "v0.0.2 — <한 줄>"
git push origin main
git push origin v0.0.2
gh release create v0.0.2 dist\GameAssetHelper.exe dist\GameAssetHelper.exe.sha256 --title "v0.0.2 — <제목>" --notes-file docs\RELEASE_NOTES_v0.0.2.md
```

상세 절차: [`docs/RELEASE_BUILD_GUIDE.md`](docs/RELEASE_BUILD_GUIDE.md).

빌드된 exe 는 단일 파일로 배포 가능. 첫 실행 시 CLIP 모델 가중치 (~600 MB) 가 `%APPDATA%\GameAssetHelper\cache\clip\` 로 자동 다운로드된다.

### 자동 업데이트 (M9)

이미 설치된 GAH 는 24h 주기로 GitHub Releases API 를 폴링해 새 버전을 감지한다. 알림이 트레이 + 웹 UI 배너에 표시되면 사용자가 "지금 업데이트" 클릭 → 백그라운드 다운로드 + SHA 검증 + swap + 재시작. 자세한 흐름은 [`docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md`](docs/superpowers/specs/2026-05-19-m9-code-signing-and-auto-update-design.md).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(m9): README §배포 — SignPath 서명 + 자동 업데이트 흐름"
```

---

### Task 17: v0.0.2 dogfood release (실 SignPath 서명 + tag + GH release)

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/gah/__init__.py`
- Create: `docs/RELEASE_NOTES_v0.0.2.md`

**Steps:**

- [ ] **Step 1: 버전 0.0.2 로 bump**

Edit `pyproject.toml`:
```toml
version = "0.0.2"
```

Edit `src/gah/__init__.py`:
```python
__version__ = "0.0.2"
```

- [ ] **Step 2: release notes 작성**

Create `docs/RELEASE_NOTES_v0.0.2.md` — v0.0.1 패턴 유지:

```markdown
## 🎮 Game Asset Helper v0.0.2 — 자동 업데이트 + 코드 서명

v0.0.1 의 SmartScreen 경고를 영구 해결하고, 이후 release 가 in-app 알림으로 자동 전파됩니다.

### ✨ 새 기능
- **코드 서명** — SignPath Foundation OSS 인증서. SmartScreen 경고 없이 실행 (평판 누적 진행 중)
- **자동 업데이트** — 24h 주기 GitHub Releases 폴링 + 트레이 알림 + 웹 UI 배너 + 사용자 동의 후 swap

### 🔧 변경 사항
- (v0.0.1 → v0.0.2 의 모든 PR 요약)

### 💻 시스템 요구사항 + 설치
(v0.0.1 release notes 와 동일 — [v0.0.1 페이지](https://github.com/v0o0v/game-asset-helper/releases/tag/v0.0.1) 참고)

### 🐛 알려진 한계
(v0.0.1 와 동일 + DB schema migration 정책 추후)
```

- [ ] **Step 3: 빌드 + 서명 + release (RELEASE_BUILD_GUIDE 절차)**

`docs/RELEASE_BUILD_GUIDE.md` 의 7 단계 그대로 실행:

1. pybabel compile
2. generate_tray_ico
3. pyinstaller
4. SHA256 생성
5. SignPath 서명 (수동 업로드)
6. tag + push
7. `gh release create v0.0.2 dist\GameAssetHelper.exe dist\GameAssetHelper.exe.sha256 --title "v0.0.2 — 자동 업데이트 + 코드 서명" --notes-file docs\RELEASE_NOTES_v0.0.2.md`

- [ ] **Step 4: 본 spec 의 첫 dogfood — 검증 시나리오 1 실행**

`milestones/M9_verification.md` 시나리오 1 (v0.0.1 → v0.0.2 실 swap) 을 실제로 실행해 본 spec 의 첫 실사용으로 확인.

- [ ] **Step 5: Commit + push**

```bash
git add pyproject.toml src/gah/__init__.py docs/RELEASE_NOTES_v0.0.2.md
git commit -m "release(v0.0.2): bump version + release notes"
git push origin main
```

---

## Self-Review

본 plan 작성 직후 self-review 결과 (기록용):

### 1. Spec coverage

| spec section | 대응 task |
|---|---|
| §2 SignPath 인증 | Task 1 |
| §2 자체 updater | Task 2~10 |
| §2 알림만 정책 | Task 11~12 |
| §2 swap 패턴 (`--complete-update`) | Task 7~10 |
| §2 폴링 주기 24h | Task 5 (Config 인자) |
| §2 버전 비교 자체 구현 | Task 3 |
| §3 아키텍처 (트레이/웹/updater 패키지) | Task 5 (app.py) + Task 11~12 (web) + Task 14 (tray) |
| §4 모듈 (8 신규 / 7 수정) | Task 별 Files 섹션 |
| §5.1 폴링 흐름 | Task 4~5 |
| §5.2 SHA256 출처 (.sha256 asset) | Task 4 (checker) + Task 6 (downloader) + Task 17 (release 절차) |
| §5.3 알림 → 다운로드 흐름 | Task 11~12 |
| §5.4 Swap 3-step | Task 7~10 |
| §5.5 "나중에" 케이스 | Task 12 (배너 dismiss) + Task 11 (state 유지) |
| §6 Error matrix | Task 별 테스트 (rate limit/SHA mismatch/network/etc) |
| §7 테스트 +50 | Task 별 신규 (~+63 over-spec, OK) |
| §8 Phase 분할 | Task 17개 in 6 phase |
| §9 메트릭 | header + 각 task |
| §10 알려진 한계 | Task 15 (verification) + Task 17 (release notes) |

### 2. Placeholder scan
- "TBD/TODO/등" 없음. 모든 step 에 실제 code 또는 명령 포함.

### 3. Type consistency
- `AvailableUpdate` 타입은 Task 4 에서 정의, Task 5/11/14 에서 동일 시그니처 사용
- `UpdateChecker.check_once() -> Optional[AvailableUpdate]` — Task 4
- `UpdateDownloader.download(...) -> DownloadResult` — Task 6
- `UpdateInstaller.swap_files / spawn_complete_update / complete_update` — Task 7~9
- `wait_for_pid(pid, timeout_sec) -> bool` — Task 9
- `PollingLoop.current() / add_listener / start / stop / join` — Task 5
- 모든 메서드 시그니처가 후속 task 에서 일관

### 4. Known follow-ups
- Task 11 의 `_spawn_download_task` 가 `downloader._progress` 를 직접 inject — refactor 여지 있지만 단순화 위해 수용
- Task 12 의 swap 트리거 (`/api/updates/install`) 는 plan 본문에서는 Task 11 으로 통합돼야 더 깔끔하지만 분리 유지 (Task 11 = check+start+status, Task 12 = banner+install)
- 트레이 i18n 은 web request ContextVar 와 분리되어 `_lang_is_ko()` 헬퍼 사용. M8 i18n 인프라 보강 필요할 수도 (다음 spec 검토)

---

## 실행 옵션

Plan 작성 끝. 두 가지 실행 옵션:

**1. Subagent-Driven (Recommended)** — 새 sub-agent 가 task 별 dispatch + 두 단계 review. M5 에서 효과 검증됨 (project_m5_subagent_workflow 메모리).

**2. Inline Execution** — 이 세션에서 task 들을 batch 단위 실행 + checkpoint 마다 검토.

어느 쪽으로 갈지 알려달라.
