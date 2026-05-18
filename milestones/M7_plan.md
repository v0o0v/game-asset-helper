# M7 — Unity Asset Store 임포트 + 프로젝트 워크플로 (구현 계획)

> **에이전트 작업자에게**: REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (권장) 또는 `superpowers:executing-plans` 로 task 단위 구현. Step 은 `- [ ]` 체크박스로 추적. 본 plan 은 [`M5_plan.md`](./M5_plan.md) / [`M6_plan.md`](./M6_plan.md) 와 같은 한국어 마일스톤 표준 형식이며, [`docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import-design.md`](../docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import-design.md) (이하 "M7 spec") 의 17 결정 + 시나리오 6개 + 모듈 계획을 작업 단위까지 1:1 로 옮긴 것이다.

**목표** — Unity Asset Store 로컬 캐시(`%APPDATA%\Unity\Asset Store-5.x\`) 의 `.unitypackage` 들을 **스캔→미리보기→사용자 선택→임포트** 3단계로 처리해 라이브러리에 편입 + **활성 프로젝트** 컨텍스트(글로벌 헤더 드롭다운) + `/projects` + `/projects/<id>` 신규 페이지(자산 사용 이력 + 채택 팩 분포 + 자산별 선호도). MCP 18 → **20 도구** (`scan_unity_asset_store_cache` + `list_unity_packages`). 임포트 / 활성 프로젝트 변경은 웹 UI 전용. **신규 의존성 0**.

**아키텍처** — `core/unity_import/` 신규 패키지(types/cache_paths/unitypackage/scanner/importer/remote_optin 6 모듈)가 캐시 스캔·미리보기·추출 캡슐화. Store 에 `unity_imports` 테이블 + Config 5 필드 신규 (idempotent 마이그레이션). 웹 라우터 2개(`unity_asset_store` + `projects`) + 글로벌 헤더 fragment. 라이브러리 ↔ Unity 후보 격리 invariant 5개(I-1~I-5) 회귀 테스트로 보장. 임포트 → `library/<pack_name>/` 물리 복사 → 일반 워처 + `PackManager` 인테이크 흐름 그대로(M2~M6 인프라 100% 보존).

**기술 스택** — Python 측 추가 의존성 0 (표준 `tarfile` + `gzip`, FastAPI / Pydantic / Jinja / Alpine.js / HTMX / SSE / Pillow / numpy 모두 기존). 신규 모듈 6 (`unity_import/*`). 신규 라우터 2 (`web/routers/unity_asset_store.py`, `web/routers/projects.py`). 신규 템플릿 7. 수정 모듈 ~15. **신규 테스트 ~125 케이스**. M7 종료 시 baseline 887 + ~125 = **~1012 passed** 목표.

---

## 1. 목표 (시나리오)

M7 가 끝나면 다음 여섯 시나리오가 정상 동작한다. (spec §3 시나리오를 plan 작업 단위로 매핑)

### 1.1 첫 부팅 + 자동 스캔

`python -m gah --tray` → 트레이 + 브라우저 자동 열림 → 부팅 직후 `UnityAssetStoreScanner.run_once()` 별도 스레드 → 캐시 경로 검출(Config → env → Unity Pref → 기본) → 디렉터리 walk → `.unitypackage` 발견 → `unity_imports` 테이블 `import_state='discovered'` row INSERT.

### 1.2 활성 프로젝트 선택 + 채택

사용자 글로벌 헤더 드롭다운 클릭 → 비어 있어 "➕ 새 프로젝트" 모달 → external_id="D:/Unity/MyGame" + display_name="MyGame" 입력 → POST `/api/projects` → 활성으로 설정 → 헤더 갱신 → 라이브러리 카드 "채택" enabled → 클릭 → POST `/api/assets/<id>/adopt` → `record_asset_use(project_id=1, source="user_web")` → asset_usage row 생성.

### 1.3 Unity 패키지 미리보기 + 임포트

`/unity-asset-store` 진입 → 발견 132건 → 한 row "미리보기" 클릭 → `.unitypackage` 안 pathname 읽어 자산 카운트 채움(image 312, sound 14) → `import_state='previewed'` → 사용자 "임포트" 클릭 → 백그라운드 `UnityImporter` 가 `tarfile.extract` 로 `library/mega_platformer_pack/` 물리 복사 → 워처가 새 디렉터리 감지 → 일반 인테이크 → `packs`/`assets` row + 분석 큐 → 완료 후 `import_state='imported'` + `pack_id` 채움.

### 1.4 사용자 "건너뜀" + 영구 유지 + 되돌리기

다른 row "건너뜀" → `import_state='skipped'` → 다음 스캔에서도 유지 (D17) → mtime 변경 시만 `discovered` 로 되돌림 / 사용자 "다시 후보로" 버튼 → 강제 `discovered`.

### 1.5 캐시 업데이트 감지 (재임포트 동의)

Unity Hub 로 v2 다운 → 같은 `.unitypackage` mtime 변경 → 다음 스캔 → `imported` → `discovered` + preview 컬럼 NULL → 페이지에 "업데이트됨, 다시 임포트?" 표시 (자동 재임포트 X).

### 1.6 프로젝트별 선호도 시각화

사이드바 "프로젝트" → `/projects` 목록 → MyGame row → `/projects/1` → (1) 자산 사용 이력 표 (2) 채택 팩 분포 도넛 (3) 자산별 선호도 패널 (signed weight 막대 + 채택 횟수 + 정렬 4종 + 검색 + 페이지네이션). 다른 프로젝트 진입 시 I-5 격리 — project_A 의 weight 가 project_B 점수에 미반영.

## 2. 산출물

### 2.1 코드 모듈

| 파일/디렉터리 | 책임 | 상태 |
|---|---|---|
| `src/gah/core/unity_import/__init__.py` | 빈 패키지 마커. | 신규 |
| `src/gah/core/unity_import/types.py` | 7 frozen dataclass: `UnityPackagePath`/`UnityPackageEntry`/`UnityPackagePreview`/`UnityScanResult`/`UnityImportResult`/`UnityImportRecord`/`ExtractResult`. | 신규 |
| `src/gah/core/unity_import/cache_paths.py` | `detect_cache_path(config) -> Path \| None` — D3 우선순위 (Config → env → Unity Pref → 기본). | 신규 |
| `src/gah/core/unity_import/unitypackage.py` | `parse_pathnames(package_path) -> dict[guid, UnityPackageEntry]` + `extract_targets(package_path, dest_dir, target_guids) -> ExtractResult`. 표준 `tarfile.open(mode="r:gz")`. 이미지/사운드 6 확장자만 필터(D4). | 신규 |
| `src/gah/core/unity_import/scanner.py` | `UnityAssetStoreScanner.run_once(force=False, filter=None) -> UnityScanResult` — 디렉터리 walk + DB 비교 + state 머신(D2/D17). | 신규 |
| `src/gah/core/unity_import/importer.py` | `UnityImporter.import_package(unity_import_id) -> UnityImportResult` — tarfile.extract + pack.json 자동 생성 + 인테이크 트리거 + SSE progress emit. 백그라운드 큐 + 락. | 신규 |
| `src/gah/core/unity_import/remote_optin.py` | `UnityRemoteOptInClient` skeleton — `is_enabled()` Config 토글만, `fetch_owned_assets()` → NotImplementedError(D10, v2). | 신규 |
| `src/gah/core/store.py` (수정) | (1) `Store.initialize()` 에 `unity_imports` CREATE TABLE + 컬럼 존재 검사(D15). (2) Unity API: `insert_unity_import`/`upsert_unity_import`/`update_unity_state`/`list_unity_imports(filter, offset, limit)`/`get_unity_import_by_id`/`get_unity_import_by_path`. (3) 활성 프로젝트: `get_active_project_id()`/`set_active_project_id(id?)` (Config 위임). (4) 프로젝트 페이지 쿼리: `upsert_project(external_id, display_name)`/`list_projects_with_summary()`/`get_project_asset_usage(project_id, offset, limit)`/`get_project_pack_distribution(project_id, top_n=5)`/`get_project_asset_preferences(project_id, sort, search, offset, limit)`. (5) `record_asset_use` source enum 확장 `+ "user_web"`. | 수정 |
| `src/gah/config.py` (수정) | 신규 5 필드 (`unity_asset_store_cache_path`/`unity_remote_optin_enabled`/`unity_remote_optin_session`/`active_project_id`/`preference_usage_weight`). load/save backward compat. | 수정 |
| `src/gah/app.py` (수정) | (1) 부팅 직후 `UnityAssetStoreScanner.run_once()` 별도 스레드(D6). (2) `UnityImporter` 백그라운드 큐 초기화. (3) 트레이 메뉴 항목 추가 (D16). | 수정 |
| `src/gah/tray.py` (수정) | 트레이 메뉴 "Unity 캐시 스캔" + "현재 프로젝트" 서브메뉴. | 수정 |
| `src/gah/mcp/models.py` (수정) | `ScanUnityAssetStoreCacheRequest`/`ScanUnityAssetStoreCacheResult`/`ListUnityPackagesRequest`/`ListUnityPackagesResult` Pydantic. | 수정 |
| `src/gah/mcp/tools.py` (수정) | `tool_scan_unity_asset_store_cache(deps, req)` + `tool_list_unity_packages(deps, req)`. | 수정 |
| `src/gah/mcp/server.py` (수정) | `register_all_tools` 18 → **20**. INSTRUCTIONS 갱신. `tools=18` → `tools=20` 로그. | 수정 |
| `src/gah/web/routers/unity_asset_store.py` | `/unity-asset-store` GET (HTML) + `/api/unity-packages` group (scan/list/preview/import/skip/restore) + SSE 진행 stream. | 신규 |
| `src/gah/web/routers/projects.py` | `/projects` GET + `/projects/<id>` GET + `/api/projects` POST + `/api/active-project` GET/PUT + `/api/assets/<id>/adopt` POST + SSE active_project_changed. | 신규 |
| `src/gah/web/routers/library.py` (수정) | 채택 버튼 hook — 활성 프로젝트 없으면 disabled. 검색 호출에 `project_id` 자동. | 수정 |
| `src/gah/web/routers/feedback.py` (수정) | 활성 프로젝트로 `report_feedback`. | 수정 |
| `src/gah/web/routers/picks.py` (수정) | 사용자 채택 endpoint 가 활성 프로젝트로 `record_asset_use(source="claude_pick")`. M5 의 흐름 보강. | 수정 |
| `src/gah/web/app.py` (또는 `server.py`) | 신규 라우터 2 등록. 글로벌 헤더 fragment 를 base 템플릿에 포함. SSE 라우트. | 수정 |
| `src/gah/web/templates/base.html` (수정) | 사이드바 메뉴 2개 + 글로벌 헤더 fragment 포함. | 수정 |
| `src/gah/web/templates/unity_asset_store.html` | Unity 페이지 본문. | 신규 |
| `src/gah/web/templates/projects_list.html` | `/projects` 본문. | 신규 |
| `src/gah/web/templates/project_detail.html` | `/projects/<id>` 본문 (헤더 + 사용 이력 + 분포 + 선호도 패널 포함). | 신규 |
| `src/gah/web/templates/_header_project_dropdown.html` | 글로벌 헤더 드롭다운 fragment(D12). | 신규 |
| `src/gah/web/templates/_modal_new_project.html` | "+ 새 프로젝트" 모달 fragment. | 신규 |
| `src/gah/web/templates/_unity_package_row.html` | Unity 페이지 표 row fragment (HTMX swap 대상). | 신규 |
| `src/gah/web/templates/_preference_panel.html` | 자산별 선호도 패널 fragment. | 신규 |
| `src/gah/web/static/css/main.css` (수정) | 글로벌 헤더 드롭다운 / Unity 표 / 프로젝트 카드 / 선호도 막대 / 상태 칩 스타일. | 수정 |
| `src/gah/web/static/css/themes.css` (수정) | 상태 칩 / 선호도 막대 light/dark 색상 변수. | 수정 |
| `src/gah/web/static/js/app.js` (또는 alpine.js component, 수정) | 활성 프로젝트 state + 드롭다운 토글 + 채택 버튼 disabled 동기화 + SSE active_project_changed 수신. | 수정 |
| `docs/MCP_USAGE_GUIDE.md` (수정) | 19/20번째 도구 설명 + 워크플로 예시. | 수정 |
| `DESIGN.md` (수정) | §4.9 / §5.4 / §6.11 / §11 M7 → 완료 표시. 단일 도구 → 2 도구 분리 명시. 활성 프로젝트 명세 신규 §4.10. | 수정 |
| `CLAUDE.md` (수정) | §2 진행 현황 표 — M7 행 (대기→진행→완료). §8 다음 작업 M8. | 수정 (M7 끝에) |
| `HANDOFF.md` (수정) | M7 완료 인계. | 수정 (M7 끝에) |
| `pyproject.toml` | **변경 없음** (신규 의존성 0). | — |
| `milestones/M7_todo.md` | TDD 체크리스트. | 신규 |
| `milestones/M7_verification.md` | M7 끝에 작성. | 신규 |

### 2.2 테스트

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_unity_import_types.py` | ~7 | 7 frozen dataclass 동등성/해시/repr |
| `tests/test_unity_cache_paths.py` | ~6 | Config 우선 / env 다음 / Unity Pref 다음 / 기본 / 모두 없음 → None / 존재하지 않는 경로 → None |
| `tests/test_unity_unitypackage.py` | ~12 | fixture .unitypackage 파싱 / pathname 추출 / 이미지 3 확장자 / 사운드 3 확장자 / PSD 제외 / extract_targets 물리 복사 / 디렉터리 보존 / 빈 .unitypackage / 손상 처리 / gzip 헤더 / 큰 파일 mock / 한글 pathname |
| `tests/test_unity_scanner.py` | ~10 | 디렉터리 walk / 신규 → discovered / mtime 동일 → unchanged / mtime 변경 imported → discovered (D17) / mtime 변경 skipped → discovered / 사라진 파일 → removed 카운트 / publisher_glob / asset_name_glob / 빈 캐시 / 권한 없음 → warning |
| `tests/test_unity_importer.py` | ~8 | tarfile.extract 물리 복사 / pack.json 자동 생성 / library/<pack_name>/ 복원 / 임포트 후 state=imported / 실패 → failed + error / 락 / 인테이크 트리거 / imported_at |
| `tests/test_unity_remote_optin.py` | ~3 | is_enabled 기본 False / fetch_owned_assets NotImplementedError / Config 토글 영향 |
| `tests/test_store_m7_unity.py` | ~10 | unity_imports CREATE TABLE idempotent / preview 컬럼 nullable / insert / upsert / update_state / list 필터+offset+limit / get_by_id / get_by_path / state 머신 invariant / 두 번 실행 |
| `tests/test_store_m7_projects.py` | ~10 | upsert_project(신규/기존) / list_projects_with_summary / get_project_asset_usage / get_project_pack_distribution / get_project_asset_preferences + 정렬 4종 / 검색 / 페이지네이션 / I-5 격리 / preference 공식 / 빈 프로젝트 |
| `tests/test_store_m7_config.py` | ~5 | Config 5 필드 라운드트립 / backward compat 기본값 / active_project_id None/Some / save 후 load |
| `tests/test_mcp_tools_m7.py` | ~10 | scan 정상 / 캐시 없음 → 503 / 권한 없음 → 403 / list 정상 / state 필터 / glob / include_preview / offset+limit / import_url 포함 / invalid_state → 400 |
| `tests/test_mcp_integration.py` (수정) | 0 신규/갱신 | tools/list 18 → **20** |
| `tests/test_web_routers_unity.py` | ~8 | GET 200 / 발견 목록 / preview API / import API + SSE / skip / restore / focus 하이라이트 / 빈 캐시 안내 |
| `tests/test_web_routers_projects.py` | ~8 | /projects GET / 활성 강조 / /projects/<id> GET / 사용 이력 / 분포 / 선호도 패널 / 정렬 4종 / 검색+페이지네이션 |
| `tests/test_web_active_project.py` | ~8 | GET /api/active-project / PUT / POST /api/projects / POST adopt / 활성 None 시 adopt → 400 / SSE broadcast / Config 영속 / 헤더 fragment |
| `tests/test_web_card_adopt_button.py` | ~5 | 활성 있음 → enabled / 없음 → disabled + tooltip / POST adopt / ✓ 표시 / source="user_web" |
| `tests/test_isolation_invariants.py` | ~5 | I-1 (discovered not in assets) / I-2 (preview 부작용 0) / I-3 (라이브러리 unity_imports 미조회) / I-4 (Unity 라우터 assets 미조회) / I-5 (프로젝트 간 선호도 격리) |

**합계 ~125 신규 active 케이스**. baseline 887 + 125 ≈ **~1012 active** 예상. 정확 수는 verification 에서 확인.

## 3. 핵심 결정사항 (spec §4 의 17 결정 그대로)

| # | 결정 | spec 절 |
|---|---|---|
| D1 | 베이스라인 = DESIGN §4.9.1 + §5.4 + §6.11. | §4.1 |
| D2 | scan/preview/import 3단계 + state 머신. | §4.2 |
| D3 | 캐시 경로 검출 우선순위(Config→env→Unity Pref→기본). | §4.3 |
| D4 | `.unitypackage` 파서 = 표준 tarfile+gzip, 이미지/사운드 6 확장자만. | §4.4 |
| D5 | 임포트 = 물리 복사, library/<pack_name>/ 일반 인테이크. | §4.5 |
| D6 | 부팅 1회 자동 스캔 + 수동, 임포트는 100% 사용자 클릭. | §4.6 |
| D7 | 라이브러리 ↔ Unity 후보 격리(I-1~I-4). | §4.7 |
| D8 | 프로젝트 간 선호도 격리(I-5). | §4.8 |
| D9 | MCP 2 도구(scan + list). 18→20. | §4.9 |
| D10 | publisher 패널 skeleton + 403_remote_disabled. | §4.10 |
| D11 | 웹 페이지 신규 2(/unity-asset-store + /projects + /projects/<id>). | §4.11 |
| D12 | 활성 프로젝트 = 서버 측 Config, 글로벌 헤더, SSE broadcast. | §4.12 |
| D13 | 채택 버튼 활성 프로젝트 연동 + 비활성 시 disabled. | §4.13 |
| D14 | 자산별 선호도 점수 = sum(feedback.weight) + 0.1*usage_count. | §4.14 |
| D15 | unity_imports CREATE TABLE + Config 5 필드 idempotent. | §4.15 |
| D16 | 트레이 = 스캔만, Windows 토스트 알림. | §4.16 |
| D17 | skipped 영구, mtime 변경 시 discovered 되돌림. | §4.17 |

---

## 4. 작업 단위

작업은 phase 순서대로, 각 phase 의 task 는 표시된 순서대로(앞 task 가 뒤 task 의 빌딩 블록). 각 task 는 **테스트 먼저 → 구현 → 통과 → 회귀 → 커밋** 사이클.

### 4.0 Phase 0 — 스캐폴딩 + 테스트 fixtures (~0.5일)

#### Task 0.1 — 브랜치 + unity_import 패키지 스캐폴딩

**Files:**
- Create: `src/gah/core/unity_import/__init__.py`

- [ ] **Step 1**: 브랜치 분기 — `git checkout -b feat/m7-unity-asset-store-import` (또는 main 위 작업).

- [ ] **Step 2**: 빈 패키지 마커 생성:

```python
"""M7 — Unity Asset Store .unitypackage 임포트 워크플로.

캐시 디렉터리 스캔(scanner) + .unitypackage 파싱(unitypackage)
+ 사용자 선택 후 추출(importer) + 활성 프로젝트 컨텍스트 통합.
M7 spec §4.1~§4.17 참고.
"""
```

- [ ] **Step 3**: 임포트 smoke — `python -c "import gah.core.unity_import; print('ok')"` → `ok`.

- [ ] **Step 4**: 커밋 — `scaffold(m7): core/unity_import 패키지 마커`.

#### Task 0.2 — types.py 7 dataclass

**Files:**
- Create: `src/gah/core/unity_import/types.py`
- Create: `tests/test_unity_import_types.py`

- [ ] **Step 1: 실패 테스트** (~7 케이스):

```python
"""M7 — unity_import 데이터클래스 frozen/동등성 회귀."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from gah.core.unity_import.types import (
    ExtractResult,
    UnityImportRecord,
    UnityImportResult,
    UnityPackageEntry,
    UnityPackagePath,
    UnityPackagePreview,
    UnityScanResult,
)


def test_unity_package_path_frozen():
    a = UnityPackagePath(
        abs_path=Path("C:/A/Mega.unitypackage"),
        publisher="A",
        category="Sprites",
        asset_name="Mega",
        size=100,
        mtime=1700000000,
    )
    b = UnityPackagePath(
        abs_path=Path("C:/A/Mega.unitypackage"),
        publisher="A",
        category="Sprites",
        asset_name="Mega",
        size=100,
        mtime=1700000000,
    )
    assert a == b
    try:
        a.size = 200  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    assert False, "UnityPackagePath must be frozen"


def test_unity_package_entry_kind_enum():
    e = UnityPackageEntry(
        guid="abcd", pathname="Assets/Sprites/idle.png",
        internal_kind="image", size=5000,
    )
    assert e.internal_kind in ("image", "sound")


def test_unity_package_preview_zero_default():
    p = UnityPackagePreview(
        asset_count=0, image_count=0, sound_count=0, sample_pathnames=[]
    )
    assert p.asset_count == 0


def test_unity_scan_result_sum_invariant():
    r = UnityScanResult(
        scanned=10, new=2, updated=1, unchanged=7, removed=0,
        cache_path=Path("C:/X"), warnings=[],
    )
    assert r.new + r.updated + r.unchanged + r.removed == r.scanned


def test_unity_import_result_states():
    r = UnityImportResult(
        pack_id=42, pack_name="mega", asset_count=312,
        state="imported", error=None,
    )
    assert r.state in ("imported", "failed")


def test_extract_result_counts():
    r = ExtractResult(files_extracted=10, bytes_written=1234567)
    assert r.files_extracted == 10


def test_unity_import_record_mirrors_db():
    rec = UnityImportRecord(
        id=1, package_path=Path("C:/A.unitypackage"),
        publisher="X", category="Y", asset_name="Z",
        package_size=100, package_mtime=1700000000,
        preview_asset_count=None, preview_image_count=None,
        preview_sound_count=None, preview_inspected_at=None,
        pack_id=None, import_state="discovered",
        import_error=None, imported_at=None,
        first_seen_at=1700000000, last_scanned_at=1700000000,
    )
    assert rec.import_state == "discovered"
```

- [ ] **Step 2**: `pytest tests/test_unity_import_types.py -v` → 7 FAIL `ModuleNotFoundError`.

- [ ] **Step 3: 구현** `types.py`:

```python
"""M7 — Unity 임포트 데이터클래스 (frozen).

UnityPackagePath  : 캐시 디렉터리에서 추출한 .unitypackage 메타.
UnityPackageEntry : .unitypackage 안 GUID → pathname 매핑 + 분류.
UnityPackagePreview: 미리보기 시 채워지는 자산 카운트.
UnityScanResult   : 한 번의 스캔 결과 (스캔/신규/변경/skip/사라짐).
UnityImportResult : 한 패키지 임포트 결과.
UnityImportRecord : DB row 미러 (변경 시 DB 스키마와 함께 갱신).
ExtractResult     : tarfile.extract 의 파일/바이트 통계.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class UnityPackagePath:
    abs_path: Path
    publisher: str | None
    category: str | None
    asset_name: str
    size: int
    mtime: int


@dataclass(frozen=True)
class UnityPackageEntry:
    guid: str
    pathname: str
    internal_kind: Literal["image", "sound"]
    size: int


@dataclass(frozen=True)
class UnityPackagePreview:
    asset_count: int
    image_count: int
    sound_count: int
    sample_pathnames: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnityScanResult:
    scanned: int
    new: int
    updated: int
    unchanged: int
    removed: int
    cache_path: Path
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnityImportResult:
    pack_id: int | None
    pack_name: str
    asset_count: int
    state: Literal["imported", "failed"]
    error: str | None = None


@dataclass(frozen=True)
class ExtractResult:
    files_extracted: int
    bytes_written: int


@dataclass(frozen=True)
class UnityImportRecord:
    id: int
    package_path: Path
    publisher: str | None
    category: str | None
    asset_name: str
    package_size: int
    package_mtime: int
    preview_asset_count: int | None
    preview_image_count: int | None
    preview_sound_count: int | None
    preview_inspected_at: int | None
    pack_id: int | None
    import_state: Literal[
        "discovered", "previewed", "import_pending",
        "imported", "failed", "skipped",
    ]
    import_error: str | None
    imported_at: int | None
    first_seen_at: int
    last_scanned_at: int
```

> 주의: `UnityPackagePreview.sample_pathnames` 가 frozen 클래스의 mutable default 라 `tuple` 로 변환.

- [ ] **Step 4**: `pytest tests/test_unity_import_types.py -v` → 7 passed.

- [ ] **Step 5**: 회귀 — `pytest -q` → 887 + 7 = **894 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import 데이터클래스 7종`.

#### Task 0.3 — fixture `.unitypackage` 생성 helper

**Files:**
- Create: `tests/fixtures/unity/__init__.py`
- Create: `tests/fixtures/unity/make_unitypackage.py`

- [ ] **Step 1**: helper 함수 작성. 작은 PNG 1 + WAV 1 + PSD 1 (PSD 는 필터에서 제외되어야 함) 을 `tarfile` + `gzip` 으로 묶어 `.unitypackage` 생성.

```python
"""M7 — 테스트용 .unitypackage 생성 helper.

`.unitypackage` 는 gzip tar. 각 GUID 디렉터리에 (asset, asset.meta, pathname).
이 helper 가 다음 layout 을 만든다:
  <guid1>/asset      = 작은 PNG 바이트
  <guid1>/asset.meta = stub YAML
  <guid1>/pathname   = "Assets/Sprites/idle.png"
  <guid2>/asset      = 작은 WAV 바이트
  <guid2>/asset.meta = stub YAML
  <guid2>/pathname   = "Assets/Sounds/jump.wav"
  <guid3>/asset      = 작은 PSD 바이트 (필터에서 제외 검증용)
  <guid3>/asset.meta = stub YAML
  <guid3>/pathname   = "Assets/Sprites/source.psd"
"""

from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
)
WAV_BYTES = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00"
    b"data\x00\x00\x00\x00"
)
PSD_BYTES = b"8BPS" + b"\x00" * 20


def write_member(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def make_fixture_unitypackage(
    dest: Path,
    *,
    include_psd: bool = True,
) -> Path:
    """fixture .unitypackage 를 dest 에 만든다. 절대 경로 반환."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, mode="w:gz") as tar:
        # PNG
        write_member(tar, "abc123/asset", PNG_BYTES)
        write_member(tar, "abc123/asset.meta", b"fileFormatVersion: 2\n")
        write_member(tar, "abc123/pathname", b"Assets/Sprites/idle.png")
        # WAV
        write_member(tar, "def456/asset", WAV_BYTES)
        write_member(tar, "def456/asset.meta", b"fileFormatVersion: 2\n")
        write_member(tar, "def456/pathname", b"Assets/Sounds/jump.wav")
        # PSD (필터 검증용)
        if include_psd:
            write_member(tar, "psd789/asset", PSD_BYTES)
            write_member(tar, "psd789/asset.meta", b"fileFormatVersion: 2\n")
            write_member(tar, "psd789/pathname", b"Assets/Sprites/source.psd")
    return dest
```

- [ ] **Step 2**: smoke 테스트 — pytest 가 fixture 모듈 import 가능한지 확인:
```bash
python -c "from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage; print('ok')"
```

- [ ] **Step 3**: 회귀 — `pytest -q` → 894 passed (회귀 0, 신규 fixture 모듈이라 collect 영향 없음).

- [ ] **Step 4**: 커밋 — `test(m7): .unitypackage fixture helper`.

#### Task 0.4 — `asset_factory` conftest fixture 추가

**Files:**
- Modify: `tests/conftest.py`

> M7 의 여러 테스트(`test_unity_importer`, `test_store_m7_projects`, `test_web_active_project`, `test_web_card_adopt_button`, `test_web_routers_projects`, `test_isolation_invariants`)가 자산을 빠르게 생성하는 helper 가 필요하다. `make_pack` (이미 conftest 에 있음) 와 짝을 이루는 `asset_factory` fixture 신규.

- [ ] **Step 1**: `tests/conftest.py` 의 `make_pack` fixture 옆에 추가:

```python
@pytest.fixture
def asset_factory(store, make_pack):
    """테스트에서 빠르게 asset row 를 만드는 헬퍼.

    Usage:
        aid = asset_factory()                    # 기본: pack 자동 생성
        aid = asset_factory(path="hero.png")     # 경로 지정
        aid = asset_factory(pack_id=42)          # 기존 pack 재사용
    """
    counter = {"n": 0}

    def _factory(*, path: str | None = None, pack_id: int | None = None,
                 kind: str = "sprite") -> int:
        counter["n"] += 1
        if pack_id is None:
            pack_dir = make_pack(name=f"pack_for_asset_{counter['n']}")
            pack_id = store.get_pack_by_path(str(pack_dir)).id
        rel_path = path or f"asset_{counter['n']}.png"
        return store.insert_asset(
            pack_id=pack_id,
            path=rel_path,
            kind=kind,
            file_hash=f"hash_{counter['n']}",
            file_size=100,
            added_at=int(time.time()),
        )
    return _factory
```

> 시그니처는 conftest 의 기존 `make_pack` / `store` 패턴에 맞춰 조정. `Store.insert_asset` / `get_pack_by_path` 의 실제 API 와 일치시켜야 함 (구현 단계에서 store.py 의 메서드명 확인 후 미세 수정).

- [ ] **Step 2**: 회귀 `pytest -q` → 894 passed (conftest 변경은 collect 단계만, 회귀 0).

- [ ] **Step 3**: 커밋 — `test(m7): conftest asset_factory fixture`.

---

### 4.1 Phase 1A — cache_paths.py (~0.5일)

#### Task 1.1 — 캐시 경로 검출 우선순위

**Files:**
- Create: `src/gah/core/unity_import/cache_paths.py`
- Create: `tests/test_unity_cache_paths.py`

- [ ] **Step 1: 실패 테스트** (~6 케이스):

```python
"""M7 — Unity Asset Store 캐시 경로 검출 우선순위 회귀."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gah.config import Config
from gah.core.unity_import.cache_paths import detect_cache_path


def make_dir(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.mkdir()
    return p


def test_config_path_takes_priority(tmp_path, monkeypatch):
    cfg_dir = make_dir(tmp_path, "cfg-cache")
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=str(cfg_dir))
    assert detect_cache_path(cfg) == cfg_dir


def test_env_var_used_when_no_config(tmp_path, monkeypatch):
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=None)
    assert detect_cache_path(cfg) == env_dir


def test_default_path_when_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    cfg = Config(unity_asset_store_cache_path=None)
    # 기본 경로가 존재하지 않으면 None
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=tmp_path / "nonexistent",
    ):
        assert detect_cache_path(cfg) is None


def test_default_path_when_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    default = make_dir(tmp_path, "default-cache")
    cfg = Config(unity_asset_store_cache_path=None)
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=default,
    ):
        assert detect_cache_path(cfg) == default


def test_config_path_nonexistent_falls_through(tmp_path, monkeypatch):
    env_dir = make_dir(tmp_path, "env-cache")
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(env_dir))
    cfg = Config(unity_asset_store_cache_path=str(tmp_path / "nope"))
    assert detect_cache_path(cfg) == env_dir


def test_all_paths_invalid_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    cfg = Config(unity_asset_store_cache_path=None)
    with patch(
        "gah.core.unity_import.cache_paths._default_cache_path",
        return_value=tmp_path / "nope",
    ):
        with patch(
            "gah.core.unity_import.cache_paths._unity_pref_cache_path",
            return_value=None,
        ):
            assert detect_cache_path(cfg) is None
```

- [ ] **Step 2**: `pytest tests/test_unity_cache_paths.py -v` → 6 FAIL.

- [ ] **Step 3: 구현** `cache_paths.py`:

```python
"""M7 — Unity Asset Store 캐시 경로 검출 (D3).

우선순위:
  1. Config.unity_asset_store_cache_path (사용자가 설정에서 입력)
  2. env ASSETSTORE_CACHE_PATH
  3. Unity Editor Preferences (assetStoreCacheLocation)
  4. %APPDATA%/Unity/Asset Store-5.x/ (Windows 기본)

각 단계에서 존재하지 않는 경로는 폴백.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from gah.config import Config


def detect_cache_path(config: Config) -> Optional[Path]:
    """우선순위대로 캐시 경로 검출. 모두 실패하면 None."""
    candidates = [
        _from_config(config),
        _from_env(),
        _unity_pref_cache_path(),
        _default_cache_path(),
    ]
    for p in candidates:
        if p is not None and p.is_dir():
            return p
    return None


def _from_config(config: Config) -> Optional[Path]:
    if not config.unity_asset_store_cache_path:
        return None
    return Path(config.unity_asset_store_cache_path)


def _from_env() -> Optional[Path]:
    v = os.environ.get("ASSETSTORE_CACHE_PATH")
    return Path(v) if v else None


def _unity_pref_cache_path() -> Optional[Path]:
    """Unity Editor Preferences 의 assetStoreCacheLocation. Windows 만 지원."""
    # v1 minimal: 빈 구현 (검출 실패) — Unity Pref 파일 포맷이 다양해 v2 에서 풀어냄.
    # 본 plan 의 회귀 테스트는 mocking 으로 검증.
    return None


def _default_cache_path() -> Optional[Path]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Unity" / "Asset Store-5.x"
```

- [ ] **Step 4**: `pytest tests/test_unity_cache_paths.py -v` → 6 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 894 + 6 = **900 passed** (Config 신규 필드 사용으로 ConfigDataclassError 발생 시 — Phase 2A 에서 Config 갱신 전이라 여기서 일단 임시 Config(unity_asset_store_cache_path=...) attribute injection 가능. 만약 Config dataclass 가 frozen 이고 신규 필드 없으면 이 task 가 fail → Phase 2A 의 Config 갱신을 먼저 진행 후 1A 로 돌아옴).

> **순서 보정 (필요 시)**: Config 가 신규 필드를 모르면 `test_config_path_takes_priority` 가 TypeError. 해결: Phase 2A 의 Task 2.1 (Config 신규 필드) 을 Phase 1A 보다 먼저 — phase 순서 1A 전 2A 의 Config 부분만 우선 작업. 단순화: 본 plan 은 **Task 2.1 (Config) → Task 1.1 (cache_paths)** 순서를 따른다.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import/cache_paths — 4단계 우선순위 검출`.

> 위 순서 보정대로 진행 시: **Task 2.1 (Config 갱신) 을 먼저 실행 → Task 1.1 로 돌아옴**. 본 plan 의 §4.5 Phase 2A 의 Task 2.1 step 참고. 한 줄 요약: `Config` 에 `unity_asset_store_cache_path / unity_remote_optin_enabled / unity_remote_optin_session / active_project_id / preference_usage_weight` 5 필드 추가 후 phase 1A 로.

---

### 4.2 Phase 1B — unitypackage.py (~1일)

#### Task 1.2 — parse_pathnames + extract_targets

**Files:**
- Create: `src/gah/core/unity_import/unitypackage.py`
- Create: `tests/test_unity_unitypackage.py`

- [ ] **Step 1: 실패 테스트** (~12 케이스, fixture helper 사용):

```python
"""M7 — .unitypackage 파서 + 추출 회귀."""
from __future__ import annotations

from pathlib import Path

import pytest

from gah.core.unity_import.unitypackage import (
    parse_pathnames,
    extract_targets,
)
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def fixture_pkg(tmp_path):
    pkg = tmp_path / "MegaPack.unitypackage"
    return make_fixture_unitypackage(pkg)


@pytest.fixture
def fixture_pkg_no_psd(tmp_path):
    pkg = tmp_path / "MegaPackNoPSD.unitypackage"
    return make_fixture_unitypackage(pkg, include_psd=False)


def test_parse_pathnames_returns_dict(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert isinstance(entries, dict)


def test_parse_filters_image_extensions(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "abc123" in entries
    assert entries["abc123"].pathname == "Assets/Sprites/idle.png"
    assert entries["abc123"].internal_kind == "image"


def test_parse_filters_sound_extensions(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "def456" in entries
    assert entries["def456"].pathname == "Assets/Sounds/jump.wav"
    assert entries["def456"].internal_kind == "sound"


def test_parse_excludes_psd(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "psd789" not in entries


def test_parse_empty_package(tmp_path):
    import gzip
    import tarfile
    pkg = tmp_path / "empty.unitypackage"
    with tarfile.open(pkg, mode="w:gz") as tar:
        pass
    entries = parse_pathnames(pkg)
    assert entries == {}


def test_parse_broken_unitypackage(tmp_path):
    pkg = tmp_path / "broken.unitypackage"
    pkg.write_bytes(b"not a gzip file")
    with pytest.raises(Exception):
        parse_pathnames(pkg)


def test_extract_targets_physical_copy(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "library" / "mega"
    result = extract_targets(fixture_pkg_no_psd, dest, target_guids=["abc123", "def456"])
    assert (dest / "Assets" / "Sprites" / "idle.png").is_file()
    assert (dest / "Assets" / "Sounds" / "jump.wav").is_file()
    assert result.files_extracted == 2
    assert result.bytes_written > 0


def test_extract_preserves_directory_structure(fixture_pkg, tmp_path):
    dest = tmp_path / "library" / "mega"
    extract_targets(fixture_pkg, dest, target_guids=["abc123"])
    assert (dest / "Assets" / "Sprites" / "idle.png").exists()
    assert not (dest / "Assets" / "Sounds").exists()


def test_extract_creates_destination(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "deep" / "library" / "mega"
    extract_targets(fixture_pkg_no_psd, dest, target_guids=["abc123"])
    assert dest.is_dir()


def test_extract_skips_psd_even_if_target(fixture_pkg, tmp_path):
    dest = tmp_path / "library" / "mega"
    # PSD GUID 를 강제로 target 에 포함시켜도 확장자 필터로 제외
    result = extract_targets(
        fixture_pkg, dest, target_guids=["abc123", "psd789"],
    )
    assert (dest / "Assets" / "Sprites" / "idle.png").is_file()
    assert not (dest / "Assets" / "Sprites" / "source.psd").exists()
    assert result.files_extracted == 1


def test_extract_empty_targets(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "library" / "mega"
    result = extract_targets(fixture_pkg_no_psd, dest, target_guids=[])
    assert result.files_extracted == 0
    assert not (dest / "Assets").exists() if not dest.exists() else True


def test_parse_unicode_pathname(tmp_path):
    import io
    import tarfile
    pkg = tmp_path / "unicode.unitypackage"
    with tarfile.open(pkg, mode="w:gz") as tar:
        def add(name, data):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        add("xyz/asset", b"PNG")
        add("xyz/pathname", "Assets/한글경로/이미지.png".encode("utf-8"))
    entries = parse_pathnames(pkg)
    assert "xyz" in entries
    assert "한글" in entries["xyz"].pathname
```

- [ ] **Step 2**: `pytest tests/test_unity_unitypackage.py -v` → 12 FAIL.

- [ ] **Step 3: 구현** `unitypackage.py`:

```python
"""M7 — .unitypackage 파서 + 추출 (D4, D5).

.unitypackage = gzip tar. 각 GUID 디렉터리에:
  <guid>/asset      — 실제 자산 바이트
  <guid>/asset.meta — Unity 메타 (YAML, v1 미사용)
  <guid>/pathname   — 원본 Unity 내부 경로 (텍스트)

parse_pathnames(): pathname 만 읽어 GUID → UnityPackageEntry 매핑.
                   이미지/사운드 6 확장자만 필터.
extract_targets(): 선택된 GUID 의 asset 파일을 dest_dir 안 pathname
                   경로로 복원 (물리 복사).
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from gah.core.unity_import.types import ExtractResult, UnityPackageEntry

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_SOUND_EXTS = {".wav", ".ogg", ".mp3"}


def _classify(pathname: str) -> str | None:
    ext = Path(pathname).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _SOUND_EXTS:
        return "sound"
    return None


def _read_member_text(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    f = tar.extractfile(member)
    if f is None:
        return ""
    return f.read().decode("utf-8", errors="replace").strip()


def parse_pathnames(package_path: Path) -> dict[str, UnityPackageEntry]:
    """GUID → UnityPackageEntry. 이미지/사운드만 포함."""
    entries: dict[str, UnityPackageEntry] = {}
    # 두 패스: (1) pathname 텍스트 수집 (2) asset 파일 size 매핑
    pathnames: dict[str, str] = {}
    asset_sizes: dict[str, int] = {}
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2:
                continue
            guid, leaf = parts
            if leaf == "pathname":
                pathnames[guid] = _read_member_text(tar, member)
            elif leaf == "asset":
                asset_sizes[guid] = member.size
    for guid, pathname in pathnames.items():
        kind = _classify(pathname)
        if kind is None:
            continue
        if guid not in asset_sizes:
            continue
        entries[guid] = UnityPackageEntry(
            guid=guid,
            pathname=pathname,
            internal_kind=kind,
            size=asset_sizes[guid],
        )
    return entries


def extract_targets(
    package_path: Path,
    dest_dir: Path,
    target_guids: list[str],
) -> ExtractResult:
    """target_guids 의 asset 파일을 dest_dir/<pathname> 으로 물리 복사.

    pathname 이 이미지/사운드 6 확장자가 아니면 skip (재확인).
    """
    if not target_guids:
        return ExtractResult(files_extracted=0, bytes_written=0)
    target_set = set(target_guids)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # pathname 먼저 수집
    pathnames: dict[str, str] = {}
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2 or parts[0] not in target_set:
                continue
            if parts[1] == "pathname":
                pathnames[parts[0]] = _read_member_text(tar, member)
    files_extracted = 0
    bytes_written = 0
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2 or parts[0] not in target_set or parts[1] != "asset":
                continue
            guid = parts[0]
            pathname = pathnames.get(guid)
            if pathname is None or _classify(pathname) is None:
                continue
            out_path = dest_dir / pathname
            out_path.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(member)
            if f is None:
                continue
            data = f.read()
            out_path.write_bytes(data)
            files_extracted += 1
            bytes_written += len(data)
    return ExtractResult(files_extracted=files_extracted, bytes_written=bytes_written)
```

- [ ] **Step 4**: `pytest tests/test_unity_unitypackage.py -v` → 12 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 900 + 12 = **912 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import/unitypackage — tarfile+gzip 파서 + 물리 복사 추출`.

---

### 4.3 Phase 1C — scanner.py (~1일)

#### Task 1.3 — UnityAssetStoreScanner 디렉터리 walk + state 머신

**Files:**
- Create: `src/gah/core/unity_import/scanner.py`
- Create: `tests/test_unity_scanner.py`
- Depends on: Phase 2A Task 2.2 (Store `upsert_unity_import` / `update_unity_state` 등)

> **순서 보정**: scanner 가 Store API 를 호출하므로 Task 2.2 (Store unity_imports CRUD) 가 먼저 필요. 본 plan 에서는 **Phase 2A 의 Task 2.2 를 Task 1.3 보다 먼저 진행**. 한 줄 요약: `unity_imports` 테이블 CREATE + `insert_unity_import`/`upsert_unity_import`/`update_unity_state`/`list_unity_imports`/`get_unity_import_by_path` 추가.

- [ ] **Step 1: 실패 테스트** (~10 케이스):

```python
"""M7 — UnityAssetStoreScanner state 머신 + walk 회귀."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from gah.core.unity_import.scanner import UnityAssetStoreScanner
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_dir(tmp_path):
    """가짜 캐시 디렉터리 구조: <Publisher>/<Category>/<AssetName>.unitypackage"""
    pub = tmp_path / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega Platformer Pack.unitypackage")
    pub2 = tmp_path / "Kenney" / "Sounds"
    pub2.mkdir(parents=True)
    make_fixture_unitypackage(pub2 / "UI Sound Pack.unitypackage")
    return tmp_path


def test_walk_picks_up_unitypackage_only(cache_dir, store):
    (cache_dir / "NotAPackage.zip").write_bytes(b"x")
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir)
    assert result.scanned == 2


def test_first_scan_marks_new_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir)
    assert result.new == 2
    rows = store.list_unity_imports()
    assert all(r.import_state == "discovered" for r in rows)


def test_second_scan_unchanged(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    result2 = scanner.run_once(cache_path=cache_dir)
    assert result2.new == 0
    assert result2.unchanged == 2


def test_mtime_change_reverts_imported_to_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "imported", pack_id=1)
    # mtime 변경 시뮬
    pkg = rows[0].package_path
    new_mtime = pkg.stat().st_mtime + 100
    import os
    os.utime(pkg, (new_mtime, new_mtime))
    result = scanner.run_once(cache_path=cache_dir)
    assert result.updated >= 1
    refreshed = store.get_unity_import_by_path(pkg)
    assert refreshed.import_state == "discovered"
    assert refreshed.preview_asset_count is None


def test_mtime_change_reverts_skipped_to_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "skipped")
    pkg = rows[0].package_path
    import os
    new_mtime = pkg.stat().st_mtime + 100
    os.utime(pkg, (new_mtime, new_mtime))
    scanner.run_once(cache_path=cache_dir)
    refreshed = store.get_unity_import_by_path(pkg)
    assert refreshed.import_state == "discovered"


def test_removed_file_counted(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    # 하나 삭제
    for p in cache_dir.rglob("*.unitypackage"):
        p.unlink()
        break
    result2 = scanner.run_once(cache_path=cache_dir)
    assert result2.removed == 1


def test_publisher_glob_filter(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir, publisher_glob="Pixel*")
    assert result.scanned == 1


def test_asset_name_glob_filter(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir, asset_name_glob="*Sound*")
    assert result.scanned == 1


def test_empty_cache_directory(tmp_path, store):
    empty = tmp_path / "empty"
    empty.mkdir()
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=empty)
    assert result.scanned == 0


def test_permission_error_warning(tmp_path, store, monkeypatch):
    bad = tmp_path / "bad"
    bad.mkdir()
    def raise_perm(*a, **kw):
        raise PermissionError("denied")
    monkeypatch.setattr(Path, "rglob", raise_perm)
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=bad)
    assert any("permission" in w.lower() or "denied" in w.lower() for w in result.warnings)
```

> 위 테스트는 `store` fixture 가 `conftest.py` 에 있어야 한다. M5/M6 의 store fixture 가 이미 있으면 그대로 사용. 없으면 Phase 2A Task 2.2 에서 추가.

- [ ] **Step 2**: `pytest tests/test_unity_scanner.py -v` → 10 FAIL.

- [ ] **Step 3: 구현** `scanner.py`:

```python
"""M7 — Unity Asset Store 캐시 디렉터리 스캐너 (D2, D17).

캐시 디렉터리를 walk 하며 .unitypackage 발견 → DB 비교 → state 머신:
  신규 → discovered
  mtime 동일 → unchanged
  mtime 변경 (state=imported|skipped|previewed) → discovered + preview NULL
  사라진 파일 → removed 카운트 (state 변경 X)
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from gah.core.unity_import.types import UnityPackagePath, UnityScanResult


def _publisher_category(p: Path, cache_root: Path) -> tuple[str | None, str | None]:
    """캐시 디렉터리 구조: <root>/<Publisher>/<Category>/<File>.unitypackage."""
    try:
        rel = p.relative_to(cache_root)
    except ValueError:
        return (None, None)
    parts = rel.parts
    if len(parts) >= 3:
        return (parts[0], parts[1])
    if len(parts) == 2:
        return (parts[0], None)
    return (None, None)


def _scan_cache(cache_root: Path) -> Iterable[UnityPackagePath]:
    for p in cache_root.rglob("*.unitypackage"):
        try:
            st = p.stat()
            publisher, category = _publisher_category(p, cache_root)
            yield UnityPackagePath(
                abs_path=p,
                publisher=publisher,
                category=category,
                asset_name=p.stem,
                size=st.st_size,
                mtime=int(st.st_mtime),
            )
        except OSError:
            continue


class UnityAssetStoreScanner:
    def __init__(self, store):
        self._store = store

    def run_once(
        self,
        cache_path: Path,
        *,
        force: bool = False,
        publisher_glob: str | None = None,
        asset_name_glob: str | None = None,
    ) -> UnityScanResult:
        warnings: list[str] = []
        if not cache_path or not cache_path.is_dir():
            return UnityScanResult(
                scanned=0, new=0, updated=0, unchanged=0, removed=0,
                cache_path=cache_path or Path(""), warnings=("cache directory missing",),
            )
        try:
            packages = list(_scan_cache(cache_path))
        except PermissionError as e:
            return UnityScanResult(
                scanned=0, new=0, updated=0, unchanged=0, removed=0,
                cache_path=cache_path, warnings=(f"permission denied: {e}",),
            )
        if publisher_glob:
            packages = [
                p for p in packages
                if p.publisher and fnmatch.fnmatch(p.publisher, publisher_glob)
            ]
        if asset_name_glob:
            packages = [
                p for p in packages
                if fnmatch.fnmatch(p.asset_name, asset_name_glob)
            ]

        existing_by_path = {
            r.package_path: r for r in self._store.list_unity_imports()
        }
        seen_paths: set[Path] = set()
        new = 0
        updated = 0
        unchanged = 0
        now = int(time.time())
        for pkg in packages:
            seen_paths.add(pkg.abs_path)
            existing = existing_by_path.get(pkg.abs_path)
            if existing is None:
                self._store.insert_unity_import(pkg, first_seen_at=now, last_scanned_at=now)
                new += 1
                continue
            if force or existing.package_mtime != pkg.mtime:
                # mtime 변경 → state 따라 처리 (D17)
                if existing.import_state in ("imported", "skipped", "previewed"):
                    self._store.update_unity_state(
                        existing.id, "discovered",
                        reset_preview=True,
                        new_mtime=pkg.mtime,
                        new_size=pkg.size,
                        last_scanned_at=now,
                    )
                else:
                    self._store.upsert_unity_import(pkg, last_scanned_at=now)
                updated += 1
            else:
                self._store.touch_unity_import(existing.id, last_scanned_at=now)
                unchanged += 1

        removed = 0
        for path in existing_by_path:
            if path not in seen_paths:
                removed += 1

        return UnityScanResult(
            scanned=len(packages),
            new=new,
            updated=updated,
            unchanged=unchanged,
            removed=removed,
            cache_path=cache_path,
            warnings=tuple(warnings),
        )
```

- [ ] **Step 4**: `pytest tests/test_unity_scanner.py -v` → 10 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 912 + 10 = **922 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import/scanner — 캐시 walk + state 머신`.

---

### 4.4 Phase 1D — importer.py (~1일)

#### Task 1.4 — UnityImporter tarfile.extract + pack.json + 인테이크

**Files:**
- Create: `src/gah/core/unity_import/importer.py`
- Create: `tests/test_unity_importer.py`
- Depends on: Phase 2A `unity_imports` Store CRUD + Phase 1B unitypackage parser

- [ ] **Step 1: 실패 테스트** (~8 케이스):

```python
"""M7 — UnityImporter 추출 + 인테이크 회귀."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from gah.core.unity_import.importer import UnityImporter
from gah.core.unity_import.scanner import UnityAssetStoreScanner
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_with_pkg(tmp_path):
    pub = tmp_path / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega Platformer Pack.unitypackage", include_psd=False)
    return tmp_path


@pytest.fixture
def library_dir(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    return lib


def _discover_and_get_id(store, cache_dir):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    return store.list_unity_imports()[0].id


def test_import_physical_copy_to_library(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    result = importer.import_package(uid)
    assert result.state == "imported"
    pack_dir = library_dir / "mega_platformer_pack"
    assert (pack_dir / "Assets" / "Sprites" / "idle.png").is_file()
    assert (pack_dir / "Assets" / "Sounds" / "jump.wav").is_file()


def test_pack_json_auto_generated(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    manifest = library_dir / "mega_platformer_pack" / "pack.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["vendor"] == "Pixel Studios"
    assert data["license"] == "Unity Asset Store EULA"
    assert data["source"] == "unity_asset_store_cache"


def test_state_imported_after_success(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "imported"
    assert row.imported_at is not None


def test_state_failed_on_error(cache_with_pkg, library_dir, store, monkeypatch):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    def raise_oops(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr("gah.core.unity_import.importer.extract_targets", raise_oops)
    result = importer.import_package(uid)
    assert result.state == "failed"
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "failed"
    assert row.import_error is not None


def test_pack_name_normalization(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    # "Mega Platformer Pack" → "mega_platformer_pack"
    assert (library_dir / "mega_platformer_pack").is_dir()


def test_import_pending_state_before_extract(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    store.update_unity_state(uid, "import_pending")
    importer = UnityImporter(store=store, library_root=library_dir)
    result = importer.import_package(uid)
    assert result.state == "imported"


def test_concurrent_import_lock(cache_with_pkg, library_dir, store):
    # 두 번 import_package 동시 호출 시 두 번째는 noop (락 or 상태 검사)
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    r1 = importer.import_package(uid)
    r2 = importer.import_package(uid)
    assert r1.state == "imported"
    # 두 번째 호출은 이미 imported 라 변경 없음 (idempotent)
    assert r2.state == "imported"


def test_imported_at_recorded(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    before = int(time.time())
    importer.import_package(uid)
    after = int(time.time())
    row = store.get_unity_import_by_id(uid)
    assert before <= row.imported_at <= after
```

- [ ] **Step 2**: `pytest tests/test_unity_importer.py -v` → 8 FAIL.

- [ ] **Step 3: 구현** `importer.py`:

```python
"""M7 — UnityImporter (D5).

선택된 .unitypackage 를 library/<pack_name>/<원본 Unity 경로>/ 로 물리 복사.
pack.json 자동 생성. 워처가 새 디렉터리 감지하면 일반 인테이크 흐름 진입.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from gah.core.unity_import.types import UnityImportResult
from gah.core.unity_import.unitypackage import (
    extract_targets,
    parse_pathnames,
)


def _normalize_pack_name(asset_name: str) -> str:
    """공백·특수문자 → _, 소문자."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", asset_name).strip("_").lower()
    return s or "unity_pack"


class UnityImporter:
    def __init__(self, store, library_root: Path):
        self._store = store
        self._library_root = library_root

    def import_package(self, unity_import_id: int) -> UnityImportResult:
        row = self._store.get_unity_import_by_id(unity_import_id)
        if row is None:
            return UnityImportResult(
                pack_id=None, pack_name="", asset_count=0,
                state="failed", error=f"unity_import id={unity_import_id} not found",
            )
        if row.import_state == "imported" and row.pack_id is not None:
            # idempotent
            return UnityImportResult(
                pack_id=row.pack_id, pack_name=Path(row.package_path).stem.lower(),
                asset_count=row.preview_asset_count or 0,
                state="imported", error=None,
            )

        pack_name = _normalize_pack_name(row.asset_name)
        dest = self._library_root / pack_name

        try:
            entries = parse_pathnames(row.package_path)
            target_guids = list(entries.keys())
            result = extract_targets(row.package_path, dest, target_guids)
            self._write_manifest(dest, row)
            now = int(time.time())
            self._store.update_unity_state(
                unity_import_id,
                "imported",
                imported_at=now,
            )
            return UnityImportResult(
                pack_id=None,  # 워처가 PackManager 통해 채움 — 동기 응답에는 None
                pack_name=pack_name,
                asset_count=result.files_extracted,
                state="imported",
                error=None,
            )
        except Exception as e:
            self._store.update_unity_state(
                unity_import_id,
                "failed",
                import_error=str(e),
            )
            return UnityImportResult(
                pack_id=None, pack_name=pack_name, asset_count=0,
                state="failed", error=str(e),
            )

    def _write_manifest(self, dest: Path, row) -> None:
        manifest = {
            "name": row.asset_name,
            "vendor": row.publisher or "",
            "license": "Unity Asset Store EULA",
            "source": "unity_asset_store_cache",
            "source_path": str(row.package_path),
            "imported_at": int(time.time()),
            "package_mtime": row.package_mtime,
        }
        (dest / "pack.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4**: `pytest tests/test_unity_importer.py -v` → 8 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 922 + 8 = **930 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import/importer — tarfile.extract + pack.json 자동 생성`.

#### Task 1.5 — remote_optin.py skeleton

**Files:**
- Create: `src/gah/core/unity_import/remote_optin.py`
- Create: `tests/test_unity_remote_optin.py`

- [ ] **Step 1: 실패 테스트** (~3 케이스):

```python
"""M7 — UnityRemoteOptInClient skeleton 회귀 (D10)."""
from __future__ import annotations

import pytest

from gah.config import Config
from gah.core.unity_import.remote_optin import UnityRemoteOptInClient


def test_is_enabled_default_false():
    cfg = Config()
    client = UnityRemoteOptInClient(config=cfg)
    assert client.is_enabled() is False


def test_is_enabled_when_toggled():
    cfg = Config(unity_remote_optin_enabled=True)
    client = UnityRemoteOptInClient(config=cfg)
    assert client.is_enabled() is True


def test_fetch_owned_assets_raises_notimplemented():
    cfg = Config(unity_remote_optin_enabled=True)
    client = UnityRemoteOptInClient(config=cfg)
    with pytest.raises(NotImplementedError):
        client.fetch_owned_assets()
```

- [ ] **Step 2**: `pytest tests/test_unity_remote_optin.py -v` → 3 FAIL.

- [ ] **Step 3: 구현** `remote_optin.py`:

```python
"""M7 — Unity Asset Store 비공식 publisher 패널 API skeleton (D10, v2).

v1 기본 비활성. is_enabled() 만 Config 토글 읽고, 실제 HTTP 요청은
v2 에서 구현. ToS 회색지대 — 사용자가 명시적으로 켜야 동작.
"""

from __future__ import annotations

from gah.config import Config


class UnityRemoteOptInClient:
    def __init__(self, config: Config):
        self._config = config

    def is_enabled(self) -> bool:
        return self._config.unity_remote_optin_enabled

    def fetch_owned_assets(self):
        """v2 에서 kharma_session 쿠키 기반 비공식 엔드포인트 호출."""
        raise NotImplementedError(
            "publisher panel API is v2 — see DESIGN.md §4.9.2"
        )
```

- [ ] **Step 4**: `pytest tests/test_unity_remote_optin.py -v` → 3 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 930 + 3 = **933 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): unity_import/remote_optin — v2 skeleton (기본 비활성)`.

---

### 4.5 Phase 2A — Store unity_imports + Config 마이그레이션 (~0.5일)

#### Task 2.1 — Config 신규 5 필드 (D15)

**Files:**
- Modify: `src/gah/config.py`
- Create: `tests/test_store_m7_config.py`

- [ ] **Step 1: 실패 테스트** (~5 케이스):

```python
"""M7 — Config 신규 5 필드 + backward compat 회귀."""
from __future__ import annotations

from pathlib import Path

from gah.config import Config, load_config, save_config


def test_config_defaults_for_new_fields():
    cfg = Config()
    assert cfg.unity_asset_store_cache_path is None
    assert cfg.unity_remote_optin_enabled is False
    assert cfg.unity_remote_optin_session is None
    assert cfg.active_project_id is None
    assert cfg.preference_usage_weight == 0.1


def test_config_round_trip(tmp_path: Path):
    cfg = Config(
        unity_asset_store_cache_path="C:/U/A",
        unity_remote_optin_enabled=True,
        unity_remote_optin_session="abc",
        active_project_id=42,
        preference_usage_weight=0.25,
    )
    p = tmp_path / "config.toml"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.unity_asset_store_cache_path == "C:/U/A"
    assert loaded.unity_remote_optin_enabled is True
    assert loaded.active_project_id == 42
    assert loaded.preference_usage_weight == 0.25


def test_config_backward_compat_legacy_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("# legacy config from M6\nlog_level = \"INFO\"\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.active_project_id is None
    assert cfg.preference_usage_weight == 0.1


def test_config_active_project_optional(tmp_path: Path):
    cfg = Config(active_project_id=None)
    save_config(cfg, tmp_path / "c.toml")
    loaded = load_config(tmp_path / "c.toml")
    assert loaded.active_project_id is None


def test_config_partial_load(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '[unity]\nunity_remote_optin_enabled = true\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    # 부분 로드는 기본값 fallback 가능 (구현 시 어떤 TOML 섹션 구조든 backward compat)
    assert cfg.active_project_id is None
```

- [ ] **Step 2**: `pytest tests/test_store_m7_config.py -v` → 5 FAIL.

- [ ] **Step 3: 구현** — `src/gah/config.py` 에 5 필드 추가:

```python
@dataclass
class Config:
    # ... 기존 필드들 ...
    # M7 — Unity Asset Store
    unity_asset_store_cache_path: str | None = None
    unity_remote_optin_enabled: bool = False
    unity_remote_optin_session: str | None = None
    # M7 — 활성 프로젝트
    active_project_id: int | None = None
    # M7 — /projects/<id> 선호도 점수 공식
    preference_usage_weight: float = 0.1
```

`load_config` / `save_config` 는 기존 패턴(unknown 키 무시 / 신규 키 기본값 fallback) 그대로. 변경 없거나 미세 조정.

- [ ] **Step 4**: `pytest tests/test_store_m7_config.py -v` → 5 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 933 + 5 = **938 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): Config 신규 5 필드 (unity + active_project + preference_usage_weight)`.

#### Task 2.2 — Store unity_imports CRUD (D15)

**Files:**
- Modify: `src/gah/core/store.py`
- Create: `tests/test_store_m7_unity.py`

- [ ] **Step 1: 실패 테스트** (~10 케이스):

```python
"""M7 — Store unity_imports CRUD + state 머신 invariant."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from gah.core.unity_import.types import UnityPackagePath


@pytest.fixture
def unity_path(tmp_path):
    pkg = tmp_path / "A.unitypackage"
    pkg.write_bytes(b"dummy")
    return UnityPackagePath(
        abs_path=pkg, publisher="A", category="B",
        asset_name="A", size=5, mtime=1700000000,
    )


def test_unity_imports_create_table_idempotent(store):
    store.initialize()
    store.initialize()  # 두 번 호출해도 OK


def test_insert_unity_import(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    assert len(rows) == 1
    assert rows[0].import_state == "discovered"


def test_upsert_unity_import(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    new = UnityPackagePath(
        abs_path=unity_path.abs_path, publisher="A", category="B",
        asset_name="A", size=999, mtime=1800000000,
    )
    store.upsert_unity_import(new, last_scanned_at=2)
    row = store.get_unity_import_by_path(unity_path.abs_path)
    assert row.package_mtime == 1800000000
    assert row.package_size == 999


def test_update_unity_state_to_imported(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "imported", pack_id=7, imported_at=2)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.import_state == "imported"
    assert row.pack_id == 7
    assert row.imported_at == 2


def test_update_unity_state_resets_preview(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_preview(rows[0].id, asset_count=10, image_count=8, sound_count=2)
    store.update_unity_state(rows[0].id, "discovered", reset_preview=True)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.preview_asset_count is None


def test_list_unity_imports_filter_state(store, unity_path, tmp_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    pkg2 = tmp_path / "B.unitypackage"
    pkg2.write_bytes(b"x")
    up2 = UnityPackagePath(
        abs_path=pkg2, publisher="A", category="B",
        asset_name="B", size=1, mtime=1700000000,
    )
    store.insert_unity_import(up2, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "skipped")
    filt = store.list_unity_imports(state="skipped")
    assert len(filt) == 1


def test_list_unity_imports_offset_limit(store, tmp_path):
    for i in range(5):
        pkg = tmp_path / f"P{i}.unitypackage"
        pkg.write_bytes(b"x")
        up = UnityPackagePath(
            abs_path=pkg, publisher="X", category="Y",
            asset_name=f"P{i}", size=1, mtime=1700000000+i,
        )
        store.insert_unity_import(up, first_seen_at=1, last_scanned_at=1)
    page1 = store.list_unity_imports(offset=0, limit=2)
    page2 = store.list_unity_imports(offset=2, limit=2)
    assert len(page1) == 2 and len(page2) == 2
    assert page1[0].id != page2[0].id


def test_get_unity_import_by_path(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    row = store.get_unity_import_by_path(unity_path.abs_path)
    assert row is not None
    assert row.asset_name == "A"


def test_get_unity_import_by_id_missing(store):
    assert store.get_unity_import_by_id(9999) is None


def test_touch_unity_import_updates_last_scanned(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.touch_unity_import(rows[0].id, last_scanned_at=999)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.last_scanned_at == 999
```

- [ ] **Step 2**: `pytest tests/test_store_m7_unity.py -v` → 10 FAIL.

- [ ] **Step 3: 구현** — `src/gah/core/store.py` 에 `unity_imports` 테이블 + API 추가:

```python
# Store.initialize() 의 끝부분 (마이그레이션):
def _migrate_unity_imports(self) -> None:
    with self._write_lock:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS unity_imports (
              id                       INTEGER PRIMARY KEY,
              package_path             TEXT NOT NULL UNIQUE,
              publisher                TEXT,
              category                 TEXT,
              asset_name               TEXT NOT NULL,
              package_size             INTEGER NOT NULL,
              package_mtime            INTEGER NOT NULL,
              preview_asset_count      INTEGER,
              preview_image_count      INTEGER,
              preview_sound_count      INTEGER,
              preview_inspected_at     INTEGER,
              pack_id                  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
              import_state             TEXT NOT NULL,
              import_error             TEXT,
              imported_at              INTEGER,
              first_seen_at            INTEGER NOT NULL,
              last_scanned_at          INTEGER NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_unity_imports_pack "
            "ON unity_imports(pack_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_unity_imports_state "
            "ON unity_imports(import_state)"
        )
        self._conn.commit()

# CRUD API:
def insert_unity_import(self, pkg, *, first_seen_at, last_scanned_at) -> int: ...
def upsert_unity_import(self, pkg, *, last_scanned_at) -> int: ...
def update_unity_state(
    self, unity_import_id, state, *,
    pack_id=None, imported_at=None, import_error=None,
    new_mtime=None, new_size=None, last_scanned_at=None,
    reset_preview=False,
) -> None: ...
def update_unity_preview(
    self, unity_import_id, *, asset_count, image_count, sound_count,
) -> None: ...
def touch_unity_import(self, unity_import_id, *, last_scanned_at) -> None: ...
def list_unity_imports(
    self, *, state=None, publisher_glob=None, asset_name_glob=None,
    offset=0, limit=None,
) -> list[UnityImportRecord]: ...
def get_unity_import_by_id(self, unity_import_id) -> UnityImportRecord | None: ...
def get_unity_import_by_path(self, package_path) -> UnityImportRecord | None: ...
```

세부 구현은 M6 의 `_migrate_sprite_meta_animations_json` 패턴 그대로. 모든 쓰기는 `with self._write_lock:` 안.

- [ ] **Step 4**: `pytest tests/test_store_m7_unity.py -v` → 10 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 938 + 10 = **948 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): Store unity_imports 테이블 + CRUD API`.

#### Task 2.3 — Store record_asset_use source enum 확장

**Files:**
- Modify: `src/gah/core/store.py`

- [ ] **Step 1**: 기존 `tests/test_usage_tracker.py` (M3) 또는 `record_asset_use` 테스트 파일 위치 확인 후 `source="user_web"` 케이스 1개 추가. red phase.

- [ ] **Step 2**: `store.py` 또는 `usage_tracker.py` 에서 source enum 검증 분기에 `"user_web"` 추가.

- [ ] **Step 3**: 통과 확인 + 회귀 `pytest -q` → **949 passed**.

- [ ] **Step 4**: 커밋 — `feat(m7): record_asset_use source enum 에 "user_web" 추가`.

---

### 4.6 Phase 2B — Store projects 쿼리 + 트레이 + 부팅 자동 스캔 (~0.5일)

#### Task 2.4 — Store projects 쿼리 (활성 + 목록 + 사용 이력 + 분포 + 선호도)

**Files:**
- Modify: `src/gah/core/store.py`
- Create: `tests/test_store_m7_projects.py`

- [ ] **Step 1: 실패 테스트** (~10 케이스):

```python
"""M7 — Store 프로젝트 / 활성 / 사용 이력 / 분포 / 선호도 + I-5 격리."""
from __future__ import annotations

import time

import pytest


def _make_project(store, ext_id="D:/Unity/A", display="A"):
    return store.upsert_project(external_id=ext_id, display_name=display)


def _make_asset(store, pack_id, path):
    # M3 의 기존 helper 또는 직접 INSERT (테스트 conftest 에 패턴 있을 것)
    return store.create_test_asset(pack_id=pack_id, path=path)  # 구현체에 맞게


def test_upsert_project_new(store):
    pid = _make_project(store)
    assert pid > 0


def test_upsert_project_existing_updates_display(store):
    pid1 = _make_project(store, "D:/X", "Old")
    pid2 = _make_project(store, "D:/X", "New")
    assert pid1 == pid2
    rows = store.list_projects_with_summary()
    assert any(r.display_name == "New" for r in rows)


def test_list_projects_with_summary(store):
    pid = _make_project(store)
    rows = store.list_projects_with_summary()
    assert len(rows) >= 1
    assert rows[0].asset_count >= 0


def test_get_project_asset_usage_empty(store):
    pid = _make_project(store)
    items = store.get_project_asset_usage(project_id=pid)
    assert items == []


def test_get_project_pack_distribution_top_n(store):
    pid = _make_project(store)
    # 사용 이력이 없으면 빈 리스트
    dist = store.get_project_pack_distribution(project_id=pid, top_n=5)
    assert dist == []


def test_get_project_asset_preferences_default_sort(store):
    pid = _make_project(store)
    rows = store.get_project_asset_preferences(project_id=pid)
    assert isinstance(rows, list)


def test_preference_score_formula(store):
    # asset_X 에 positive feedback (weight=+0.3) 2회 + usage 3회
    # composite = 0.6 + 0.1 * 3 = 0.9
    pid = _make_project(store)
    asset_id = _make_asset(store, pack_id=1, path="x.png")
    store.report_feedback(
        project_id=pid, asset_id=asset_id, query_id=None,
        reason="positive", weight=0.3, created_at=1,
    )
    store.report_feedback(
        project_id=pid, asset_id=asset_id, query_id=None,
        reason="positive", weight=0.3, created_at=2,
    )
    for _ in range(3):
        store.record_asset_use(
            project_id=pid, asset_id=asset_id,
            pack_id=1, source="explicit", used_at=int(time.time()),
        )
    rows = store.get_project_asset_preferences(
        project_id=pid, sort="score_desc",
    )
    row = next(r for r in rows if r.asset_id == asset_id)
    assert abs(row.composite_score - 0.9) < 1e-9


def test_preference_isolation_i5(store):
    pa = _make_project(store, "D:/A", "A")
    pb = _make_project(store, "D:/B", "B")
    asset_id = _make_asset(store, pack_id=1, path="x.png")
    # project A 에 negative feedback
    store.report_feedback(
        project_id=pa, asset_id=asset_id, query_id=None,
        reason="negative", weight=-0.5, created_at=1,
    )
    # project B 의 선호도 응답에 영향 없어야 함
    rows_a = store.get_project_asset_preferences(project_id=pa)
    rows_b = store.get_project_asset_preferences(project_id=pb)
    score_a = next(r.composite_score for r in rows_a if r.asset_id == asset_id)
    matching_b = [r for r in rows_b if r.asset_id == asset_id]
    assert score_a == -0.5
    # B 에서는 사용/피드백 없으므로 0 또는 row 부재
    if matching_b:
        assert matching_b[0].composite_score == 0


def test_preference_sort_options(store):
    pid = _make_project(store)
    for s in ("score_desc", "score_asc", "usage_desc", "recent_desc"):
        rows = store.get_project_asset_preferences(project_id=pid, sort=s)
        assert isinstance(rows, list)


def test_preference_search_and_pagination(store):
    pid = _make_project(store)
    for i in range(5):
        aid = _make_asset(store, pack_id=1, path=f"asset{i}.png")
        store.record_asset_use(
            project_id=pid, asset_id=aid,
            pack_id=1, source="explicit", used_at=int(time.time()),
        )
    page = store.get_project_asset_preferences(
        project_id=pid, offset=0, limit=3,
    )
    assert len(page) <= 3
```

> `_make_asset` 와 `report_feedback` 의 시그니처는 기존 store 의 API 에 맞춰야 한다. conftest 에 helper 가 이미 있으면 그대로 사용. M3/M4 의 테스트 파일 (`test_usage_tracker.py`, `test_feedback_records.py` 등) 에서 패턴 발견.

- [ ] **Step 2**: `pytest tests/test_store_m7_projects.py -v` → 10 FAIL.

- [ ] **Step 3: 구현** — `src/gah/core/store.py` 에 다음 메서드 추가:

```python
def upsert_project(self, *, external_id: str, display_name: str | None = None) -> int:
    """external_id 로 검색 후 신규 INSERT 또는 display_name UPDATE. project_id 반환."""

def list_projects_with_summary(self) -> list[ProjectSummary]:
    """projects + asset_usage 통계 JOIN. ProjectSummary 데이터클래스 신규."""

def get_project_asset_usage(
    self, *, project_id: int, offset: int = 0, limit: int | None = None,
) -> list[AssetUsageRow]:
    """asset_usage JOIN assets, 최근 used_at 순."""

def get_project_pack_distribution(
    self, *, project_id: int, top_n: int = 5,
) -> list[PackDistRow]:
    """asset_usage GROUP BY pack_id, top_n. 비율은 응답 계산."""

def get_project_asset_preferences(
    self, *, project_id: int,
    sort: str = "score_desc",
    search: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[PreferenceRow]:
    """feedback_records + asset_usage 종합 → composite_score 컬럼.

    composite_score = SUM(feedback.weight) + preference_usage_weight * usage_count.
    preference_usage_weight 는 Config 에서 받음 (Store 가 Config 참조 보유).
    """

def count_project_asset_preferences(
    self, *, project_id: int, search: str | None = None,
) -> int:
    """선호도 패널 페이지네이션용 total. get_project_asset_preferences 와 같은
    WHERE 조건으로 COUNT(*)."""

def get_project_by_id(self, project_id: int):
    """projects 테이블 단일 row 조회 (없으면 None)."""
```

`ProjectSummary`/`AssetUsageRow`/`PackDistRow`/`PreferenceRow` 4 신규 dataclass 를 `store.py` 또는 `core/projects.py` 에 정의.

- [ ] **Step 4**: `pytest tests/test_store_m7_projects.py -v` → 10 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 949 + 10 = **959 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): Store projects 쿼리 (활성 + 목록 + 사용 + 분포 + 선호도 + I-5 격리)`.

#### Task 2.5 — 트레이 메뉴 + 부팅 자동 스캔

**Files:**
- Modify: `src/gah/app.py`
- Modify: `src/gah/tray.py`

- [ ] **Step 1**: 부팅 직후 별도 스레드 자동 스캔:

```python
# app.py run_tray() 안 (또는 시작 hook):
def _boot_unity_scan(config, store):
    from gah.core.unity_import.cache_paths import detect_cache_path
    from gah.core.unity_import.scanner import UnityAssetStoreScanner
    cache = detect_cache_path(config)
    if cache is None:
        return
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache)
    if result.new > 0:
        _notify_toast(f"Unity 캐시에 새 패키지 {result.new}개")

threading.Thread(target=_boot_unity_scan, args=(config, store), daemon=True).start()
```

- [ ] **Step 2**: 트레이 메뉴 액션 추가:

```python
# tray.py
class GahTray:
    def __init__(self, ...):
        # ...
        self.unity_scan_action = QAction("Unity 캐시 스캔", parent)
        self.unity_scan_action.triggered.connect(self._on_unity_scan)
        # 현재 프로젝트 서브메뉴
        self.project_menu = QMenu("현재 프로젝트", parent)
```

- [ ] **Step 3**: 회귀 — 트레이 UI 자동 테스트 어려우므로 단순 import smoke + headless 환경 회귀:
```bash
pytest tests/test_ui_smoke.py -v
pytest -q
```
→ 959 passed (회귀 0).

- [ ] **Step 4**: 커밋 — `feat(m7): 부팅 자동 스캔 + 트레이 "Unity 캐시 스캔" 메뉴`.

---

### 4.7 Phase 3A — MCP Pydantic 모델 + 도구 (~0.5일)

#### Task 3.1 — MCP 모델 + 도구 구현

**Files:**
- Modify: `src/gah/mcp/models.py`
- Modify: `src/gah/mcp/tools.py`
- Create: `tests/test_mcp_tools_m7.py`

- [ ] **Step 1: 실패 테스트** (~10 케이스):

```python
"""M7 — MCP scan_unity_asset_store_cache + list_unity_packages 도구."""
from __future__ import annotations

import pytest

from gah.mcp.tools import tool_scan_unity_asset_store_cache, tool_list_unity_packages
from gah.mcp.models import (
    ScanUnityAssetStoreCacheRequest,
    ListUnityPackagesRequest,
)
from gah.mcp.errors import McpError


def test_scan_normal(deps_with_cache):
    req = ScanUnityAssetStoreCacheRequest(force=False, filter=None)
    result = tool_scan_unity_asset_store_cache(deps_with_cache, req)
    assert result.scanned >= 0
    assert result.cache_path


def test_scan_cache_not_found(deps_no_cache):
    req = ScanUnityAssetStoreCacheRequest(force=False, filter=None)
    with pytest.raises(McpError) as exc:
        tool_scan_unity_asset_store_cache(deps_no_cache, req)
    assert "503" in str(exc.value) or "cache_not_found" in str(exc.value)


def test_scan_permission_denied(deps_with_unreadable_cache):
    req = ScanUnityAssetStoreCacheRequest(force=False, filter=None)
    # 권한 없음 시 결과 warnings 에 메시지 / 또는 403 에러
    result = tool_scan_unity_asset_store_cache(deps_with_unreadable_cache, req)
    assert any("permission" in w.lower() for w in result.warnings)


def test_list_returns_all(deps_with_some_imports):
    req = ListUnityPackagesRequest()
    result = tool_list_unity_packages(deps_with_some_imports, req)
    assert result.total >= 1


def test_list_filter_state(deps_with_some_imports):
    req = ListUnityPackagesRequest(state="discovered")
    result = tool_list_unity_packages(deps_with_some_imports, req)
    assert all(item.import_state == "discovered" for item in result.items)


def test_list_publisher_glob(deps_with_some_imports):
    req = ListUnityPackagesRequest(filter={"publisher_glob": "Kenney*"})
    result = tool_list_unity_packages(deps_with_some_imports, req)
    assert all(
        item.publisher and item.publisher.startswith("Kenney")
        for item in result.items
    )


def test_list_include_preview_populates(deps_with_some_imports):
    req = ListUnityPackagesRequest(include_preview=True)
    result = tool_list_unity_packages(deps_with_some_imports, req)
    assert any(item.preview_asset_count is not None for item in result.items)


def test_list_offset_limit(deps_with_many_imports):
    req = ListUnityPackagesRequest(offset=10, limit=5)
    result = tool_list_unity_packages(deps_with_many_imports, req)
    assert len(result.items) <= 5


def test_list_each_item_has_import_url(deps_with_some_imports):
    req = ListUnityPackagesRequest()
    result = tool_list_unity_packages(deps_with_some_imports, req)
    for item in result.items:
        assert item.import_url.startswith("http://")
        assert "/unity-asset-store" in item.import_url
        assert f"focus={item.id}" in item.import_url


def test_list_invalid_state(deps_with_some_imports):
    req = ListUnityPackagesRequest(state="bogus")
    with pytest.raises(McpError) as exc:
        tool_list_unity_packages(deps_with_some_imports, req)
    assert "400" in str(exc.value)
```

> `deps_*` fixture 는 conftest 에서 구성. 기존 M5/M6 패턴 따라 `deps = McpDeps(store=store, config=cfg, ...)`.

- [ ] **Step 2**: `pytest tests/test_mcp_tools_m7.py -v` → 10 FAIL.

- [ ] **Step 3: 모델 추가** `src/gah/mcp/models.py`:

```python
class ScanUnityAssetStoreCacheRequest(BaseModel):
    force: bool = False
    filter: ScanFilter | None = None

class ScanFilter(BaseModel):
    publisher_glob: str | None = None
    asset_name_glob: str | None = None

class ScanUnityAssetStoreCacheResult(BaseModel):
    scanned: int
    new: int
    updated: int
    unchanged: int
    removed: int
    cache_path: str
    warnings: list[str] = []

class ListUnityPackagesRequest(BaseModel):
    state: Literal[
        "discovered", "previewed", "import_pending",
        "imported", "skipped", "failed",
    ] | None = None
    filter: ScanFilter | None = None
    include_preview: bool = False
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)

class UnityPackageItem(BaseModel):
    id: int
    package_path: str
    publisher: str | None
    category: str | None
    asset_name: str
    package_size: int
    package_mtime: int
    import_state: str
    preview_asset_count: int | None
    preview_image_count: int | None
    preview_sound_count: int | None
    pack_id: int | None
    imported_at: int | None
    import_url: str

class ListUnityPackagesResult(BaseModel):
    total: int
    items: list[UnityPackageItem]
```

- [ ] **Step 4: 도구 구현** `src/gah/mcp/tools.py`:

```python
def tool_scan_unity_asset_store_cache(deps, req: ScanUnityAssetStoreCacheRequest):
    from gah.core.unity_import.cache_paths import detect_cache_path
    from gah.core.unity_import.scanner import UnityAssetStoreScanner

    cache = detect_cache_path(deps.config)
    if cache is None:
        raise McpError("503_cache_not_found", "Unity 캐시 경로를 찾을 수 없음")

    scanner = UnityAssetStoreScanner(store=deps.store)
    publisher_glob = req.filter.publisher_glob if req.filter else None
    asset_name_glob = req.filter.asset_name_glob if req.filter else None
    result = scanner.run_once(
        cache_path=cache, force=req.force,
        publisher_glob=publisher_glob, asset_name_glob=asset_name_glob,
    )
    return ScanUnityAssetStoreCacheResult(
        scanned=result.scanned, new=result.new, updated=result.updated,
        unchanged=result.unchanged, removed=result.removed,
        cache_path=str(result.cache_path),
        warnings=list(result.warnings),
    )


def tool_list_unity_packages(deps, req: ListUnityPackagesRequest):
    if req.state and req.state not in {
        "discovered", "previewed", "import_pending",
        "imported", "skipped", "failed",
    }:
        raise McpError("400_invalid_state", f"invalid state: {req.state}")

    publisher_glob = req.filter.publisher_glob if req.filter else None
    asset_name_glob = req.filter.asset_name_glob if req.filter else None
    rows = deps.store.list_unity_imports(
        state=req.state,
        publisher_glob=publisher_glob,
        asset_name_glob=asset_name_glob,
        offset=req.offset,
        limit=req.limit,
    )
    total = deps.store.count_unity_imports(
        state=req.state,
        publisher_glob=publisher_glob,
        asset_name_glob=asset_name_glob,
    )

    if req.include_preview:
        from gah.core.unity_import.unitypackage import parse_pathnames
        for r in rows:
            if r.preview_asset_count is None:
                entries = parse_pathnames(r.package_path)
                deps.store.update_unity_preview(
                    r.id,
                    asset_count=len(entries),
                    image_count=sum(1 for e in entries.values() if e.internal_kind == "image"),
                    sound_count=sum(1 for e in entries.values() if e.internal_kind == "sound"),
                )
        rows = deps.store.list_unity_imports(
            state=req.state,
            publisher_glob=publisher_glob,
            asset_name_glob=asset_name_glob,
            offset=req.offset,
            limit=req.limit,
        )

    base_url = deps.config.web_base_url  # 예: "http://127.0.0.1:9874"
    items = [
        UnityPackageItem(
            id=r.id, package_path=str(r.package_path),
            publisher=r.publisher, category=r.category,
            asset_name=r.asset_name,
            package_size=r.package_size, package_mtime=r.package_mtime,
            import_state=r.import_state,
            preview_asset_count=r.preview_asset_count,
            preview_image_count=r.preview_image_count,
            preview_sound_count=r.preview_sound_count,
            pack_id=r.pack_id, imported_at=r.imported_at,
            import_url=f"{base_url}/unity-asset-store?focus={r.id}",
        )
        for r in rows
    ]
    return ListUnityPackagesResult(total=total, items=items)
```

- [ ] **Step 5**: `pytest tests/test_mcp_tools_m7.py -v` → 10 passed.

- [ ] **Step 6**: 회귀 `pytest -q` → 959 + 10 = **969 passed**.

- [ ] **Step 7**: 커밋 — `feat(m7): MCP scan + list 도구 (19, 20번째) + Pydantic 모델`.

---

### 4.8 Phase 3B — MCP server 등록 + INSTRUCTIONS + integration (~0.5일)

#### Task 3.2 — register_all_tools 18 → 20 + INSTRUCTIONS

**Files:**
- Modify: `src/gah/mcp/server.py`

- [ ] **Step 1**: `register_all_tools` 함수에 2 도구 추가, 로그 메시지 변경:

```python
mcp.tool()(tool_scan_unity_asset_store_cache)
mcp.tool()(tool_list_unity_packages)
logger.info("MCP server tools=20 instructions_chars=%d", len(INSTRUCTIONS))
```

- [ ] **Step 2**: `INSTRUCTIONS` 텍스트에 Unity Asset Store 워크플로 문단 추가:

```
## Unity Asset Store 통합 (M7)

GAH 는 Unity Asset Store 로컬 캐시(.unitypackage) 도 인덱싱한다. 사용자가
이미 다운받아 둔 패키지 중 어떤 게 라이브러리에 임포트됐는지·아직 안 됐는지
파악하려면:

  scan_unity_asset_store_cache    — 캐시 디렉터리 재스캔.
  list_unity_packages(state="discovered")
                                  — 아직 임포트 안 된 패키지 목록.
                                    각 row 의 import_url 로 사용자에게
                                    "이 패키지 임포트하려면 <URL>" 안내.

임포트(파일 추출) 자체는 사용자가 웹 UI 에서 직접 트리거해야 한다 — MCP
도구로는 임포트할 수 없다(사용자 통제 보존).
```

#### Task 3.3 — mcp_integration 20 도구 검증

**Files:**
- Modify: `tests/test_mcp_integration.py`

- [ ] **Step 1**: integration 테스트 (opt-in `pytest -m mcp_integration -v`) 에서 `tools/list` 응답 검증 카운트 18 → 20.

- [ ] **Step 2**: `pytest -m mcp_integration -v` → 2 passed (도구 카운트 20 확인).

- [ ] **Step 3**: 회귀 `pytest -q` → 969 passed (회귀 0).

- [ ] **Step 4**: 커밋 — `feat(m7): MCP server 등록 20 도구 + INSTRUCTIONS Unity 워크플로`.

---

### 4.9 Phase 4A — `/unity-asset-store` 라우터 + SSE + skeleton (~1일)

#### Task 4.1 — 라우터 + 6 endpoint + SSE

**Files:**
- Create: `src/gah/web/routers/unity_asset_store.py`
- Modify: `src/gah/web/app.py` (또는 `server.py`) — 라우터 등록
- Create: `tests/test_web_routers_unity.py`

- [ ] **Step 1: 실패 테스트** (~8 케이스):

```python
"""M7 — /unity-asset-store 라우터 + API 회귀."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def app_with_cache(tmp_path, monkeypatch, store):
    """fixture: 작은 fake 캐시 + GAH FastAPI 앱."""
    cache = tmp_path / "cache"
    pub = cache / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega.unitypackage", include_psd=False)
    monkeypatch.setenv("ASSETSTORE_CACHE_PATH", str(cache))
    from gah.web.app import create_app
    app = create_app(store=store)
    return app, cache


def test_get_unity_page_renders(app_with_cache):
    app, _ = app_with_cache
    client = TestClient(app)
    r = client.get("/unity-asset-store")
    assert r.status_code == 200
    assert "Unity Asset Store" in r.text


def test_scan_api_creates_rows(app_with_cache, store):
    app, _ = app_with_cache
    client = TestClient(app)
    r = client.post("/api/unity-packages/scan", json={"force": False})
    assert r.status_code == 200
    rows = store.list_unity_imports()
    assert len(rows) >= 1


def test_preview_api_updates_state(app_with_cache, store):
    app, _ = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.post(f"/api/unity-packages/{uid}/preview")
    assert r.status_code == 200
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "previewed"
    assert row.preview_asset_count is not None


def test_import_api_triggers_extract(app_with_cache, store, tmp_path):
    app, _ = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.post(f"/api/unity-packages/{uid}/import")
    assert r.status_code in (200, 202)


def test_skip_api(app_with_cache, store):
    app, _ = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.post(f"/api/unity-packages/{uid}/skip")
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "skipped"


def test_restore_api(app_with_cache, store):
    app, _ = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    store.update_unity_state(uid, "skipped")
    r = client.post(f"/api/unity-packages/{uid}/restore")
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "discovered"


def test_focus_query_highlight(app_with_cache, store):
    app, _ = app_with_cache
    client = TestClient(app)
    client.post("/api/unity-packages/scan", json={"force": False})
    uid = store.list_unity_imports()[0].id
    r = client.get(f"/unity-asset-store?focus={uid}")
    assert r.status_code == 200
    assert f'data-focus="{uid}"' in r.text or f'id="row-{uid}"' in r.text


def test_empty_cache_message(store, monkeypatch):
    monkeypatch.delenv("ASSETSTORE_CACHE_PATH", raising=False)
    from gah.web.app import create_app
    app = create_app(store=store)
    client = TestClient(app)
    r = client.get("/unity-asset-store")
    assert r.status_code == 200
    assert "캐시 경로" in r.text or "cache path" in r.text.lower()
```

- [ ] **Step 2**: `pytest tests/test_web_routers_unity.py -v` → 8 FAIL.

- [ ] **Step 3: 라우터 구현** `src/gah/web/routers/unity_asset_store.py`:

```python
"""M7 — /unity-asset-store 페이지 + /api/unity-packages 그룹.

GET /unity-asset-store         HTML (발견 목록 표 + 상태 칩 + scan 버튼)
POST /api/unity-packages/scan  스캐너 실행 → JSON 결과
POST /api/unity-packages/{id}/preview  pathname 읽기 → 카운트 채움
POST /api/unity-packages/{id}/import   백그라운드 importer 큐 등록
POST /api/unity-packages/{id}/skip     state=skipped
POST /api/unity-packages/{id}/restore  state=discovered
GET  /api/unity-packages/stream         SSE 진행 (scan_progress / import_progress)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from gah.core.unity_import.cache_paths import detect_cache_path
from gah.core.unity_import.importer import UnityImporter
from gah.core.unity_import.scanner import UnityAssetStoreScanner
from gah.core.unity_import.unitypackage import parse_pathnames
from gah.web.deps import get_deps

router = APIRouter()


@router.get("/unity-asset-store", response_class=HTMLResponse)
async def unity_page(request: Request, deps=Depends(get_deps)):
    cache = detect_cache_path(deps.config)
    items = deps.store.list_unity_imports() if cache else []
    focus = request.query_params.get("focus")
    return deps.templates.TemplateResponse(
        "unity_asset_store.html",
        {
            "request": request,
            "items": items,
            "cache_path": str(cache) if cache else None,
            "focus_id": int(focus) if focus and focus.isdigit() else None,
        },
    )


@router.post("/api/unity-packages/scan")
async def api_scan(body: dict, deps=Depends(get_deps)):
    cache = detect_cache_path(deps.config)
    if cache is None:
        raise HTTPException(status_code=503, detail="cache_not_found")
    scanner = UnityAssetStoreScanner(store=deps.store)
    result = scanner.run_once(
        cache_path=cache,
        force=body.get("force", False),
    )
    return {
        "scanned": result.scanned, "new": result.new,
        "updated": result.updated, "unchanged": result.unchanged,
        "removed": result.removed,
    }


@router.post("/api/unity-packages/{uid}/preview")
async def api_preview(uid: int, deps=Depends(get_deps)):
    row = deps.store.get_unity_import_by_id(uid)
    if row is None:
        raise HTTPException(404, "not found")
    entries = parse_pathnames(row.package_path)
    deps.store.update_unity_preview(
        uid,
        asset_count=len(entries),
        image_count=sum(1 for e in entries.values() if e.internal_kind == "image"),
        sound_count=sum(1 for e in entries.values() if e.internal_kind == "sound"),
    )
    deps.store.update_unity_state(uid, "previewed")
    return {"ok": True}


@router.post("/api/unity-packages/{uid}/import")
async def api_import(uid: int, deps=Depends(get_deps)):
    row = deps.store.get_unity_import_by_id(uid)
    if row is None:
        raise HTTPException(404, "not found")
    deps.store.update_unity_state(uid, "import_pending")
    # 백그라운드 큐
    importer = UnityImporter(store=deps.store, library_root=deps.library_root)
    result = importer.import_package(uid)
    # SSE 진행 emit 은 별도 채널 — 본 endpoint 는 동기 응답
    return {
        "state": result.state, "pack_name": result.pack_name,
        "asset_count": result.asset_count, "error": result.error,
    }


@router.post("/api/unity-packages/{uid}/skip")
async def api_skip(uid: int, deps=Depends(get_deps)):
    deps.store.update_unity_state(uid, "skipped")
    return {"ok": True}


@router.post("/api/unity-packages/{uid}/restore")
async def api_restore(uid: int, deps=Depends(get_deps)):
    deps.store.update_unity_state(uid, "discovered")
    return {"ok": True}
```

> SSE progress (scan_progress / import_progress) 는 단순화 — initial implementation 은 동기. 추후 v2 에서 EventSourceResponse 채널 추가.

- [ ] **Step 4: 라우터 등록** `src/gah/web/app.py`:

```python
from gah.web.routers import unity_asset_store
app.include_router(unity_asset_store.router)
```

- [ ] **Step 5**: `pytest tests/test_web_routers_unity.py -v` → 8 passed.

- [ ] **Step 6**: 회귀 `pytest -q` → 969 + 8 = **977 passed**.

- [ ] **Step 7**: 커밋 — `feat(m7): /unity-asset-store 라우터 + 6 endpoint`.

---

### 4.10 Phase 4B — Unity 페이지 HTML + 사이드바 + CSS (~0.5일)

#### Task 4.2 — unity_asset_store.html + 사이드바 + 상태 칩 CSS

**Files:**
- Create: `src/gah/web/templates/unity_asset_store.html`
- Create: `src/gah/web/templates/_unity_package_row.html`
- Modify: `src/gah/web/templates/base.html` (사이드바 메뉴 추가)
- Modify: `src/gah/web/static/css/main.css`
- Modify: `src/gah/web/static/css/themes.css`

- [ ] **Step 1**: `unity_asset_store.html` — 페이지 본문:

```html
{# M7 — Unity Asset Store 발견 패키지 표 #}
{% extends "base.html" %}
{% block title %}Unity Asset Store{% endblock %}
{% block main %}
<section class="unity-page" x-data="unityPage()">
  <header class="unity-header">
    <h1>{{ _("Unity Asset Store") }}</h1>
    {% if cache_path %}
      <p class="unity-cache-path">
        {{ _("캐시 경로") }}: <code>{{ cache_path }}</code>
      </p>
    {% else %}
      <p class="unity-empty">{{ _("캐시 경로가 비어 있습니다. 설정에서 Unity Asset Store 캐시 경로를 입력하세요.") }}</p>
    {% endif %}
    <button @click="scan()" :disabled="scanning">
      {{ _("캐시 스캔") }}
    </button>
  </header>
  <div class="unity-filter">
    {% for s in ("discovered", "previewed", "import_pending", "imported", "skipped", "failed") %}
      <button class="state-chip" :class="{'active': activeState === '{{ s }}'}"
              @click="setState('{{ s }}')">{{ s }}</button>
    {% endfor %}
  </div>
  <table class="unity-table">
    <thead>
      <tr>
        <th>{{ _("Publisher") }}</th>
        <th>{{ _("Category") }}</th>
        <th>{{ _("Asset name") }}</th>
        <th>{{ _("Size") }}</th>
        <th>{{ _("mtime") }}</th>
        <th>{{ _("State") }}</th>
        <th>{{ _("Preview") }}</th>
        <th>{{ _("Actions") }}</th>
      </tr>
    </thead>
    <tbody id="unity-rows">
      {% for item in items %}
        {% include "_unity_package_row.html" %}
      {% endfor %}
    </tbody>
  </table>
</section>
<script>
function unityPage() {
  return {
    scanning: false,
    activeState: null,
    focusId: {{ focus_id|tojson if focus_id else 'null' }},
    init() {
      if (this.focusId) {
        const row = document.querySelector(`[data-focus="${this.focusId}"]`);
        if (row) row.scrollIntoView({block: "center"});
      }
    },
    async scan() {
      this.scanning = true;
      const r = await fetch("/api/unity-packages/scan", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({force: false}),
      });
      this.scanning = false;
      location.reload();
    },
    setState(s) { this.activeState = s === this.activeState ? null : s; },
  };
}
</script>
{% endblock %}
```

- [ ] **Step 2**: `_unity_package_row.html` fragment:

```html
{# M7 — Unity package 표 row (HTMX swap 대상) #}
<tr {% if focus_id == item.id %}data-focus="{{ item.id }}" class="row-focus"{% endif %}>
  <td>{{ item.publisher or "—" }}</td>
  <td>{{ item.category or "—" }}</td>
  <td><strong>{{ item.asset_name }}</strong></td>
  <td>{{ item.package_size }}</td>
  <td>{{ item.package_mtime }}</td>
  <td>
    <span class="state-chip state-{{ item.import_state }}">
      {{ item.import_state }}
    </span>
  </td>
  <td>
    {% if item.preview_asset_count %}
      🖼 {{ item.preview_image_count }} · 🔊 {{ item.preview_sound_count }}
    {% else %}
      —
    {% endif %}
  </td>
  <td class="unity-actions">
    {% if item.import_state in ("discovered", "previewed", "skipped") %}
      <button hx-post="/api/unity-packages/{{ item.id }}/preview"
              hx-target="closest tr" hx-swap="outerHTML">{{ _("미리보기") }}</button>
      <button hx-post="/api/unity-packages/{{ item.id }}/import"
              hx-target="closest tr" hx-swap="outerHTML"
              hx-confirm="{{ _('이 패키지를 임포트합니다. 계속할까요?') }}">{{ _("임포트") }}</button>
    {% endif %}
    {% if item.import_state in ("discovered", "previewed") %}
      <button hx-post="/api/unity-packages/{{ item.id }}/skip"
              hx-target="closest tr" hx-swap="outerHTML">{{ _("건너뜀") }}</button>
    {% endif %}
    {% if item.import_state == "skipped" %}
      <button hx-post="/api/unity-packages/{{ item.id }}/restore"
              hx-target="closest tr" hx-swap="outerHTML">{{ _("다시 후보로") }}</button>
    {% endif %}
  </td>
</tr>
```

- [ ] **Step 3**: 사이드바 메뉴 — `base.html` 의 사이드바 fragment 에 신규 2개 추가:

```html
<nav class="sidebar">
  <a href="/library">{{ _("라이브러리") }}</a>
  <a href="/packs">{{ _("팩") }}</a>
  <a href="/labels">{{ _("라벨") }}</a>
  <a href="/search">{{ _("검색") }}</a>
  <hr class="sidebar-divider">
  <a href="/projects">{{ _("프로젝트") }}</a>
  <a href="/unity-asset-store">{{ _("Unity Asset Store") }}</a>
  <hr class="sidebar-divider">
  <a href="/settings">{{ _("설정") }}</a>
</nav>
```

- [ ] **Step 4**: CSS — `main.css` 에 추가:

```css
/* M7 — Unity Asset Store */
.unity-table { width: 100%; border-collapse: collapse; }
.unity-table th, .unity-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }
.state-chip {
  padding: 2px 8px; border-radius: 12px; font-size: 0.8em;
  background: var(--chip-bg); color: var(--chip-fg);
}
.state-chip.state-discovered { background: var(--chip-discovered-bg); }
.state-chip.state-previewed  { background: var(--chip-previewed-bg); }
.state-chip.state-imported   { background: var(--chip-imported-bg); }
.state-chip.state-skipped    { background: var(--chip-skipped-bg); color: var(--chip-skipped-fg); }
.state-chip.state-failed     { background: var(--chip-failed-bg); color: var(--chip-failed-fg); }
.row-focus { outline: 2px solid var(--focus-outline); }
.sidebar-divider { border: 0; border-top: 1px solid var(--border-color); margin: 8px 0; }
```

`themes.css` — light/dark 변수 추가:

```css
:root {
  --chip-bg: #eee; --chip-fg: #333;
  --chip-discovered-bg: #cce4ff;
  --chip-previewed-bg: #d4edff;
  --chip-imported-bg: #d4edda;
  --chip-skipped-bg: #f0f0f0; --chip-skipped-fg: #777;
  --chip-failed-bg: #f8d7da; --chip-failed-fg: #721c24;
  --focus-outline: #ffaa00;
}
[data-theme="dark"] {
  --chip-bg: #333; --chip-fg: #ddd;
  --chip-discovered-bg: #1f3a5f;
  --chip-previewed-bg: #2a4a6f;
  --chip-imported-bg: #2a5f3a;
  --chip-skipped-bg: #444; --chip-skipped-fg: #999;
  --chip-failed-bg: #5f2a2a; --chip-failed-fg: #f8d7da;
  --focus-outline: #ffcc55;
}
```

- [ ] **Step 5**: 회귀 `pytest -q` → 977 passed (회귀 0, UI 만 변경).

- [ ] **Step 6**: 커밋 — `feat(m7): Unity Asset Store 페이지 HTML + 상태 칩 CSS + 사이드바`.

---

### 4.11 Phase 5 — 활성 프로젝트 컨텍스트 + 채택 통합 (~1일)

> Cross-cutting phase: 글로벌 헤더 / 라우터 / 라이브러리 카드 / SSE / Alpine state 동시 변경. 가장 큰 phase.

#### Task 5.1 — 활성 프로젝트 라우터 + API 4개 + SSE broadcast

**Files:**
- Create: `src/gah/web/routers/projects.py` (M7 의 첫 절반 — active project API)
- Modify: `src/gah/web/app.py` — 라우터 등록
- Create: `tests/test_web_active_project.py`

- [ ] **Step 1: 실패 테스트** (~8 케이스):

```python
"""M7 — 활성 프로젝트 + 채택 API 회귀."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_for_projects(store, tmp_path):
    from gah.web.app import create_app
    app = create_app(store=store)
    return app


def test_get_active_project_none(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/api/active-project")
    assert r.status_code == 200
    assert r.json() == {"active": None}


def test_put_active_project_sets_config(app_for_projects, store):
    store.upsert_project(external_id="D:/X", display_name="X")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    r = client.put("/api/active-project", json={"project_id": pid})
    assert r.status_code == 200
    r2 = client.get("/api/active-project")
    assert r2.json()["active"]["id"] == pid


def test_put_active_project_clear(app_for_projects, store):
    store.upsert_project(external_id="D:/X", display_name="X")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.put("/api/active-project", json={"project_id": None})
    assert r.status_code == 200
    r2 = client.get("/api/active-project")
    assert r2.json() == {"active": None}


def test_post_projects_creates(app_for_projects, store):
    client = TestClient(app_for_projects)
    r = client.post("/api/projects", json={
        "external_id": "D:/Unity/MyGame",
        "display_name": "MyGame",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"] > 0


def test_post_adopt_active_project(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="A")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    asset_id = asset_factory()
    r = client.post(f"/api/assets/{asset_id}/adopt", json={"context": "x"})
    assert r.status_code == 200


def test_post_adopt_without_active_project(app_for_projects, asset_factory):
    client = TestClient(app_for_projects)
    asset_id = asset_factory()
    r = client.post(f"/api/assets/{asset_id}/adopt", json={"context": "x"})
    assert r.status_code == 400
    assert "no_active_project" in r.json().get("detail", "")


def test_adopt_records_source_user_web(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="A")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    asset_id = asset_factory()
    client.post(f"/api/assets/{asset_id}/adopt", json={})
    rows = store.get_project_asset_usage(project_id=pid)
    assert any(r.source == "user_web" for r in rows)


def test_sse_active_project_changed(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="A")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    # SSE stream 은 long-poll — 변경 후 첫 이벤트 받기
    with client.stream("GET", "/api/active-project/stream") as resp:
        client.put("/api/active-project", json={"project_id": pid})
        # 첫 이벤트 1개만 읽고 종료
        for line in resp.iter_lines():
            if "active_project_changed" in line:
                return
        assert False, "no active_project_changed event"
```

- [ ] **Step 2**: `pytest tests/test_web_active_project.py -v` → 8 FAIL.

- [ ] **Step 3: 구현** `src/gah/web/routers/projects.py` 의 active-project API 부분:

```python
"""M7 — /projects + /api/active-project + /api/projects + /api/assets/<id>/adopt.

