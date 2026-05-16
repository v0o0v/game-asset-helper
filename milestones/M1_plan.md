# M1 — 워처 + Pack Manager + DB (구현 계획)

## 1. 목표

M0의 뼈대 위에 라이브러리 인덱싱의 기초를 올린다. **분석(이미지/오디오 메타 추출, Gemma 호출, 임베딩)은 전부 M2 이후의 일이고**, M1은 다음만 책임진다.

- `%APPDATA%/GameAssetHelper/library/` 를 재귀로 감시한다.
- top-level 하위 디렉터리 1개 = 1 팩 으로 인식해 팩 단위로 디바운스해 처리한다.
- 각 팩 안에서 지원 확장자(`.png`, `.webp`, `.jpg`, `.jpeg`, `.wav`, `.ogg`, `.mp3`)만 골라 SQLite에 행으로 등록한다 (kind=`sprite|sound`, `analysis_state='pending'`).
- 팩 루트의 `pack.json` 또는 `pack.toml` 매니페스트를 읽어 `name`, `vendor`, `license`, `source_url`, `description`을 채운다. 매니페스트가 없으면 폴더명 패턴으로 벤더를 추정한다.
- 앱 부팅 직후 라이브러리 풀스캔과 DB의 차이(추가/삭제/해시 변경)를 한 번 화해(reconcile)한다.
- GUI에는 **팩 탭**과 **라이브러리 탭**(둘 다 메타 없는 단순 표 리스트)을 추가해 인덱싱 결과를 눈으로 확인할 수 있게 한다.

M1이 끝나면 사용자가 `library/`에 폴더 하나를 통째로 떨어뜨렸을 때, 트레이 앱의 "메인 창 열기" 메뉴에서 그 팩과 안의 에셋 행을 볼 수 있어야 한다. 시트는 모두 `sprite`로 들어가고(시트 자동 분할은 M4), 메타데이터 열은 비어 있다(분석은 M2).

## 2. 산출물

| 파일/디렉터리 | 책임 |
|---|---|
| `pyproject.toml` (수정) | `watchdog>=4` 추가 |
| `src/gah/config.py` (수정) | `Config`에 `watch_debounce_seconds: float`, `library_dir_override: str \| None` 두 필드 추가 |
| `src/gah/core/__init__.py` | core 패키지 마커 |
| `src/gah/core/asset_kind.py` | 확장자 → `kind` 분류. 지원 확장자 상수. |
| `src/gah/core/manifest.py` | `pack.json`/`pack.toml` 파싱 + 벤더 휴리스틱(`PackManifest` 데이터클래스 반환) |
| `src/gah/core/store.py` | SQLite 연결 컨텍스트, M1 스키마 생성(idempotent), packs/assets/tags/asset_tags upsert·삭제·조회 |
| `src/gah/core/pack_manager.py` | 팩 디렉터리 인테이크 — 매니페스트 + 파일 워크 → store에 반영, 사라진 파일은 제거 |
| `src/gah/core/scanner.py` | 부팅 시 라이브러리 풀스캔과 DB의 diff 화해 (`reconcile_library()`) |
| `src/gah/core/watcher.py` | watchdog 래퍼 + 팩 단위 디바운스 + pack_manager 디스패치 |
| `src/gah/ui/__init__.py` | ui 패키지 마커 |
| `src/gah/ui/main_window.py` | `QMainWindow` + `QTabWidget` (탭 2개: 팩, 라이브러리). `refresh()` 메서드. |
| `src/gah/ui/pack_view.py` | `QTableWidget` 기반 팩 리스트 (이름·벤더·라이선스·파일 수·enabled) |
| `src/gah/ui/library_view.py` | `QTableWidget` 기반 에셋 리스트 (팩·경로·kind·파일 크기·analysis_state) |
| `src/gah/app.py` (수정) | 워처 시작/정지, 메인 윈도우 인스턴스 보유 |
| `src/gah/tray.py` (수정) | "메인 창 열기" 액션 추가 |
| `tests/test_asset_kind.py` | 확장자 분류 |
| `tests/test_manifest.py` | `pack.json`/`pack.toml` 파싱, 벤더 휴리스틱 |
| `tests/test_store.py` | 스키마 생성, WAL 모드, packs/assets/tags upsert·삭제·조회 |
| `tests/test_pack_manager.py` | 인테이크: 신규/변경/삭제 시나리오 |
| `tests/test_scanner.py` | 풀스캔 diff (추가/제거/no-op) |
| `tests/test_watcher.py` | 디바운서·핸들러 단위 (watchdog Observer는 미사용) |
| `tests/test_ui_smoke.py` | 메인 윈도우/탭 위젯이 import + construct 가능 (offscreen) |

