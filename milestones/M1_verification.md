# M1 검증 보고서

## 1. 자동 검증 결과: ✅ 63/63 통과

사용자 PC(Windows 10, python.org Python 3.12.10, `%USERPROFILE%\.venvs\gah`)에서 `pytest -v` 전체 실행 결과 — M0의 18개를 포함해 63개 모두 통과.

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
configfile: pyproject.toml
testpaths: tests
plugins: mock-3.15.1
collected 63 items

tests/test_asset_kind.py ........................................[  6%]   4 passed
tests/test_config.py    ........................................[ 15%]   6 passed (M0 회귀)
tests/test_entrypoint.py .......................................[ 20%]   3 passed (M0 회귀)
tests/test_imports.py  .........................................[ 22%]   1 passed (M0 회귀, 모듈 목록은 M1 신규 포함)
tests/test_logging.py  .........................................[ 28%]   4 passed (M0 회귀)
tests/test_manifest.py .........................................[ 41%]   8 passed
tests/test_pack_manager.py .....................................[ 53%]   8 passed
tests/test_scanner.py  .........................................[ 61%]   5 passed
tests/test_single_instance.py ..................................[ 68%]   4 passed (M0 회귀)
tests/test_store.py    .........................................[ 87%]  12 passed
tests/test_ui_smoke.py .........................................[ 92%]   3 passed
tests/test_watcher.py  .........................................[100%]   5 passed

============================= 63 passed in 1.14s ==============================
```

분해:

| 묶음 | 신규/회귀 | 케이스 수 |
|---|---|---|
| `test_asset_kind` | 신규 | 4 |
| `test_manifest` | 신규 | 8 |
| `test_store` | 신규 | 12 |
| `test_pack_manager` | 신규 | 8 |
| `test_scanner` | 신규 | 5 |
| `test_watcher` | 신규 | 5 (디바운서 단위) |
| `test_ui_smoke` | 신규 | 3 |
| `test_config` | M0 회귀 | 6 |
| `test_logging` | M0 회귀 | 4 |
| `test_single_instance` | M0 회귀 | 4 |
| `test_entrypoint` | M0 회귀 | 3 |
| `test_imports` | M0 회귀 (M1 모듈 추가) | 1 |
| **합계** | | **63** |

## 2. 검증 환경의 한계

자동 테스트가 다루지 **못한** 항목 — 모두 사용자 PC에서 수동으로 본다.

- **watchdog Observer 실제 동작** — `LibraryWatcher`는 단위 테스트 없이 `PackDebouncer`만 검증했다. `Observer.schedule(handler, ..., recursive=True)`이 Windows에서 라이브러리 트리의 새 디렉터리·파일을 정상 이벤트로 전달하는지는 OS 의존이라 수동 확인이 필요하다.
- **Qt 트레이 메뉴 + 메인 윈도우 표시** — UI 위젯 생성은 `offscreen` Qt 플랫폼으로 스모크 검증했지만, 실제 트레이 아이콘 → "메인 창 열기" 클릭으로 윈도우가 뜨는지는 수동.
- **2초 디바운스로 합쳐진 인테이크 → GUI 갱신 라운드트립** — 워처 스레드에서 `MainWindow.packChanged.emit()` 이 GUI 스레드 슬롯으로 큐드 연결되어 정확히 한 번 인테이크하고 화면이 갱신되는 흐름은, 실제 ReadDirectoryChangesW 이벤트와 Qt 이벤트 루프가 협력해야 확인 가능.

## 3. 사용자 측 수동 검증 항목

PowerShell에서 다음 시나리오를 차례로 실행. 한 줄씩 분리.

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `63 passed` 가 보여야 한다.

### 3.1 회귀 확인 (M0 시나리오가 그대로 동작하는가)

```powershell
python -m gah --version
```

→ 종료 코드 0, `game-asset-helper 0.0.1`.

```powershell
python -m gah --mcp
```

→ 종료 코드 2, "MCP mode is not implemented yet (planned for M3)."

### 3.2 트레이 + 메인 윈도우

```powershell
python -m gah --tray
```

확인 항목:
- 시스템 트레이에 아이콘이 나타난다.
- 아이콘 우클릭 → 메뉴에 "메인 창 열기"와 "종료"가 보인다.
- "메인 창 열기" 클릭 → 빈 팩/라이브러리 탭이 있는 윈도우가 뜬다.
- 로그(`%APPDATA%\GameAssetHelper\logs\gah.log`)에 `library reconciled: +0 / -0 / =0` 라인이 있다 (첫 부팅이면 라이브러리가 비어 있으므로).

### 3.3 워처 → 인테이크 → GUI 갱신

다른 PowerShell 창에서:

```powershell
mkdir $env:APPDATA\GameAssetHelper\library\kenney_test
```

```powershell
Copy-Item -Path "C:\Windows\Web\Screen\img100.jpg" -Destination "$env:APPDATA\GameAssetHelper\library\kenney_test\hello.jpg"
```

(JPG가 없으면 임의의 PNG/WAV 파일을 라이브러리에 떨어뜨려도 된다.)

대기 ≈ 2~3초 후 GUI 메인 윈도우에서:
- "팩" 탭: 1행, 이름 `kenney_test`, 벤더 `kenney` (휴리스틱), 에셋 수 1
- "라이브러리" 탭: 1행, 경로 `kenney_test/hello.jpg`, 종류 `sprite`, 분석 상태 `pending`

### 3.4 삭제 화해

```powershell
Remove-Item -Recurse -Force "$env:APPDATA\GameAssetHelper\library\kenney_test"
```

대기 ≈ 2~3초 후 GUI에서 양쪽 탭의 해당 행이 사라진다. (`MainWindow._on_pack_changed` 가 폴더 부재를 감지해 `reconcile_library`로 폴백.)

### 3.5 부팅 시 풀스캔 diff

GAH 종료 후, GAH 가 꺼진 상태에서 `library/` 에 새 폴더 만들고 GAH를 다시 켠다.

```powershell
mkdir $env:APPDATA\GameAssetHelper\library\my_custom_sfx
```

```powershell
Copy-Item C:\Windows\Media\Alarm01.wav $env:APPDATA\GameAssetHelper\library\my_custom_sfx\alarm.wav
```

```powershell
python -m gah --tray
```

→ 로그에 `library reconciled: +1 / -0 / =N` (N은 기존 팩 수). 메인 창 열기 → 새 팩이 보임. 벤더는 비어 있고(폴더 prefix가 알려진 벤더가 아니므로) `analysis_state=pending`.

### 3.6 DB 시각 확인 (선택)

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db ".tables"
```

→ `asset_tags assets packs tags` 가 나와야 한다 (M2+ 테이블은 아직 없음).

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db "SELECT name, vendor, license FROM packs"
```

→ 등록된 팩 목록.

## 4. 알려진 한계 / M2로 미룬 것

- `assets.analysis_state` 는 항상 `pending` 으로만 들어간다. 실제 분석기와 상태 전이(`analyzing` → `ok` / `partial` / `failed`)는 M2.
- `packs.aggregate_meta` 는 항상 NULL. 집계 메타는 분석 결과를 모아야 하므로 M2.
- 시트(`spritesheet`) kind 는 M1에선 분류되지 않는다 — 모든 이미지가 `sprite`. M4에서 격자 자동 분할과 함께 재분류.
- 검색·필터·통일성 가중치는 M3 일이라 GUI 라이브러리 탭은 단순 페이지(상한 1000행) 만 보여준다.
- Unity Asset Store 캐시 임포트는 M5. M1 의 워처는 사용자가 직접 떨어뜨리는 팩 폴더만 본다.