활성 프로젝트는 Config 에 영속. SSE broadcast 로 모든 탭 동기.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from gah.web.deps import get_deps

router = APIRouter()

# SSE 구독자 큐 (간단 구현 — single-process)
_subscribers: list[asyncio.Queue] = []


def _broadcast(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


@router.get("/api/active-project")
async def get_active(deps=Depends(get_deps)):
    pid = deps.config.active_project_id
    if pid is None:
        return {"active": None}
    p = deps.store.get_project_by_id(pid)
    if p is None:
        return {"active": None}
    return {"active": {"id": p.id, "external_id": p.external_id, "display_name": p.display_name}}


@router.put("/api/active-project")
async def put_active(body: dict, deps=Depends(get_deps)):
    pid = body.get("project_id")
    deps.config.active_project_id = pid
    deps.save_config()
    _broadcast({"event": "active_project_changed", "project_id": pid})
    return {"ok": True}


@router.post("/api/projects")
async def post_project(body: dict, deps=Depends(get_deps)):
    ext_id = body.get("external_id")
    display_name = body.get("display_name")
    if not ext_id:
        raise HTTPException(400, "external_id required")
    pid = deps.store.upsert_project(external_id=ext_id, display_name=display_name)
    return {"id": pid, "external_id": ext_id, "display_name": display_name}


@router.post("/api/assets/{asset_id}/adopt")
async def post_adopt(asset_id: int, body: dict, deps=Depends(get_deps)):
    pid = deps.config.active_project_id
    if pid is None:
        raise HTTPException(400, "no_active_project")
    asset = deps.store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    deps.store.record_asset_use(
        project_id=pid, asset_id=asset_id, pack_id=asset.pack_id,
        source="user_web", context=body.get("context"),
        used_at=int(time.time()),
    )
    return {"ok": True}


@router.get("/api/active-project/stream")
async def active_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _subscribers.append(q)
    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await q.get()
                yield {"event": event["event"], "data": json.dumps(event)}
        finally:
            _subscribers.remove(q)
    return EventSourceResponse(gen())
```

- [ ] **Step 4: 라우터 등록** `web/app.py`:

```python
from gah.web.routers import projects
app.include_router(projects.router)
```

- [ ] **Step 5**: `pytest tests/test_web_active_project.py -v` → 8 passed.

- [ ] **Step 6**: 회귀 `pytest -q` → 977 + 8 = **985 passed**.

- [ ] **Step 7**: 커밋 — `feat(m7): 활성 프로젝트 API + SSE broadcast + 채택 endpoint`.

#### Task 5.2 — 글로벌 헤더 드롭다운 fragment + 새 프로젝트 모달

**Files:**
- Create: `src/gah/web/templates/_header_project_dropdown.html`
- Create: `src/gah/web/templates/_modal_new_project.html`
- Modify: `src/gah/web/templates/base.html` — 헤더에 fragment 포함

- [ ] **Step 1: 헤더 fragment**:

```html
{# M7 — 글로벌 헤더 활성 프로젝트 드롭다운 (D12) #}
<div class="header-project" x-data="headerProject()" x-init="init()">
  <button class="header-project-chip" @click="open = !open">
    <span x-show="active">{{ _("현재 프로젝트") }}: <strong x-text="active?.display_name || active?.external_id"></strong></span>
    <span x-show="!active">{{ _("프로젝트 선택") }}</span>
    <span class="caret">▾</span>
  </button>
  <div class="header-project-menu" x-show="open" @click.away="open = false">
    <template x-for="p in projects">
      <button class="menu-item" @click="setActive(p.id)" :class="{'active': active?.id === p.id}">
        <span x-text="p.display_name || p.external_id"></span>
      </button>
    </template>
    <hr>
    <button class="menu-item" @click="openNew()">{{ _("➕ 새 프로젝트") }}</button>
    <button class="menu-item" @click="setActive(null)" x-show="active">{{ _("선택 해제") }}</button>
  </div>
  {% include "_modal_new_project.html" %}
</div>
<script>
function headerProject() {
  return {
    open: false,
    showModal: false,
    active: null,
    projects: [],
    newExternal: "",
    newDisplay: "",
    async init() {
      await this.refresh();
      this.subscribe();
    },
    async refresh() {
      this.active = (await (await fetch("/api/active-project")).json()).active;
      this.projects = await (await fetch("/api/projects")).json();
    },
    subscribe() {
      const es = new EventSource("/api/active-project/stream");
      es.addEventListener("active_project_changed", () => this.refresh());
    },
    async setActive(pid) {
      await fetch("/api/active-project", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({project_id: pid}),
      });
      this.open = false;
    },
    openNew() { this.showModal = true; this.open = false; },
    async createNew() {
      const r = await fetch("/api/projects", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({external_id: this.newExternal, display_name: this.newDisplay}),
      });
      const body = await r.json();
      await this.setActive(body.id);
      this.showModal = false;
      this.newExternal = "";
      this.newDisplay = "";
    },
  };
}
</script>
```

- [ ] **Step 2: 새 프로젝트 모달 fragment**:

```html
{# M7 — 새 프로젝트 생성 모달 #}
<div class="modal-overlay" x-show="showModal" @click.self="showModal = false">
  <div class="modal-content">
    <h2>{{ _("새 프로젝트") }}</h2>
    <label>
      {{ _("프로젝트 경로 / external_id") }}
      <input type="text" x-model="newExternal" placeholder="D:/Unity/MyGame">
    </label>
    <label>
      {{ _("표시 이름") }}
      <input type="text" x-model="newDisplay" placeholder="MyGame">
    </label>
    <div class="modal-actions">
      <button @click="showModal = false">{{ _("취소") }}</button>
      <button @click="createNew()" :disabled="!newExternal">{{ _("생성") }}</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: base.html** — 헤더에 fragment 포함:

```html
<header class="app-header">
  <a href="/" class="app-logo">GAH</a>
  {% include "_header_project_dropdown.html" %}
</header>
```

- [ ] **Step 4**: 회귀 `pytest -q` → 985 passed (UI 만 변경, 회귀 0). 헤더 렌더 검증은 다음 단계 통합 테스트에 포함.

- [ ] **Step 5**: 커밋 — `feat(m7): 글로벌 헤더 활성 프로젝트 드롭다운 + 새 프로젝트 모달`.

#### Task 5.3 — 라이브러리 카드 채택 버튼 통합

**Files:**
- Modify: `src/gah/web/routers/library.py`
- Modify: `src/gah/web/templates/_card_wide.html` / `_card_list.html`
- Modify: `src/gah/web/routers/feedback.py`
- Modify: `src/gah/web/routers/picks.py`
- Create: `tests/test_web_card_adopt_button.py`

- [ ] **Step 1: 실패 테스트** (~5 케이스):

```python
"""M7 — 라이브러리 카드 채택 버튼 활성 프로젝트 연동."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_adopt_button_enabled_with_active(app_for_projects, store):
    store.upsert_project(external_id="D:/X", display_name="X")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.get("/library")
    assert r.status_code == 200
    assert "adopt-btn" in r.text
    assert "disabled" not in r.text or "data-disabled=\"false\"" in r.text


def test_adopt_button_disabled_without_active(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/library")
    assert "data-disabled=\"true\"" in r.text or 'disabled' in r.text


def test_adopt_button_tooltip_when_disabled(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/library")
    assert "프로젝트를 먼저 선택" in r.text or "select a project" in r.text.lower()


def test_adopt_post_records_with_active(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/X", display_name="X")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    asset_id = asset_factory()
    r = client.post(f"/api/assets/{asset_id}/adopt", json={})
    assert r.status_code == 200
    rows = store.get_project_asset_usage(project_id=pid)
    assert any(r.asset_id == asset_id and r.source == "user_web" for r in rows)


def test_search_passes_active_project_id(app_for_projects, store):
    store.upsert_project(external_id="D:/X", display_name="X")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    # 검색 호출 시 응답에 project_id 가 포함되거나 결과가 통일성 가중치 반영된 것 확인
    r = client.get("/api/find_asset?q=sword")
    assert r.status_code == 200
    # 통일성 가중치 반영 검증은 ConsistencyScorer 테스트에 위임. 여기는 호출만 검증.
```

- [ ] **Step 2: `_card_wide.html` 갱신**:

```html
{# 채택 버튼 — 활성 프로젝트 없으면 disabled #}
<button class="adopt-btn"
        :data-disabled="!active"
        :disabled="!active"
        :title="active ? '' : '{{ _('프로젝트를 먼저 선택하세요') }}'"
        @click="adopt({{ row.asset_id }})">
  {{ _("채택") }}
</button>
```

- [ ] **Step 3: library router** — `_hit_to_row` 또는 검색 호출에 활성 프로젝트 주입:

```python
@router.get("/api/find_asset")
async def api_find_asset(q: str, deps=Depends(get_deps)):
    project_id = deps.config.active_project_id  # 활성 프로젝트 자동 주입
    request = FindAssetRequest(query=q, project_id=project_id, ...)
    return tool_find_asset(deps, request)
```

- [ ] **Step 4: feedback router** — 동일 패턴으로 `project_id` 주입.

- [ ] **Step 5: picks router** — 사용자 채택 endpoint 가 활성 프로젝트로 `record_asset_use(source="claude_pick")`.

- [ ] **Step 6**: `pytest tests/test_web_card_adopt_button.py -v` → 5 passed.

- [ ] **Step 7**: 회귀 `pytest -q` → 985 + 5 = **990 passed**.

- [ ] **Step 8**: 커밋 — `feat(m7): 라이브러리 카드 채택 버튼 + 검색/피드백/픽 활성 프로젝트 연동`.

---

### 4.12 Phase 6A — `/projects` 라우터 + 페이지 (~0.5일)

#### Task 6.1 — /projects GET + 페이지 HTML

**Files:**
- Modify: `src/gah/web/routers/projects.py` — `/projects` GET 추가
- Create: `src/gah/web/templates/projects_list.html`
- Create: `tests/test_web_routers_projects.py` (Phase 6A 부분)

- [ ] **Step 1: 실패 테스트** (~4 케이스, 본 phase 분):

```python
"""M7 — /projects 목록 페이지 회귀."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_projects_page_renders_empty(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert r.status_code == 200
    assert "프로젝트" in r.text or "Projects" in r.text


def test_projects_page_lists_projects(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    store.upsert_project(external_id="D:/B", display_name="GameB")
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert "GameA" in r.text
    assert "GameB" in r.text


def test_projects_page_highlights_active(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.get("/projects")
    assert f'data-active="{pid}"' in r.text or "row-active" in r.text


def test_projects_page_has_new_button(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert "새 프로젝트" in r.text or "new project" in r.text.lower()
```

- [ ] **Step 2: 라우터 구현**:

```python
@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, deps=Depends(get_deps)):
    rows = deps.store.list_projects_with_summary()
    active = deps.config.active_project_id
    return deps.templates.TemplateResponse(
        "projects_list.html",
        {"request": request, "rows": rows, "active_project_id": active},
    )
```

- [ ] **Step 3: 페이지 HTML** `projects_list.html`:

```html
{% extends "base.html" %}
{% block title %}{{ _("프로젝트") }}{% endblock %}
{% block main %}
<section class="projects-page" x-data="projectsPage()">
  <header>
    <h1>{{ _("프로젝트") }}</h1>
    <button @click="showModal = true">{{ _("➕ 새 프로젝트") }}</button>
  </header>
  <table class="projects-table">
    <thead>
      <tr>
        <th>{{ _("표시 이름") }}</th>
        <th>{{ _("external_id") }}</th>
        <th>{{ _("첫 발견") }}</th>
        <th>{{ _("마지막 활동") }}</th>
        <th>{{ _("채택 자산") }}</th>
        <th>{{ _("주력 팩") }}</th>
        <th>{{ _("핀/블록") }}</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {% for r in rows %}
        <tr {% if r.id == active_project_id %}class="row-active" data-active="{{ r.id }}"{% endif %}>
          <td><strong>{{ r.display_name or r.external_id }}</strong></td>
          <td><code>{{ r.external_id }}</code></td>
          <td>{{ r.first_seen }}</td>
          <td>{{ r.last_seen }}</td>
          <td>{{ r.asset_count }}</td>
          <td>{{ r.top_pack_name or "—" }}</td>
          <td>
            {% if r.pinned_pack_id %}📌 {{ r.pinned_pack_name }}{% endif %}
            {% if r.blocked_count %}🚫 {{ r.blocked_count }}{% endif %}
          </td>
          <td><a href="/projects/{{ r.id }}">{{ _("상세") }}</a></td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
  {% include "_modal_new_project.html" %}
</section>
<script>
function projectsPage() { return { showModal: false, newExternal: "", newDisplay: "",
  async createNew() {
    const r = await fetch("/api/projects", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({external_id: this.newExternal, display_name: this.newDisplay})});
    location.reload();
  }
}; }
</script>
{% endblock %}
```

- [ ] **Step 4**: `pytest tests/test_web_routers_projects.py -v` → 4 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 990 + 4 = **994 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): /projects 목록 페이지 + 활성 프로젝트 강조`.

---

### 4.13 Phase 6B — `/projects/<id>` 사용 이력 + 채택 팩 분포 (~0.5일)

#### Task 6.2 — /projects/<id> GET + 사용 이력 + 분포

**Files:**
- Modify: `src/gah/web/routers/projects.py`
- Create: `src/gah/web/templates/project_detail.html`
- Modify: `tests/test_web_routers_projects.py`

- [ ] **Step 1: 실패 테스트** (~4 추가 케이스):

```python
def test_project_detail_renders(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert r.status_code == 200
    assert "GameA" in r.text


def test_project_detail_404(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/projects/9999")
    assert r.status_code == 404


def test_project_detail_shows_usage_table(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    aid = asset_factory()
    store.record_asset_use(
        project_id=pid, asset_id=aid, pack_id=1,
        source="explicit", used_at=1, context="lvl1",
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "lvl1" in r.text


def test_project_detail_pack_distribution(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    aid = asset_factory()
    for _ in range(3):
        store.record_asset_use(
            project_id=pid, asset_id=aid, pack_id=1,
            source="explicit", used_at=1,
        )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "pack-distribution" in r.text
```

- [ ] **Step 2: 라우터 구현**:

```python
@router.get("/projects/{pid}", response_class=HTMLResponse)
async def project_detail(pid: int, request: Request, deps=Depends(get_deps)):
    project = deps.store.get_project_by_id(pid)
    if project is None:
        raise HTTPException(404, "project not found")
    usage = deps.store.get_project_asset_usage(project_id=pid, limit=100)
    distribution = deps.store.get_project_pack_distribution(project_id=pid, top_n=5)
    preferences = deps.store.get_project_asset_preferences(project_id=pid, sort="score_desc", limit=50)
    active = deps.config.active_project_id
    return deps.templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request, "project": project,
            "usage": usage, "distribution": distribution,
            "preferences": preferences, "is_active": project.id == active,
        },
    )
```

- [ ] **Step 3: 페이지 HTML** `project_detail.html` (헤더 + 사용 이력 + 분포 부분만 — 선호도 패널은 6C):

```html
{% extends "base.html" %}
{% block title %}{{ project.display_name or project.external_id }}{% endblock %}
{% block main %}
<section class="project-detail">
  <header>
    <h1>{{ project.display_name or project.external_id }}</h1>
    <p class="project-meta">
      <code>{{ project.external_id }}</code>
      {% if is_active %}<span class="active-chip">{{ _("현재 활성") }}</span>{% endif %}
    </p>
    <div class="project-actions">
      {% if not is_active %}
        <button hx-put="/api/active-project" hx-vals='{"project_id": {{ project.id }}}'>
          {{ _("활성 프로젝트로 설정") }}
        </button>
      {% endif %}
    </div>
  </header>

  <section class="project-usage">
    <h2>{{ _("자산 사용 이력") }}</h2>
    <table>
      <thead>
        <tr>
          <th>{{ _("자산") }}</th>
          <th>{{ _("팩") }}</th>
          <th>{{ _("source") }}</th>
          <th>{{ _("사용 시점") }}</th>
          <th>{{ _("context") }}</th>
        </tr>
      </thead>
      <tbody>
        {% for u in usage %}
          <tr>
            <td><a href="/asset/{{ u.asset_id }}">{{ u.asset_path }}</a></td>
            <td>{{ u.pack_name }}</td>
            <td>{{ u.source }}</td>
            <td>{{ u.used_at }}</td>
            <td>{{ u.context or "" }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="project-distribution">
    <h2>{{ _("채택 팩 분포") }}</h2>
    <ul class="pack-distribution">
      {% set total = distribution|sum(attribute="uses") or 1 %}
      {% for d in distribution %}
        <li>
          <span class="pack-name">{{ d.pack_name }}</span>
          <div class="pack-bar-track">
            <div class="pack-bar" style="width: {{ (d.uses * 100 / total)|round(1) }}%"></div>
          </div>
          <span class="pack-uses">{{ d.uses }} ({{ (d.uses * 100 / total)|round(1) }}%)</span>
        </li>
      {% endfor %}
    </ul>
  </section>

  {# Phase 6C 에서 추가 — 자산별 선호도 패널 #}
  {% include "_preference_panel.html" %}
</section>
{% endblock %}
```

- [ ] **Step 4**: `pytest tests/test_web_routers_projects.py -v` → 4 추가 passed (총 8).

- [ ] **Step 5**: 회귀 `pytest -q` → 994 + 4 = **998 passed**.

- [ ] **Step 6**: 커밋 — `feat(m7): /projects/<id> 상세 페이지 + 사용 이력 + 채택 팩 분포`.

---

### 4.14 Phase 6C — `/projects/<id>` 자산별 선호도 패널 (~1일)

#### Task 6.3 — 선호도 패널 fragment + I-5 회귀 + 정렬/검색/페이지네이션

**Files:**
- Create: `src/gah/web/templates/_preference_panel.html`
- Modify: `src/gah/web/routers/projects.py` — `/projects/<id>/preferences.json` API + 정렬/검색 query
- Modify: `tests/test_web_routers_projects.py`

- [ ] **Step 1: 실패 테스트** (~5 추가 케이스):

```python
def test_preference_panel_in_detail(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    aid = asset_factory()
    store.report_feedback(
        project_id=pid, asset_id=aid, query_id=None,
        reason="positive", weight=0.3, created_at=1,
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "preference-panel" in r.text
    assert "0.3" in r.text or "score" in r.text.lower()


def test_preference_sort_query(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?sort=usage_desc")
    assert r.status_code == 200


def test_preference_search_query(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    aid = asset_factory(path="hero.png")
    store.record_asset_use(
        project_id=pid, asset_id=aid, pack_id=1, source="explicit", used_at=1,
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?search=hero")
    assert r.status_code == 200
    body = r.json()
    assert any("hero" in item["asset_path"] for item in body["items"])


def test_preference_pagination(app_for_projects, store):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?offset=0&limit=5")
    assert r.status_code == 200


def test_preference_score_bar_clamping(app_for_projects, store, asset_factory):
    store.upsert_project(external_id="D:/A", display_name="GameA")
    pid = store.list_projects_with_summary()[0].id
    aid = asset_factory()
    # 매우 큰 negative weight → 시각화 막대는 -2 로 클램프
    for _ in range(20):
        store.report_feedback(
            project_id=pid, asset_id=aid, query_id=None,
            reason="negative", weight=-0.5, created_at=1,
        )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json")
    body = r.json()
    item = next(i for i in body["items"] if i["asset_id"] == aid)
    assert item["bar_value"] == -2  # 클램프 결과
```

- [ ] **Step 2: 선호도 패널 fragment** `_preference_panel.html`:

```html
{# M7 — 자산별 선호도 패널 (D14) #}
<section class="preference-panel" x-data="preferencePanel({{ project.id }})">
  <h2>{{ _("자산별 선호도") }}</h2>
  <div class="preference-controls">
    <select x-model="sort" @change="refresh()">
      <option value="score_desc">{{ _("선호도 높은 순") }}</option>
      <option value="score_asc">{{ _("선호도 낮은 순") }}</option>
      <option value="usage_desc">{{ _("채택 많은 순") }}</option>
      <option value="recent_desc">{{ _("최근 활동 순") }}</option>
    </select>
    <input type="text" x-model.debounce.300ms="search" @input="refresh()" placeholder="{{ _('자산 검색') }}">
  </div>
  <table class="preference-table">
    <thead>
      <tr>
        <th>{{ _("자산") }}</th>
        <th>{{ _("팩") }}</th>
        <th>{{ _("선호도") }}</th>
        <th>{{ _("feedback") }}</th>
        <th>{{ _("채택") }}</th>
        <th>{{ _("마지막 활동") }}</th>
      </tr>
    </thead>
    <tbody>
      <template x-for="item in items" :key="item.asset_id">
        <tr>
          <td><a :href="'/asset/' + item.asset_id" x-text="item.asset_path"></a></td>
          <td x-text="item.pack_name"></td>
          <td>
            <div class="score-bar"
                 :class="item.bar_value < 0 ? 'neg' : (item.bar_value > 0 ? 'pos' : 'zero')">
              <div class="score-bar-fill" :style="`width: ${Math.abs(item.bar_value) * 50}%`"></div>
            </div>
            <span class="score-value" x-text="item.composite_score.toFixed(2)"></span>
          </td>
          <td>
            <span class="fb-positive" x-text="item.positive_count"></span> /
            <span class="fb-negative" x-text="item.negative_count"></span> /
            <span class="fb-irrelevant" x-text="item.irrelevant_count"></span>
          </td>
          <td x-text="item.usage_count"></td>
          <td x-text="item.last_activity_at"></td>
        </tr>
      </template>
    </tbody>
  </table>
  <nav class="pager">
    <button @click="prev()" :disabled="offset === 0">{{ _("◀") }}</button>
    <span x-text="`${offset+1}-${offset+items.length} / ${total}`"></span>
    <button @click="next()" :disabled="offset + items.length >= total">{{ _("▶") }}</button>
  </nav>
</section>
<script>
function preferencePanel(pid) {
  return {
    items: [], total: 0, offset: 0, limit: 25,
    sort: "score_desc", search: "",
    async init() { await this.refresh(); },
    async refresh() {
      const url = new URL(`/projects/${pid}/preferences.json`, location.origin);
      url.searchParams.set("sort", this.sort);
      url.searchParams.set("offset", this.offset);
      url.searchParams.set("limit", this.limit);
      if (this.search) url.searchParams.set("search", this.search);
      const r = await fetch(url);
      const body = await r.json();
      this.items = body.items;
      this.total = body.total;
    },
    prev() { this.offset = Math.max(0, this.offset - this.limit); this.refresh(); },
    next() { this.offset += this.limit; this.refresh(); },
  };
}
</script>
```

- [ ] **Step 3: `/projects/<id>/preferences.json` API**:

```python
@router.get("/projects/{pid}/preferences.json")
async def project_preferences_json(
    pid: int,
    sort: str = "score_desc",
    search: str | None = None,
    offset: int = 0,
    limit: int = 25,
    deps=Depends(get_deps),
):
    rows = deps.store.get_project_asset_preferences(
        project_id=pid, sort=sort, search=search,
        offset=offset, limit=limit,
    )
    total = deps.store.count_project_asset_preferences(project_id=pid, search=search)
    items = []
    for r in rows:
        bar_value = max(-2, min(2, r.composite_score))
        items.append({
            "asset_id": r.asset_id,
            "asset_path": r.asset_path,
            "pack_name": r.pack_name,
            "composite_score": r.composite_score,
            "bar_value": bar_value,
            "positive_count": r.positive_count,
            "negative_count": r.negative_count,
            "irrelevant_count": r.irrelevant_count,
            "usage_count": r.usage_count,
            "last_activity_at": r.last_activity_at,
        })
    return {"items": items, "total": total}
```

- [ ] **Step 4: CSS** — `main.css` 에 선호도 막대 스타일 추가:

```css
.score-bar { display: inline-block; width: 100px; height: 12px; background: var(--bar-track); position: relative; }
.score-bar.pos .score-bar-fill { background: var(--score-pos); float: right; }
.score-bar.neg .score-bar-fill { background: var(--score-neg); }
.score-bar.zero .score-bar-fill { background: transparent; }
.score-value { font-variant-numeric: tabular-nums; margin-left: 4px; }
```

`themes.css`:
```css
:root {
  --bar-track: #ddd;
  --score-pos: #28a745;
  --score-neg: #dc3545;
}
[data-theme="dark"] {
  --bar-track: #444;
  --score-pos: #4caf50;
  --score-neg: #f44336;
}
```

- [ ] **Step 5**: `pytest tests/test_web_routers_projects.py -v` → 5 추가 passed (총 13).

- [ ] **Step 6**: 회귀 `pytest -q` → 998 + 5 = **1003 passed**.

- [ ] **Step 7**: 커밋 — `feat(m7): 자산별 선호도 패널 + 정렬/검색/페이지네이션 + 점수 막대`.

---

### 4.15 Phase 7 — 격리 invariant + 문서 마감 + verification (~0.5일)

#### Task 7.1 — 격리 invariant 회귀 테스트 5개

**Files:**
- Create: `tests/test_isolation_invariants.py`

- [ ] **Step 1: 5 회귀 테스트 작성**:

```python
"""M7 — 라이브러리 ↔ Unity 후보 격리 (I-1~I-4) + 프로젝트 간 선호도 격리 (I-5)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from gah.core.unity_import.scanner import UnityAssetStoreScanner
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_with_one_pkg(tmp_path):
    pub = tmp_path / "Pub" / "Cat"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "X.unitypackage")
    return tmp_path


def test_i1_discovered_not_in_assets(cache_with_one_pkg, store):
    """I-1: discovered/previewed 패키지의 자산은 assets 테이블에 없음."""
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_with_one_pkg)
    rows = store.list_unity_imports()
    assert all(r.import_state != "imported" for r in rows)
    # 라이브러리 자산 0
    assert len(store.list_assets()) == 0


def test_i2_preview_no_side_effects(cache_with_one_pkg, store):
    """I-2: preview 는 unity_imports.preview_* 만 갱신, library/ assets 부작용 0."""
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_with_one_pkg)
    uid = store.list_unity_imports()[0].id
    from gah.core.unity_import.unitypackage import parse_pathnames
    row = store.get_unity_import_by_id(uid)
    entries = parse_pathnames(row.package_path)
    store.update_unity_preview(
        uid, asset_count=len(entries), image_count=1, sound_count=1,
    )
    assert len(store.list_assets()) == 0
    assert len(store.list_packs()) == 0


def test_i3_library_routers_dont_query_unity_imports(store):
    """I-3: 라이브러리 라우터가 unity_imports 테이블 미조회 — 코드 인스펙션."""
    import gah.web.routers.library as lib_router
    import inspect
    src = inspect.getsource(lib_router)
    assert "unity_imports" not in src, "library router must not query unity_imports"


def test_i4_unity_routers_dont_query_assets(store):
    """I-4: Unity 라우터가 assets 테이블 미조회."""
    import gah.web.routers.unity_asset_store as unity_router
    import inspect
    src = inspect.getsource(unity_router)
    # assets 테이블 직접 쿼리 X (find_asset / list_assets 같은 함수 호출은 OK 아닌가? — 본 invariant 는 직접 SQL/Store API 호출 금지)
    assert "list_assets" not in src
    assert "find_asset" not in src


def test_i5_project_preferences_isolated(store, asset_factory):
    """I-5: project_A 의 weight 가 project_B 의 점수에 미반영."""
    pa = store.upsert_project(external_id="D:/A", display_name="A")
    pb = store.upsert_project(external_id="D:/B", display_name="B")
    aid = asset_factory()
    # A 에 negative + 사용 5회
    for _ in range(3):
        store.report_feedback(
            project_id=pa, asset_id=aid, query_id=None,
            reason="negative", weight=-0.5, created_at=1,
        )
    for _ in range(5):
        store.record_asset_use(
            project_id=pa, asset_id=aid, pack_id=1,
            source="explicit", used_at=int(time.time()),
        )
    # B 의 선호도 응답
    rows_b = store.get_project_asset_preferences(project_id=pb)
    for r in rows_b:
        if r.asset_id == aid:
            assert r.composite_score == 0
            assert r.usage_count == 0
```

- [ ] **Step 2**: `pytest tests/test_isolation_invariants.py -v` → 5 FAIL 또는 5 passed (이미 격리 보장돼 있으면 통과).

- [ ] **Step 3**: 실패한 invariant 가 있으면 그 원인 (e.g. library router 가 unity_imports 참조) 을 fix.

- [ ] **Step 4**: `pytest tests/test_isolation_invariants.py -v` → 5 passed.

- [ ] **Step 5**: 회귀 `pytest -q` → 1003 + 5 = **1008 passed**.

- [ ] **Step 6**: 커밋 — `test(m7): I-1~I-5 격리 invariant 회귀 테스트`.

#### Task 7.2 — DESIGN.md / CLAUDE.md / HANDOFF.md / MCP_USAGE_GUIDE.md 갱신

**Files:**
- Modify: `DESIGN.md`
- Modify: `CLAUDE.md`
- Modify: `HANDOFF.md`
- Modify: `docs/MCP_USAGE_GUIDE.md`

- [ ] **Step 1**: `DESIGN.md` §4.9 ~ §6.11 ~ §11 Milestone 7 완료 표시:
  - §4.9.1 — "M7 구현 완료" 한 줄 추가
  - §5.4 unity_imports 스키마 — preview 컬럼 4개 추가 명시
  - §6.11 — 단일 도구 → 2 도구 분리, 임포트는 웹 UI 전용 명시
  - §11 Milestone 7 — "✅ 완료" 표시
  - §4.10 (또는 §4.13 정도) — "활성 프로젝트 + 프로젝트 페이지 + 자산별 선호도" 신규 절 추가 (1 페이지 분량)

- [ ] **Step 2**: `CLAUDE.md` §2 진행 현황 표 — M7 행 (대기 → 진행 → 완료) + §8 다음 작업 M8.

- [ ] **Step 3**: `HANDOFF.md` 전체 갱신:
  - §1 한 줄 요약 = M7 완료
  - §2 검증된 사실 = 1008 passed (또는 verification 으로 정확 수)
  - §5 다음 세션 = M8 spec 부터

- [ ] **Step 4**: `docs/MCP_USAGE_GUIDE.md` — 19, 20번째 도구 (`scan_unity_asset_store_cache`, `list_unity_packages`) 설명 + Claude Code 워크플로 예시 (e.g. "사용자: '내 Unity 에셋 다 끌어와줘' → Claude Code 의 응답") 추가.

- [ ] **Step 5**: 회귀 `pytest -q` → 1008 passed (회귀 0, doc 만 변경).

- [ ] **Step 6**: 커밋 — `docs(m7): DESIGN/CLAUDE/HANDOFF/MCP_USAGE_GUIDE M7 완료 표시 + 갱신`.

#### Task 7.3 — M7_verification.md 작성

**Files:**
- Create: `milestones/M7_verification.md`

- [ ] **Step 1**: `pytest -q` 실행 결과 (passed/skipped/deselected) 캡처.

- [ ] **Step 2**: 시나리오 자동 검증 결과 (Phase 0~7 표 형태) + 사용자 수동 검증 항목 + 알려진 한계 작성. M5/M6 verification 파일 패턴 그대로.

- [ ] **Step 3**: 커밋 — `docs(m7): M7_verification.md — 최종 검증 결과`.

---

## 5. 작업 phase 합계

| Phase | 기간 | 누적 baseline | 핵심 산출물 |
|---|---:|---:|---|
| 0 — 스캐폴딩 + fixtures | 0.5일 | 894 | unity_import 패키지 + 7 dataclass + .unitypackage fixture |
| 1A — cache_paths (Task 1.1, 2.1 선행) | 0.5일 | 900 | 4단계 우선순위 검출 |
| 1B — unitypackage | 1일 | 912 | gzip+tarfile 파서 + 물리 복사 |
| 1C — scanner | 1일 | 922 | 캐시 walk + state 머신 |
| 1D — importer + remote_optin skeleton | 1일 | 933 | tarfile.extract + pack.json + skeleton |
| 2A — Store unity_imports + Config | 0.5일 | 949 | 마이그레이션 + CRUD + record_asset_use enum |
| 2B — Store projects 쿼리 + 트레이 + 부팅 자동 스캔 | 0.5일 | 959 | upsert_project + 사용 이력/분포/선호도 + I-5 격리 |
| 3A — MCP 모델 + 도구 | 0.5일 | 969 | 4 Pydantic + 2 도구 + import_url 빌더 |
| 3B — MCP server 20 도구 + integration | 0.5일 | 969 | INSTRUCTIONS + mcp_integration 갱신 |
| 4A — /unity-asset-store 라우터 + 6 endpoint | 1일 | 977 | scan/preview/import/skip/restore API |
| 4B — Unity 페이지 HTML + 사이드바 | 0.5일 | 977 | unity_asset_store.html + 상태 칩 + 사이드바 메뉴 2개 |
| 5 — 활성 프로젝트 + 채택 통합 | 1일 | 990 | 4 API + SSE broadcast + 글로벌 헤더 + 채택 버튼 |
| 6A — /projects 라우터 + 페이지 | 0.5일 | 994 | projects_list.html + 활성 강조 |
| 6B — /projects/<id> 사용 이력 + 분포 | 0.5일 | 998 | project_detail.html + 도넛/막대 분포 |
| 6C — /projects/<id> 자산별 선호도 패널 | 1일 | 1003 | _preference_panel.html + 정렬/검색/페이지네이션 + 점수 막대 |
| 7 — invariant + 문서 + verification | 0.5일 | 1008 | I-1~I-5 회귀 + DESIGN/CLAUDE/HANDOFF/MCP_USAGE_GUIDE + M7_verification |
| **합계** | **~10일** | **1008** | **MCP 18→20 + 의존성 0** |

> 위 누적 baseline 은 추정. 정확 수는 verification 에서 확인. 본 plan 의 +~125 신규 테스트 목표보다 최종이 약간 적을 수 있다 (~120 정도).

## 6. 핵심 결정 요약 체크리스트

- [x] **D1**: 베이스라인 DESIGN §4.9.1 + §5.4 + §6.11. (4.5/4.9/4.15)
- [x] **D2**: scan / preview / import 3단계 state 머신. (4.3/4.5/4.9)
- [x] **D3**: 캐시 경로 4단계 우선순위. (4.1)
- [x] **D4**: tarfile + gzip + 6 확장자 필터. (4.2)
- [x] **D5**: 물리 복사 + library/<pack_name>/ 일반 인테이크. (4.4)
- [x] **D6**: 부팅 1회 자동 스캔, 임포트 100% 사용자. (4.6/4.9)
- [x] **D7**: 라이브러리 ↔ Unity 후보 격리 I-1~I-4. (4.15 Task 7.1)
- [x] **D8**: 프로젝트 간 선호도 격리 I-5. (4.6/4.15)
- [x] **D9**: MCP 2 도구 18→20. (4.7/4.8)
- [x] **D10**: publisher 패널 skeleton. (4.4 Task 1.5)
- [x] **D11**: 웹 페이지 신규 2. (4.9~4.10/4.12~4.14)
- [x] **D12**: 활성 프로젝트 + 글로벌 헤더 + SSE. (4.11)
- [x] **D13**: 채택 버튼 활성 프로젝트 연동. (4.11 Task 5.3)
- [x] **D14**: 선호도 점수 = sum(weight) + 0.1*usage. (4.14)
- [x] **D15**: idempotent 마이그레이션 unity_imports + Config. (4.5)
- [x] **D16**: 트레이 메뉴 = 스캔만. (4.6 Task 2.5)
- [x] **D17**: skipped 영구, mtime 변경 시 되돌림. (4.3 Task 1.3)

## 7. v1 의도적 미룬 항목 (spec §8 그대로)

- publisher 패널 실제 HTTP 구현 (v2)
- 자동 동기화 스케줄러 (M8)
- 캐시에서 사라진 .unitypackage 자동 제거 실제 로직 (v2)
- 다중 캐시 경로 (v2)
- UPM `.tgz` 임포트 (v2)
- 사용자 별칭 매핑 GUI (v2)
- `get_active_project` / `set_active_project` / `get_project_preferences` MCP 도구 (v2)
- PSD/TGA 확장자 임포트 (v2)
- 라이브러리 카드 직접 피드백 입력 UI (v2)
- search_queries 로그 시각화 (v2)
- 프로젝트별 자산 JSON export (v2)
- 임포트 완료 후 unity_imports 자동 되돌림 (v2)
- 디스크 사용량 표시 (v2 / M8)
- GUI 에서 frame size 입력 (v2)

## 8. 외부 출처

- [Unity Manual — Asset Store cache location](https://docs.unity3d.com/Manual/upm-config-cache-as.html)
- [Python `tarfile`](https://docs.python.org/3/library/tarfile.html)
- [DESIGN.md §4.9 / §5.4 / §6.11 / §11](../DESIGN.md)
- [M7 spec](../docs/superpowers/specs/2026-05-18-m7-unity-asset-store-import-design.md)