## 3. 작업 단위와 책임

### 3.1 `core/asset_kind.py`

- `SUPPORTED_IMAGE = {".png", ".webp", ".jpg", ".jpeg"}`, `SUPPORTED_AUDIO = {".wav", ".ogg", ".mp3"}`.
- 함수 `classify(path: Path) -> str | None` — 확장자 소문자 매칭. 이미지 → `"sprite"`, 오디오 → `"sound"`, 그 외 → `None`.
- M1에서는 시트 자동 판별을 하지 않는다. 모든 이미지는 `sprite`. (시트는 M4에서 `sprite` → `spritesheet`로 재분류한다.)

### 3.2 `core/manifest.py`

- `@dataclass(frozen=True) PackManifest` 필드: `display_name: str | None`, `vendor: str | None`, `source_url: str | None`, `license: str | None`, `description: str | None`. (스키마에 들어가지 않는 자유 키는 무시.)
- `load_manifest(pack_dir: Path) -> PackManifest` — 다음 순서로 시도:
  1. `pack.json` 존재하면 `json.loads`. 파싱 실패 시 경고 로그 후 휴리스틱.
  2. `pack.toml` 존재하면 `tomllib.load`. 파싱 실패 시 경고 로그 후 휴리스틱.
  3. 둘 다 없으면 휴리스틱 — 폴더명 패턴으로 `vendor` 추정 (`kenney_*` → `kenney`, `kaykit_*` → `kaykit`, `craftpix_*` → `craftpix`). 추정 못 하면 `vendor=None`.
- `display_name` 기본값: 매니페스트가 주지 않으면 `None`(store가 폴더명을 사용).
- 매니페스트의 `tags`/`style_hint` 같은 추가 필드는 M1에서는 무시(주석으로 미래 마일스톤 표시).

### 3.3 `core/store.py`

- `Store(db_path: Path)` 클래스. 생성 시 `sqlite3.connect(db_path, isolation_level=None)` + `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA foreign_keys=ON`.
- `initialize()` — 다음 테이블을 `IF NOT EXISTS`로 생성: `packs`, `assets`, `tags`, `asset_tags`. 스키마는 DESIGN.md §5.1을 그대로 따른다. M2+ 테이블(`sprite_meta`/`sound_meta`/`assets_fts`/`asset_embeddings`/`projects`/`asset_usage`/`search_queries`/`unity_imports`)은 **생성하지 않는다** — 해당 마일스톤에서 추가.
- 메서드:
  - `upsert_pack(name, manifest, scanned_at) -> int` — `INSERT … ON CONFLICT(name) DO UPDATE`. `added_at`은 INSERT 경로에서만 채운다. `aggregate_meta`는 항상 `NULL` (M1 범위 밖). 반환은 `packs.id`.
  - `delete_pack(pack_id)` — 외래키 CASCADE로 `assets`·`asset_tags`도 함께 제거.
  - `set_pack_enabled(pack_id, enabled: bool)` — 향후 GUI 토글용. M1 자동 변경 경로는 없음.
  - `list_packs(include_disabled=True) -> list[PackRow]` — GUI에서 사용. `enabled=0`은 기본 포함, 검색 필터는 M3 일이라 여기선 단순 SELECT.
  - `get_pack_by_name(name) -> PackRow | None`.
  - `upsert_asset(pack_id, rel_path, kind, file_hash, file_size, added_at) -> int` — `path` 유니크. 기존 행이 있으면 `file_hash`/`file_size`만 갱신하고, `file_hash`가 바뀌면 `analyzed_at=NULL`, `analysis_state='pending'`으로 되돌린다. (M2가 다시 분석하도록.)
  - `delete_asset(asset_id)`.
  - `delete_assets_outside(pack_id, kept_rel_paths: set[str])` — 인테이크 후 사라진 파일 제거.
  - `assets_for_pack(pack_id) -> list[AssetRow]`.
  - `list_assets(limit, offset) -> list[AssetRow]` — GUI 라이브러리 탭.
