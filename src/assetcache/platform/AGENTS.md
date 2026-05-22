<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# platform

## Purpose
OS 종속 기능 어댑터. 현재는 Windows 중심 — 단일 인스턴스 락 (cross-platform) + Windows 자동 시작 (`HKCU\...\Run`). 비-Windows 에서는 자동 시작은 no-op, 단일 인스턴스는 POSIX `flock` 으로 동작.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | 패키지 마커 |
| `single_instance.py` | `SingleInstance(lock_path)` context manager — `portalocker` exclusive lock + PID 기록 + `AlreadyRunning` 예외. cross-platform (Windows + POSIX). DESIGN §9 |
| `autostart.py` | M8 — Windows `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AssetCacheMCP` 토글. `is_autostart_enabled()` / `set_autostart(enabled, exe_path)`. 비-Windows no-op |

## For AI Agents

### Working In This Directory
- **트레이 모드만 단일 인스턴스 락** — MCP stdio 는 매번 새 프로세스 spawn 이라 락 안 잡음 (WAL + busy_timeout 으로 충돌 흡수). `app.py.run_tray()` 만 `SingleInstance(paths.lock_path)` 사용.
- **stale lock 자동 복구** — 파일은 PID 만 기록용이고, 진짜 mutual exclusion 은 kernel lock. 크래시한 이전 프로세스의 lock 파일이 남아도 다음 run 이 즉시 락 획득 가능.
- **autostart 권한** — HKCU 는 표준 사용자 권한으로 R/W 가능. GPO 차단 시 `OSError` 발생, settings router 가 캐치해 사용자에게 알림.
- **`_VALUE_NAME = "AssetCacheMCP"`** — M10 rename 이후 키 이름. 구버전 `GameAssetHelper` 키 마이그레이션은 별도 안 함 (외부 배포 0).
- **`exe_path`** — `pythonw.exe -m assetcache --tray` 또는 PyInstaller exe 절대 경로. 사용자가 venv 위치 옮기면 키 재등록 필요.

### Testing Requirements
- `tests/test_single_instance.py` — cross-platform lock 동작 + AlreadyRunning + stale recovery.
- autostart 회귀는 별도 없음 — Windows 전용 + 사용자 환경 의존이라 수동 검증.

### Common Patterns
- `with SingleInstance(lock_path) as si: ...` — 컨텍스트 종료 시 자동 unlock.
- 비-Windows 분기: `if sys.platform != "win32": return False` / no-op. 명시적 분기로 import 실패 회피.

## Dependencies

### Internal
- `../config.py` (`AppPaths.lock_path`).

### External
- `portalocker>=2.8` (cross-platform exclusive lock).
- `winreg` (Windows stdlib, autostart 전용).

<!-- MANUAL: 향후 macOS launchd / Linux systemd 자동 시작 추가 시 이 디렉터리에 어댑터 추가. -->
