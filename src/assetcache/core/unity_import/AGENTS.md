<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# unity_import

## Purpose
M7 — Unity Asset Store `.unitypackage` 임포트 워크플로. 캐시 디렉터리 스캔 → `.unitypackage` 파싱 → 사용자 선택 (`/unity` 페이지) → 추출 + 라이브러리 팩으로 등록. spec: `docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import-design.md` §4.1~§4.17.

## Key Files
| File | Description |
|------|-------------|
| `scanner.py` | `UnityAssetStoreScanner` — 캐시 디렉터리 재스캔. 부팅 직후 자동 실행 (`app._boot_unity_scan`) |
| `cache_paths.py` | `detect_cache_path(config)` — 환경변수 `ASSETSTORE_CACHE_PATH` + Config + Unity 기본 경로 (`%APPDATA%\Unity\Asset Store-5.x`) 휴리스틱 |
| `unitypackage.py` | `.unitypackage` (gzip tar) 파서 — `pathname` 메타 + `asset.meta` + 파일 추출 |
| `importer.py` | 추출 + 라이브러리 팩으로 등록 + 사용자 진행률 콜백 |
| `remote_optin.py` | 비공식 publisher 패널 API 경유 다운로드 (옵트인 실험 기능, §4.9) |
| `types.py` | `UnityPackage` / `UnityImportResult` dataclass |

## For AI Agents

### Working In This Directory
- **부팅 자동 스캔** — `app._boot_unity_scan()` 가 별도 스레드에서 `run_once`. 경로 없거나 임포트 실패 시 조용히 종료. 임포트 자체는 사용자가 웹 UI 에서 트리거.
- **MCP 통합** — `mcp.tools.scan_unity_asset_store_cache` + `list_unity_packages(state)` (state ∈ `discovered` / `imported` / `failed`). 임포트 트리거는 MCP 가 아닌 웹 UI 책임.
- **`asset_usage` 보존** — 팩 삭제 시 `ON DELETE CASCADE` 로 assets / embeddings 제거되지만 `asset_usage` 이력은 보존 (분석용).
- **Remote opt-in** — `remote_optin.py` 는 공식 API 가 없어 비공식 publisher 패널 사용. 기본 OFF, `/settings` 에서 옵트인.

### Testing Requirements
- `tests/test_unity_scanner.py` — 캐시 스캔.
- `tests/test_unity_cache_paths.py` — 경로 탐지.
- `tests/test_unity_unitypackage.py` — 파서.
- `tests/test_unity_importer.py` — 추출 + 등록.
- `tests/test_unity_remote_optin.py` — 옵트인.
- `tests/test_unity_import_types.py` — dataclass.
- `tests/test_store_m7_unity.py` + `test_store_m7_projects.py` + `test_store_m7_config.py` — store 측 통합.
- `tests/test_app_unity_boot_scan.py` — 부팅 자동 스캔.
- fixture: `tests/fixtures/unity/make_unitypackage.py` — 합성 `.unitypackage` 빌더.

### Common Patterns
- `state` 머신: `discovered` (스캔만) → `imported` (추출 완료) → `failed` (오류).
- 활성 프로젝트 컨텍스트 — 임포트 시 현재 활성 `project_id` 를 받아 통일성 가중치에 반영.

## Dependencies

### Internal
- `../store.py` (`unity_imports` / `projects` 테이블).
- `../pack_manager.py` (추출 후 팩 등록).
- `../../web/routers/unity_asset_store.py` (웹 UI 트리거).
- `../../mcp/tools.py` (MCP 도구).

### External
- 표준 라이브러리만 (gzip + tarfile). HTTP 클라이언트는 `httpx` (remote opt-in 만).

<!-- MANUAL: remote_optin 은 비공식 API 의존. 공식 API 가 생기면 마이그레이션. -->