- `PackRow`, `AssetRow`는 `dataclass(frozen=True)`로 둔다.
- `close()` — 컨텍스트 매니저 `__enter__/__exit__`도 함께 지원.
- 파일 해시: 본문에서 `xxhash`를 쓰지 않고 표준 `hashlib.blake2b(digest_size=16).hexdigest()` 16바이트(32자) 헥스를 사용. DESIGN §5.1이 `xxhash64`를 권장하지만 외부 의존성을 늘리지 않기 위해 표준 라이브러리로 대체한다 — `file_hash`는 컬럼 타입이 `TEXT`라 알고리즘 교체에 안전하다.

### 3.4 `core/pack_manager.py`

- `ingest_pack(store: Store, pack_dir: Path, library_root: Path, *, now: Callable[[], int] = time.time) -> int` —
  1. 매니페스트 로드.
  2. `store.upsert_pack(...)`로 `pack_id` 확보.
  3. 재귀로 `pack_dir`를 워크하면서 지원 확장자만 골라 `(rel_path, kind, file_hash, file_size)` 리스트 만든다. `rel_path`는 `library_root`로부터의 POSIX 상대 경로(`Path.as_posix()`)로 정규화.
  4. 각 항목 `store.upsert_asset(...)`.
  5. 인테이크가 끝난 뒤 `store.delete_assets_outside(pack_id, kept_rel_paths)`로 사라진 파일을 정리.
  6. 마지막으로 `packs.scanned_at`을 `now()`로 업데이트.
- 디렉터리가 0개의 지원 파일만 있어도 팩 행은 만들어 둔다(빈 팩은 GUI에서 가시화 가능).
- 큰 파일에서 hashlib을 64KB 청크로 스트리밍.
- 예외 정책: I/O 에러는 파일 단위로 잡아 로그하고 다음 파일로 진행. 팩 전체는 실패시키지 않는다.

### 3.5 `core/scanner.py`

- `reconcile_library(store: Store, library_root: Path) -> ReconcileReport` —
  1. `library_root` 바로 아래 디렉터리만 나열 → 현재 디스크 팩 집합.
  2. `store.list_packs(include_disabled=True)` → 현재 DB 팩 집합.
  3. 추가된 팩: `pack_manager.ingest_pack(...)` 호출.
  4. 사라진 팩: `store.delete_pack(...)`.
  5. 유지된 팩: `ingest_pack` 동일 호출(재인덱싱 — 해시 동일이면 no-op이라 비용 적음).
- `ReconcileReport(added: list[str], removed: list[str], rescanned: list[str])` 데이터클래스. 로깅·검증·GUI에 사용.
- 라이브러리 루트에 **파일** 만 떨어진 경우는 무시(경고 로그). 팩이 아니라서.

### 3.6 `core/watcher.py`

watchdog 자체는 통합 테스트가 까다로워 다음 두 층으로 분리한다.

- **Pure 디바운서 (`PackDebouncer`)** — 외부 라이브러리 의존 없음.
  - `__init__(window_seconds: float, clock: Callable[[], float] = time.monotonic, on_fire: Callable[[str], None])`.
  - `notify(pack_name: str) -> None` — 호출 시 해당 팩의 다음 발화 시각을 `clock() + window_seconds`로 설정.
  - `tick() -> list[str]` — 현재 시각 기준으로 만료된 팩 이름들을 반환하고 `on_fire`로도 호출. (수동 펌프 가능하게 둬 테스트가 쉽게 시간을 진행할 수 있게 한다.)
