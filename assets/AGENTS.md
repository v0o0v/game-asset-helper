<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# assets

## Purpose
저장소 루트의 정적 자산. 현재는 트레이 아이콘 한 개만. 패키지에 포함시킬 정적 파일은 `src/assetcache/web/static/` 에 두고, 여기는 빌드 산출물(.ico, 라이선스 이미지 등) 용도.

## Key Files
| File | Description |
|------|-------------|
| `tray.ico` | Windows 트레이 + PyInstaller exe 의 아이콘. `scripts/generate_tray_ico.py` 로 재생성 가능 |

## For AI Agents

### Working In This Directory
- `tray.ico` 는 PyInstaller `.spec` 와 `tray.py` 가 직접 경로로 참조한다. 파일명을 바꾸면 양쪽 모두 갱신.
- 새 아이콘이 필요하면 `scripts/generate_tray_ico.py` 의 PIL 코드를 수정해 재생성.

### Testing Requirements
- 시각 검증 — 트레이에 아이콘이 보이는지 사용자 수동 확인.

### Common Patterns
- 이 디렉터리는 **소스 자산** 보관. 런타임 데이터 (`%APPDATA%\AssetCacheMCP\`) 와 혼동 X.

## Dependencies

### Internal
- `src/assetcache/tray.py` — 아이콘 로드.
- `assetcache.spec` (PyInstaller) — `--icon=assets/tray.ico`.
- `scripts/generate_tray_ico.py` — 아이콘 빌드 스크립트.

### External
- 없음.

<!-- MANUAL: -->