- **watchdog 어댑터 (`LibraryWatcher`)** — `watchdog.observers.Observer`와 `FileSystemEventHandler`를 결합.
  - `start(library_root: Path, on_pack_changed: Callable[[str], None])` — 옵저버 시작, 이벤트 경로의 첫 세그먼트로 팩 이름을 뽑아 `PackDebouncer.notify(pack_name)`.
  - `library_root` 바깥 경로나 루트 직속 파일 이벤트는 버린다.
  - 별도 스레드에서 `PackDebouncer.tick`을 주기적으로 펌프(`threading.Timer` 또는 `Observer.event_queue` 후처리). 발화 시 `on_pack_changed(pack_name)`을 메인 스레드 신호로 콜.
  - `stop()` — 옵저버 정지 + 펌프 스레드 정리.
- M1 단위 테스트는 `PackDebouncer`만 검증한다. `LibraryWatcher`의 watchdog 연동은 수동 검증(사용자 PC에서 폴더 드롭 시 GUI 갱신).

### 3.7 `core/__init__.py` 및 통합

- `core/__init__.py`는 패키지 마커만 둔다.
- `app.run_tray(paths, config)` 동작 흐름 보강:
  1. `Store(paths.db_path)` 생성 + `initialize()`.
  2. `library_root = Path(config.library_dir_override) if config.library_dir_override else paths.library_dir`.
  3. `reconcile_library(store, library_root)` 호출 (로그에 결과 카운트).
  4. `MainWindow(store)` 생성 — `refresh()` 호출로 초기 데이터 채우기.
  5. `LibraryWatcher.start(library_root, on_pack_changed=lambda name: _schedule_intake_and_refresh(store, library_root, name, main_window))`.
  6. `qapp.exec()`.
  7. 종료 시 `LibraryWatcher.stop()`, `Store.close()`.
- `tray.make_tray_icon`에 액션 추가: `"메인 창 열기"` → 메인 윈도우 `show()` + `raise_()` + `activateWindow()`. 콜백을 `make_tray_icon(qapp, *, on_open_main: Callable[[], None] | None = None)`로 받는다 (M0 시그니처는 보존하고 키워드 인자 한 개 추가).
- `_schedule_intake_and_refresh`는 워처 스레드에서 호출되므로 `QMetaObject.invokeMethod`로 GUI 스레드에 디스패치한다. 직접 GUI 객체 접근 금지.

### 3.8 `config.py` 변경

- `Config`에 두 필드를 추가:
  ```python
  watch_debounce_seconds: float = 2.0
  library_dir_override: str | None = None
  ```
- 기존 6개 테스트는 그대로 통과해야 한다(추가 필드는 기본값 보유). `from_mapping`이 이미 forward-compat이라 별도 변경 불필요.

## 4. 외부 의존성

| 패키지 | 용도 | 비고 |
|---|---|---|
| `watchdog>=4.0` | 폴더 감시 | Windows ReadDirectoryChangesW 기반. POSIX 폴백도 같은 API. |

새 의존성은 `watchdog` 하나뿐. 해시는 `hashlib` 표준, SQLite는 `sqlite3` 표준, JSON/TOML도 표준. dev 그룹 변경 없음.

## 5. 테스트 전략

### 5.1 단위 테스트 목록

**asset_kind** — `tests/test_asset_kind.py`
- `test_png_jpg_webp_classified_as_sprite`
- `test_wav_ogg_mp3_classified_as_sound`
- `test_unknown_extension_returns_none` — `.txt`, `.meta`, 확장자 없는 파일
- `test_case_insensitive_extension` — `.PNG` 도 `sprite`

**manifest** — `tests/test_manifest.py`
- `test_pack_json_is_parsed_fully` — name/vendor/source_url/license/description 정확히 매핑
- `test_pack_toml_is_parsed_fully` — 동일 필드, TOML
- `test_pack_json_preferred_when_both_present`
- `test_missing_manifest_uses_heuristic_kenney_prefix`
- `test_missing_manifest_uses_heuristic_kaykit_prefix`
- `test_missing_manifest_unknown_prefix_returns_none_vendor`
- `test_malformed_pack_json_falls_back_to_heuristic` — 깨진 JSON이어도 예외 안 던지고 vendor 휴리스틱으로
- `test_unknown_keys_are_ignored` — `pack.json`에 없는 키 있어도 OK

**store** — `tests/test_store.py`
- `test_initialize_creates_required_tables` — `sqlite_master`에서 packs/assets/tags/asset_tags 확인
- `test_pragma_journal_mode_is_wal`
- `test_initialize_is_idempotent`
- `test_upsert_pack_inserts_then_updates` — 같은 name 두 번 → 한 행, `vendor` 갱신됨
- `test_upsert_pack_returns_stable_id`
- `test_delete_pack_cascades_assets` — `assets` 행도 자동 삭제
- `test_upsert_asset_sets_pending_state` — 신규는 `analysis_state='pending'`, `analyzed_at IS NULL`
- `test_upsert_asset_with_same_hash_is_noop` — `analyzed_at`이 이미 채워져 있던 경우 보존
- `test_upsert_asset_with_changed_hash_resets_analysis` — `analyzed_at`을 NULL로, `analysis_state='pending'`로
- `test_delete_assets_outside_removes_missing_only`
- `test_list_packs_returns_dataclasses`
- `test_assets_for_pack_returns_in_path_order`

**pack_manager** — `tests/test_pack_manager.py`
- `test_ingest_creates_pack_and_assets_from_manifest` — pack.json + PNG 2 + WAV 1 → packs 1행, assets 3행
- `test_ingest_without_manifest_uses_folder_heuristic` — kenney_* 폴더 → vendor=kenney
- `test_ingest_skips_unsupported_files` — .txt/.gd 무시
- `test_reingest_is_noop_when_unchanged`
- `test_reingest_updates_hash_when_bytes_change`
- `test_reingest_removes_deleted_files`
- `test_ingest_handles_empty_pack` — 지원 파일 0개여도 packs 행 1개 + assets 0개
- `test_ingest_normalizes_relative_path_to_posix` — Windows 백슬래시여도 DB는 forward slash

**scanner** — `tests/test_scanner.py`
- `test_reconcile_adds_new_packs`
- `test_reconcile_removes_vanished_packs`
- `test_reconcile_no_changes_is_noop_report` — added/removed 모두 비어 있고 rescanned 만 채워짐
- `test_reconcile_ignores_files_at_library_root`
- `test_reconcile_runs_on_empty_library` — 라이브러리 폴더는 있지만 빈 경우 보고서 모두 빈 리스트

**watcher** — `tests/test_watcher.py`
- `test_debouncer_fires_after_window` — `notify` → 시간 진행 → `tick()`이 그 팩 이름 반환
- `test_debouncer_coalesces_within_window` — 동일 팩에 두 번 notify해도 한 번 발화
- `test_debouncer_resets_window_on_new_event` — 윈도우 만료 전 새 notify가 들어오면 다음 발화 시각이 밀린다
- `test_debouncer_handles_multiple_packs_independently`
- `test_debouncer_uses_injected_clock` — 픽스처 시각이 흐르도록 주입

**ui_smoke** — `tests/test_ui_smoke.py`
- `test_main_window_can_be_constructed` — 메모리 DB(`:memory:`)에 빈 store → MainWindow 생성 + show 호출(`offscreen`에선 표시되지 않음) 시 예외 없음
- `test_pack_view_populates_from_store` — store에 팩 1개 넣고 `view.refresh()` 후 `rowCount() == 1`
- `test_library_view_populates_from_store` — 비슷한 방식
- 위 세 테스트 모두 `qt_offscreen` autouse 픽스처가 적용됨

### 5.2 테스트 인프라

- `tests/conftest.py`에 추가 픽스처:
  - `library_root(tmp_appdata) -> Path` — `tmp_appdata / "library"`을 만들어 반환.
  - `make_pack(library_root)` 팩토리 — `(name, files: dict[str, bytes])`를 받아 디렉터리 만들고 파일 작성, 매니페스트도 옵션.
  - `store(tmp_appdata)` — `Store(tmp_appdata / "test.db")` + `initialize()` 호출 후 yield, 종료 시 close.
- watchdog Observer는 단위 테스트에서 띄우지 않는다 — 디바운서만 검증하고 옵저버 연동은 수동 검증 항목.

### 5.3 검증 기준 (Definition of Done)

1. `pytest -q` 전체 통과. M0의 18개 + M1의 신규 테스트 모두 PASS.
2. M0 회귀 없음 (config/logging/single_instance/entrypoint/imports 18개 그대로).
3. PowerShell에서 다음 시나리오가 동작:
   - `python -m gah --tray` 로 트레이가 뜬다.
   - 트레이 메뉴 "메인 창 열기" → 빈 팩/라이브러리 탭이 보이는 메인 윈도우 표시.
   - 다른 셸에서 `%APPDATA%\GameAssetHelper\library\` 아래에 `mkdir kenney_test` + PNG 1~2개 복사.
   - 2초 안에 GUI의 팩 탭에 행 1개, 라이브러리 탭에 행 1~2개가 보임 (`analysis_state` 컬럼은 `pending`).
   - 폴더를 삭제하면 다음 부팅(혹은 즉시) 재화해 후 GUI에서도 사라짐.
4. `metadata.db` 가 생성되고 `sqlite3` CLI로 열어 보면 packs/assets 행이 채워져 있다.

## 6. 위험 요소와 완화

- **watchdog 이벤트 폭주 / 디바운스 정확성** — 압축 해제 시 수백 개의 이벤트가 몰리는데, 디바운서를 팩 단위·monotonic clock 기반으로 만들어 정확한 윈도우를 보장. 단위 테스트가 주입 시계로 시간 진행을 검증한다.
- **윈도우즈 경로 분리자 / 대소문자 / 유니코드** — 모든 DB 경로는 `Path.as_posix()`로 정규화하고 비교도 같은 형식으로. 파일 이름이 한글이면 `tomli`/`json`이 UTF-8을 그대로 다루므로 추가 처리 없음 다만 매니페스트 파일 읽기는 명시적으로 `encoding="utf-8"`을 사용한다.
- **재해시 비용** — 매 부팅마다 전체 라이브러리 재해시는 부담. 1차로는 `(file_size, mtime_ns)` 캐시 비교로 `file_hash` 재계산을 스킵하고, 다른 경우에만 hashlib 스트리밍. 캐시는 `assets` 행 자체(`file_size`)와 디스크 `stat`만 사용 (별도 캐시 테이블 없이도 효과). M1 안에서 구현한다.
- **DB 동시 접근** — 워처 콜백과 GUI 갱신이 같은 store를 만지므로, `sqlite3` 연결은 GUI 스레드 1개만 보유하고 워처 스레드는 `QMetaObject.invokeMethod`로 GUI 스레드에 작업을 넘긴다. WAL 모드라 읽기 잠금 충돌은 적지만 모든 쓰기는 GUI 스레드로 직렬화.
- **GUI 테스트의 플레이키함** — `QT_QPA_PLATFORM=offscreen`(M0 autouse 픽스처)으로 헤드리스 동작 보장. `QTimer.singleShot` 이나 `app.processEvents()`에 의존하지 않는 단순 위젯 단위 검증만 한다.
- **GUI 갱신 빈도** — 한 팩 인테이크가 끝날 때마다 `MainWindow.refresh()`를 전체 호출하면 큰 라이브러리에서 느려질 수 있다. M1 범위에서는 단순 전체 새로고침으로 두고, 부분 갱신은 M6 GUI 마감에서 다룬다.

## 7. M2 인계점

- `assets.analysis_state='pending'` 행이 M2의 분석기 입력 큐가 된다. M2가 추가할 테이블(`sprite_meta`, `sound_meta`, `assets_fts`, `asset_embeddings`)은 `Store.initialize()`가 새 마이그레이션 함수를 호출하도록 구조만 잡아 두자(단, M1에서는 이 함수를 비워둔다 — 호출 자체가 idempotent라 향후 마이그레이션 위치만 확보).
- `Config.watch_debounce_seconds`/`library_dir_override`는 M2 분석 큐 폭주 제어와 비표준 라이브러리 경로 테스트에서 다시 활용된다.
- `core/watcher.LibraryWatcher`의 콜백 시그니처(`on_pack_changed: (pack_name) -> None`)는 M2의 분석 큐 입력으로 자연 연장된다 — M2는 동일 콜백 안에서 `analysis_state='pending'` 행을 큐에 넣으면 된다.
- M3의 검색/통일성은 `packs.aggregate_meta`, `projects`, `asset_usage`, `assets_fts`, `asset_embeddings` 를 새로 만들어야 한다. M1 스키마는 이들을 건드리지 않으므로 충돌 없음.
