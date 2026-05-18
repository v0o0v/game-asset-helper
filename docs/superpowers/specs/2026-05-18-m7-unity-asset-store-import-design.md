# M7 — Unity Asset Store 임포트 + 프로젝트 워크플로 (설계 spec)

> 본 문서는 [M5 spec](./2026-05-17-m5-web-gui-and-library-redesign.md) / [M6 spec](./2026-05-18-m6-sheet-and-animation-design.md) 과 같은 형식이며, [`CLAUDE.md`](../../../CLAUDE.md) §2 / [`DESIGN.md`](../../../DESIGN.md) §4.9 + §5.4 + §6.11 + §11 Milestone 7 의 한 줄 항목을 작업 단위까지 풀어 적은 1차 결정 문서다. 본 spec 의 결정을 [`milestones/M7_plan.md`](../../../milestones/M7_plan.md) 가 phase / task 로 옮기고, 실제 구현은 plan 의 체크박스를 따라간다.
>
> **작성일**: 2026-05-18
> **타깃 마일스톤**: M7 (M6 완료 후)
> **예상 소요**: ~1.5주 (~8일)
> **누적 자동 테스트 baseline**: M6 종료 시 887 passed + 1 skipped + 40 deselected. M7 종료 시 **~1012 passed** 목표.

---

## 1. 한 줄 요약

Unity Asset Store 로컬 캐시(`%APPDATA%\Unity\Asset Store-5.x\`)의 `.unitypackage` 들을 **스캔→발견→사용자 선택→임포트** 2단계로 분리해 처리하고, 임포트된 자산은 일반 팩과 동일한 인테이크 흐름으로 라이브러리에 편입한다. 동시에 **활성 프로젝트** 컨텍스트(글로벌 헤더 드롭다운)를 도입해 웹 UI의 채택/검색/피드백 흐름이 프로젝트별로 분리되어 동작하고, `/projects` + `/projects/<id>` 신규 페이지에서 프로젝트별 자산 사용 이력 + 채택 팩 분포 + 자산별 선호도를 시각화한다. MCP는 `scan_unity_asset_store_cache` + `list_unity_packages` 2개 도구 추가 (18 → **20**). 임포트 / 활성 프로젝트 변경 / 신규 프로젝트 생성은 **웹 UI 전용**. **신규 의존성 0**.

## 2. 배경 / 발견 사항 (코드베이스 실측)

- **`unity_imports` 테이블 스키마 이미 명세**: `DESIGN.md:552` — `id / package_path UNIQUE / publisher / category / asset_name / package_size / package_mtime / pack_id FK / import_state / import_error / imported_at + idx_unity_imports_pack`. 본 M7 가 마이그레이션을 수행한다.
- **`projects` 테이블 + `asset_usage` 테이블 모두 `project_id` 컬럼 NOT NULL** (`DESIGN.md:519, 530`). M3 부터 프로젝트별 분리되어 있다.
- **`feedback_records` 테이블도 `project_id` NOT NULL + 인덱스 2개** (`DESIGN.md:580`). M4 부터 자산별 선호도가 프로젝트별로 분리 저장되어 있다.
- **`record_asset_use` MCP 도구 + `UsageTracker` + `_modal_usage.html` 모달은 M3/M5 부터 존재** (`src/gah/core/usage_tracker.py`, `src/gah/web/templates/_modal_usage.html`). 단 **현재 활성 프로젝트를 선택/저장하는 UI 자체는 없음** — M5 의 채택 흐름(`_pick_card.html`, `routers/picks.py`)은 Claude Code가 명시한 `project_id`만 사용. 라이브러리 페이지에서 사용자가 직접 채택할 때 활성 프로젝트 컨텍스트가 빠져 있어 `record_asset_use` 가 충분히 동작 못 함.
- **MCP 도구 18개** (`src/gah/mcp/server.py` — `register_all_tools` 가 18 도구 등록, M6 `suggest_animation_frames` 포함).
- **사이드바 메뉴**는 M5 의 4 페이지(library / packs / labels / search) + settings. `src/gah/web/templates/base.html` 또는 `_side_panel_*.html` 에 정의됨.
- **Config 파일** = `%APPDATA%\GameAssetHelper\config.toml` (`src/gah/config.py:Config` dataclass + `load_config()` / `save_config()`).
- **라이브러리 디렉터리** = `%APPDATA%\GameAssetHelper\library\` (각 팩이 하위 디렉터리). 워처(`src/gah/core/watcher.py`)가 변경 감지 → `PackManager.intake()` → `assets` 테이블 row 자동 생성.
- **DESIGN §4.9.1** = 캐시 경로 검출 우선순위 + `.unitypackage` 파서 로직 + 팩 매니페스트 자동 생성 모두 명세 완료. **신규 의존성 0** (표준 `tarfile` + `gzip`).
- **DESIGN §6.11 `sync_unity_asset_store`** = 한 도구로 발견→임포트를 묶었으나, 본 M7 는 **사용자 의도 반영해 2 도구로 분리** (`scan_unity_asset_store_cache` + `list_unity_packages`). 실제 임포트는 웹 UI 전용.

## 3. 시나리오 (M7 종료 시 동작)

### 3.1 첫 부팅 + 자동 스캔

사용자가 `python -m gah --tray` → 트레이 아이콘 + 브라우저 자동 열림.

1. 부팅 직후, `app.py` 가 `UnityAssetStoreScanner` 를 별도 스레드에서 1회 실행. 캐시 경로 검출 (env → Unity Pref → 기본) → 디렉터리 walk → `.unitypackage` 발견 → `unity_imports` 테이블에 `import_state='discovered'` row 들 INSERT.
2. 사용자가 사이드바 "Unity Asset Store" 클릭 → `/unity-asset-store` 페이지 진입 → 발견 목록 표(`publisher / category / asset_name / size / mtime / state`) 표시.
3. 사용자가 처음 보는 화면이라 활성 프로젝트는 아직 None — 글로벌 헤더 우상단 "프로젝트 선택" 칩 표시.

### 3.2 활성 프로젝트 선택 + 채택 흐름

1. 사용자가 글로벌 헤더 드롭다운 클릭 → 기존 프로젝트 0개라 "➕ 새 프로젝트" 모달 → `external_id="D:/Unity/MyGame"` + `display_name="MyGame"` 입력 → POST `/api/projects` → Store `upsert_project` → 응답 `{id: 1, ...}` → 그 즉시 활성 프로젝트로 설정 (`PUT /api/active-project {project_id: 1}`) → 헤더가 `MyGame ▾` 로 갱신.
2. 사용자가 "라이브러리" 페이지 진입 → 자산 카드 4개. 카드 각각에 "채택" 버튼이 enabled. 사용자가 한 카드 채택 → `POST /api/assets/12/adopt {context: "platformer level1"}` → 서버가 활성 프로젝트 `id=1` 로 `record_asset_use(asset_id=12, project_id=1, source="user_web", context="platformer level1")` → asset_usage row 생성. 카드 채택 표시(✓) 갱신.
3. 검색 박스에 "공중 적" 입력 → `find_asset` 호출에 `project_id=1` 자동 포함 → 통일성 가중치 작동 → 같은 프로젝트에서 이전 채택한 팩이 우선.

### 3.3 Unity 패키지 임포트

1. 사용자가 `/unity-asset-store` 진입 → 발견 132건. 한 row("Mega Platformer Pack") 클릭 → "미리보기" 버튼 → POST `/api/unity-packages/<id>/preview` → `.unitypackage` 의 pathname 텍스트 읽기 → 자산 카운트(image 312, sound 14) 채움 → `import_state='previewed'` + `preview_*_count` 컬럼 채움 → row 가 갱신되어 자산 카운트 표시. 라이브러리는 아무 영향 없음(I-2).
2. 사용자가 "임포트" 버튼 → POST `/api/unity-packages/<id>/import` → `import_state='import_pending'` → 백그라운드 `UnityImporter` 가 `tarfile.extract` 로 `library/mega_platformer_pack/` 에 풀음(물리 복사, D5). 진행은 SSE 로 페이지에 실시간 표시.
3. 워처가 `library/mega_platformer_pack/` 등장 감지 → 일반 `PackManager.intake` → `packs` row 생성 + 자산들 `assets` row 생성 → 분석 큐로 들어감(M2/M5 흐름 그대로).
4. 임포트 완료 후 `unity_imports.import_state='imported'` + `pack_id=새 팩 id` + `imported_at` 채움. 페이지 상태 칩 갱신.
5. 사용자가 "라이브러리" 탭 진입 → 새 팩 카드가 일반 팩과 동일하게 노출. 카드 메타에 vendor=`Pixel Studios` + 작은 "Unity" 칩 표시.
6. Unity 캐시 디렉터리는 GAH 가 건드리지 않음 — Unity Hub 가 그대로 사용 가능(D5).

### 3.4 사용자가 "건너뜀" 선택

1. 사용자가 다른 row("Old Asset Pack") → "건너뜀" 버튼 → POST `/api/unity-packages/<id>/skip` → `import_state='skipped'`.
2. 다음 부팅 스캔 → 캐시 디렉터리에 여전히 존재하지만 `unity_imports` 기존 row 의 mtime 변동 없으므로 `state` 유지(I-5 의 "skipped 영구").
3. 사용자가 마음 바꿔 "다시 후보로" 버튼 → POST `/api/unity-packages/<id>/restore` → `import_state='discovered'` 로 되돌림 → 임포트 가능.

### 3.5 캐시 업데이트 감지

1. 사용자가 Unity Hub 로 "Mega Platformer Pack v2" 다운받음 → 같은 `.unitypackage` 파일이 mtime 변경.
2. 다음 스캔(부팅 또는 수동) → `unity_imports` 의 mtime 비교 → 변경 감지 → `import_state` 가 `imported` 였다면 `discovered` 로 되돌리고 `preview_*_count` NULL 화. **자동 재임포트 안 함** — 사용자에게 다시 묻기(D17).
3. 페이지에 "이 패키지가 업데이트됨, 다시 임포트하겠습니까?" 시각적 표시.

### 3.6 프로젝트별 선호도 시각화

1. 사용자가 사이드바 "프로젝트" → `/projects` 목록 → MyGame 행 클릭 → `/projects/1` 상세 페이지.
2. 페이지 본문:
   - **헤더**: 프로젝트 메타 + 핀/블록 관리 버튼.
   - **자산 사용 이력 표**: `썸네일 / 자산 이름 / 팩 / 사용 횟수 / 마지막 사용 / source / context`.
   - **채택 팩 분포**: 도넛 또는 가로 막대(CSS 만 사용, 차트 라이브러리 0). 상위 5팩 + "기타".
   - **자산별 선호도 패널**: `썸네일 / 자산 이름 / 팩 / 종합 선호도 점수 막대(빨강~초록, -2~+2 클램프) / signed weight 합 / positive·negative·irrelevant 카운트 / 채택 횟수 / 마지막 활동 시점`. 정렬(선호도 높은 순 기본) + 검색 + 페이지네이션.
3. 다른 프로젝트 OtherGame 으로 활성 변경 → `/projects/2` 진입 → MyGame 의 feedback/usage 가 OtherGame 의 점수에 영향 안 미침(I-5 invariant).

## 4. 결정사항

### 4.1 베이스라인 = DESIGN §4.9.1 + §5.4 + §6.11 그대로 (D1)

**결정** — Unity Asset Store 캐시 스캔 + `.unitypackage` 파서 + `unity_imports` 테이블 + MCP 도구 노출까지 DESIGN.md 의 명세대로 구현. 단 §6.11 의 단일 `sync_unity_asset_store` 도구는 사용자 의도 반영해 **2 도구로 분리**(D9).

비공식 publisher 패널 API(DESIGN §4.9.2)는 **v1 skeleton 만, 기본 비활성, MCP/UI 호출 시 `403_remote_disabled` 응답**(D10).

### 4.2 스캔 / 미리보기 / 임포트 3단계 분리 (D2)

**결정** — `unity_imports.import_state` 가 다음 상태 머신을 가짐:

| state | 의미 | 진입 트리거 |
|---|---|---|
| `discovered` | 스캔만 됨, 메타(publisher/category/asset_name/size/mtime)만 채워짐. 실제 .unitypackage 열림 X | 스캔 (자동 / 수동) |
| `previewed` | 사용자가 미리보기 클릭, `.unitypackage` 안 pathname 읽혀서 `preview_asset_count / preview_image_count / preview_sound_count` 채워짐. asset 바이트는 추출 X | 사용자 클릭 (웹 UI) |
| `import_pending` | 사용자가 임포트 결정, 백그라운드 큐 대기 | 사용자 클릭 (웹 UI) |
| `imported` | `tarfile.extract` 완료, `pack_id` 채워짐, library/ 에 풀려 일반 인테이크 흐름 진입 | 백그라운드 importer |
| `skipped` | 사용자가 명시적으로 건너뜀 — 다음 스캔에서도 유지 | 사용자 클릭 (웹 UI) |
| `failed` | 추출 실패, `import_error` 채워짐 | 백그라운드 importer |

mtime 변경 감지 시 `imported` → `discovered` 로 되돌리고 preview 컬럼 NULL 화. 자동 재임포트 X(D17).

### 4.3 캐시 경로 검출 우선순위 (D3)

**결정** — 다음 순서로 첫 번째 유효한 경로 사용:

1. `Config.unity_asset_store_cache_path` (사용자가 GAH 설정 페이지에서 입력)
2. `os.environ.get("ASSETSTORE_CACHE_PATH")` (환경변수)
3. Unity Editor Preferences (`%APPDATA%\Unity\Editor-5.x\Preferences` 의 `assetStoreCacheLocation` 키, 있으면)
4. `%APPDATA%\Unity\Asset Store-5.x\` (기본)

모두 비어 있으면 `/unity-asset-store` 페이지에 "캐시 경로를 설정해 주세요" 빈 상태 + 설정 페이지 링크.

### 4.4 `.unitypackage` 파서 (D4)

**결정** — 표준 `tarfile` + `gzip` 만 사용. `.unitypackage` = `tarfile.open(mode="r:gz")`.

```python
def parse_pathnames(package_path: Path) -> dict[str, UnityPackageEntry]:
    """guid → (pathname, internal_asset_path) 매핑.

    `.unitypackage` 안 `<guid>/pathname` 텍스트만 읽음. asset 바이트는 안 건드림.
    이미지/사운드 6개 확장자만 필터링.
    """

def extract_targets(package_path: Path, dest_dir: Path) -> ExtractResult:
    """선택된 GUID 들의 asset 만 dest_dir 안 pathname 원본 경로로 풀음.

    tarfile.extract 로 물리 복사 (D5). 심볼릭 링크 / 하드 링크 X.
    """
```

대상 확장자(6개, GAH 분석기가 처리 가능한 것만):
- 이미지: `.png`, `.jpg`, `.webp`
- 사운드: `.wav`, `.ogg`, `.mp3`

PSD/TGA 등은 임포트 안 함(노이즈 방지).

### 4.5 임포트 = 물리 복사, `library/<pack_name>/` 일반 인테이크 흐름 (D5)

**결정** —

1. `pack_name = normalize(asset_name)` — 공백·특수문자 → `_`, 소문자.
2. `library/<pack_name>/<원본 Unity 내부 경로>` 에 `tarfile.extract` 로 물리 복사.
3. 추출 직후 `pack.json` 자동 생성:
   ```json
   {
     "name": "<원래 AssetName>",
     "vendor": "<Publisher>",
     "license": "Unity Asset Store EULA",
     "source": "unity_asset_store_cache",
     "source_path": "<.unitypackage 절대 경로>",
     "imported_at": <unix_ts>,
     "package_mtime": <unix_ts>
   }
   ```
4. 워처가 새 디렉터리 감지 → 일반 `PackManager.intake` → `packs` row + `assets` row → 분석 큐(M2~M6 흐름).
5. `unity_imports.pack_id` 채움 + `import_state='imported'` + `imported_at`.
6. Unity 캐시 디렉터리는 read-only — GAH 가 절대 건드리지 않음.

심볼릭 링크 / 하드 링크 사용 안 함(Windows 권한 + Unity 캐시 변동 시 깨질 리스크).

### 4.6 부팅 자동 스캔, 임포트 100% 사용자 클릭 (D6)

**결정** —

- **자동**: 부팅 직후 1회 자동 스캔(사용자 동의 없이도 read-only). 단 (a) 캐시 디렉터리 존재 (b) 한 번도 스캔 안 됐거나 (c) 마지막 스캔 이후 캐시 디렉터리 mtime 변동 인 경우만.
- **수동 트리거 3종**: 웹 UI "캐시 스캔" 버튼 / 트레이 메뉴 "Unity 캐시 스캔" / MCP `scan_unity_asset_store_cache`.
- **임포트 트리거 1종**: 웹 UI 의 "임포트" 버튼만. MCP 임포트 도구 없음. 자동 임포트 안 함.
- **미리보기 트리거 2종**: 웹 UI row 클릭(lazy) / MCP `list_unity_packages(include_preview=true)`.

자동 동기화(매일 1회 등)는 v2 / M8.

### 4.7 라이브러리 ↔ Unity 후보 격리 invariant (D7)

**결정** — 다음 invariant 회귀 테스트로 보장:

- **I-1**: `unity_imports.import_state != 'imported'` 인 패키지의 자산은 `assets` 테이블에 **존재하지 않는다** (애초에 `library/` 에 추출 안 됐으니 자동 보장).
- **I-2**: `preview` 호출은 `unity_imports.preview_*` 컬럼만 갱신하고 `library/` / `packs` / `assets` 어디에도 부작용 없음 (pathname 텍스트만 읽음).
- **I-3**: 라이브러리 라우터(`/library`, `/packs`, `/labels`, `/search`)와 MCP `find_asset` / `list_packs` / `suggest_packs` 등은 `unity_imports` 테이블을 **조회하지 않는다**.
- **I-4**: Unity Asset Store 라우터는 `assets` / `sprite_meta` / `sound_meta` 를 조회하지 않는다 (역방향 격리, 발견 목록 화면은 후보 메타만).

### 4.8 프로젝트 간 선호도 격리 invariant (D8)

**결정** —

- **I-5**: 한 프로젝트의 `feedback_records` / `asset_usage` 는 **다른 프로젝트의 검색 가중치에 영향 주지 않는다**.

회귀 테스트:
1. project_A 에서 asset_X 에 negative feedback 3회 + 5회 채택
2. project_B 에서 동일 asset_X 검색
3. project_B 의 검색 결과 점수에 project_A 의 weight / usage 가 **반영되지 않음** (M3/M4 의 가중치 함수가 이미 `WHERE project_id=?` 필터를 거는지 코드 인스펙션 + 시나리오 테스트)

기존 가중치 계산 코드(`src/gah/core/consistency.py`, `src/gah/core/search.py`, `src/gah/core/usage_tracker.py`)가 이미 `project_id` 필터를 사용 중이라면 변경 없이 회귀 테스트만 추가. 누락 시 fix + 테스트.

### 4.9 MCP 도구 2개 추가 (D9)

**결정** — 18 → **20 도구**:

#### `scan_unity_asset_store_cache`

```jsonc
// input
{
  "force": false,                    // true면 mtime 변화 없어도 전부 재기록
  "filter": {                         // optional
    "publisher_glob": "Kenney*",
    "asset_name_glob": "*platformer*"
  }
}

// output
{
  "scanned": 132,
  "new": 4,                  // 신규 discovered
  "updated": 1,              // mtime 변경 감지 (imported → discovered 되돌림 포함)
  "unchanged": 127,
  "removed": 0,              // 캐시에서 사라짐 (state 변경 X, 통보용)
  "cache_path": "C:/Users/.../Unity/Asset Store-5.x",
  "warnings": []
}
```

에러:
- `503_cache_not_found` — 캐시 경로 모두 비어있음.
- `403_path_not_readable` — 경로는 있지만 접근 권한 없음.

#### `list_unity_packages`

```jsonc
// input
{
  "state": null,                      // optional. "discovered"|"previewed"|"import_pending"|"imported"|"skipped"|"failed" 중 하나
  "filter": {                         // optional
    "publisher_glob": "Kenney*",
    "asset_name_glob": "*platformer*"
  },
  "include_preview": false,           // true면 미리보기 안 된 row 들도 .unitypackage 안 pathname 읽어 카운트 채움 (DB 갱신)
  "offset": 0,
  "limit": 50
}

// output
{
  "total": 132,
  "items": [
    {
      "id": 41,
      "package_path": "C:/Users/.../Mega Platformer Pack.unitypackage",
      "publisher": "Pixel Studios",
      "category": "Sprites",
      "asset_name": "Mega Platformer Pack",
      "package_size": 24500000,
      "package_mtime": 1740000000,
      "import_state": "discovered",
      "preview_asset_count": null,
      "preview_image_count": null,
      "preview_sound_count": null,
      "pack_id": null,
      "imported_at": null,
      "import_url": "http://127.0.0.1:9874/unity-asset-store?focus=41"
    }
  ]
}
```

`import_url` 은 Claude Code 가 사용자에게 "이 패키지 보유, 임포트하려면 <URL>" 안내할 수 있도록 응답에 포함.

에러:
- `400_invalid_state` — `state` 가 enum 밖.

### 4.10 publisher 패널 skeleton (D10)

**결정** — `src/gah/core/unity_import/remote_optin.py` 파일 생성, 단:

- `UnityRemoteOptInClient.is_enabled() -> bool` = `Config.unity_remote_optin_enabled` (기본 `False`) 만 읽음
- `UnityRemoteOptInClient.fetch_owned_assets() -> list` = `raise NotImplementedError("publisher panel API is v2")`
- 설정 페이지에 "Unity Asset Store 비공식 다운로드" 토글 placeholder + 경고 안내 텍스트(약관 회색지대) 추가, 토글 활성해도 실제 동작 안 함(NotImplementedError catch → UI 에 "v2 에서 지원 예정" 메시지)
- 향후 v2 에서 이 파일을 채우면 자동으로 활성

### 4.11 웹 페이지 신규 2개 (D11)

**결정** — 사이드바 메뉴 추가:

```
[ 라이브러리 / 팩 / 라벨 / 검색 ]
─────────────
[ 프로젝트 ]                         ← 신규
[ Unity Asset Store ]                ← 신규
─────────────
[ 설정 ]
```

#### `/unity-asset-store`

- **상단**: 캐시 경로 표시 + "캐시 스캔" 버튼 (SSE 진행 — `event: scan_progress`)
- **필터**: 상태 칩(discovered / previewed / import_pending / imported / skipped / failed) + publisher 검색 + asset_name 검색
- **본문**: 발견 패키지 표 (publisher / category / asset_name / size / mtime / state 칩 / preview 자산 카운트 (있으면))
- **각 row 액션**:
  - "미리보기" (discovered → previewed)
  - "임포트" (discovered/previewed/skipped → import_pending → imported, SSE 진행 — `event: import_progress`)
  - "건너뜀" (discovered/previewed → skipped)
  - "다시 후보로" (skipped → discovered)
- **하단**: 임포트 대기 큐 + 진행 표시
- 페이지에 URL query `?focus=<id>` 받으면 그 row 하이라이트 + 스크롤(Claude Code 의 `import_url` 안내용)

#### `/projects` + `/projects/<id>`

**`/projects` 목록**:
- 표: display_name / external_id / first_seen / last_seen / 채택 자산 카운트 / 가장 많이 쓴 팩 / pinned_pack_id 칩 / blocked_packs 카운트 / "상세" 버튼
- 활성 프로젝트는 시각적으로 구분(테두리 강조).
- 상단에 "+ 새 프로젝트" 버튼(글로벌 헤더 드롭다운 모달과 같은 모달 재사용).

**`/projects/<id>` 상세**:
- **헤더**: 프로젝트 메타 + 핀/블록 관리 버튼 + "활성 프로젝트로 설정" 버튼(이미 활성이면 disabled)
- **자산 사용 이력 표**: 썸네일 / 자산 이름 / 팩 / 사용 횟수 / 마지막 사용 / `source` (explicit / implicit_top1 / manual / claude_pick / user_web) / `context`
- **채택 팩 분포**: 도넛 또는 가로 막대(CSS only). 상위 5팩 + "기타".
- **자산별 선호도 패널**: 썸네일 / 자산 이름 / 팩 / **종합 선호도 점수 막대**(빨강~초록, -2~+2 클램프) / signed weight 합 / positive·negative·irrelevant 카운트 / 채택 횟수 / 마지막 활동 시점. 정렬 4종(선호도 높은 순 기본 / 낮은 순 / 채택 많은 순 / 최근 활동 순) + 검색 + 페이지네이션.

### 4.12 활성 프로젝트 컨텍스트 (D12)

**결정** —

- **상태 위치**: `Config.active_project_id: Optional[int]`. `%APPDATA%\GameAssetHelper\config.toml` 에 저장. 단일 데스크톱 앱 가정 — 모든 브라우저 탭 / 모든 페이지 / 트레이가 공유.
- **글로벌 헤더**: 우상단 드롭다운 `[ 현재 프로젝트: <display_name> ▾ ]`. 모든 페이지(라이브러리 / 팩 / 라벨 / 검색 / 프로젝트 / Unity Asset Store / 설정) 공통.
- **드롭다운 내용**: 기존 프로젝트 목록 + "➕ 새 프로젝트" 모달(display_name + external_id 입력) + "선택 해제".
- **활성 프로젝트 변경 즉시 모든 탭 갱신**: SSE `event: active_project_changed` broadcast(M5 SSE 인프라 재사용).

### 4.13 채택 버튼 + 활성 프로젝트 연동 (D13)

**결정** —

- 라이브러리 카드의 "채택" 버튼:
  - 활성 프로젝트 **있음**: enabled. 클릭 → POST `/api/assets/<asset_id>/adopt` (body `{query_id?, context?}`) → 서버가 `record_asset_use(asset_id, project_id=active, source="user_web", ...)`.
  - 활성 프로젝트 **없음**: disabled + tooltip "프로젝트를 먼저 선택하세요".
- 검색 박스 / 자동 검색 호출: 활성 프로젝트 있을 시 `project_id` 자동 포함 → 통일성 가중치 작동.
- 피드백 입력(라이브러리 카드 또는 모달의 좋아요/싫어요 등): 활성 프로젝트로 `report_feedback`.
- 통일성 모달(`_modal_usage.html`): 활성 프로젝트 기준으로 데이터 fetch.
- Claude pending-pick (`_pick_card.html`): 사용자 채택 시 활성 프로젝트로 자동(M5 의 `source="claude_pick"` + `record_asset_use` 흐름 보강).

활성 프로젝트는 **웹 UI 전용 컨텍스트** — MCP 클라이언트(Claude Code)는 그대로 매번 명시적 `project_id` 보냄(D12 격리 명확). 두 채널 모두 같은 `asset_usage` row 에 누적되어 일관성 유지.

### 4.14 자산별 선호도 점수 공식 (D14)

**결정** — `/projects/<id>` 페이지의 종합 선호도 점수:

```
composite_score(asset_id, project_id) = sum(feedback.weight) + Config.preference_usage_weight * usage_count
```

- `feedback.weight` = `feedback_records.weight` (M4 의 signed weight, `Config.feedback_*_weight` 적용 결과)
- `usage_count` = `COUNT(*) FROM asset_usage WHERE asset_id=? AND project_id=?`
- `Config.preference_usage_weight: float = 0.1` 신규 추가
- 시각화 막대: -2 ~ +2 범위 클램프, 음수 빨강 / 양수 초록 / 0 회색

검색 가중치와는 별개 — 검색에는 기존 M4 의 ConsistencyScorer + feedback weight 가 그대로. 본 공식은 **시각화 전용 종합 점수**.

### 4.15 DB 마이그레이션 = 컬럼 추가 + 신규 테이블 (D15)

**결정** —

신규 테이블 `unity_imports` (DESIGN §5.4 기준, preview 컬럼 추가):

```sql
CREATE TABLE IF NOT EXISTS unity_imports (
  id                       INTEGER PRIMARY KEY,
  package_path             TEXT NOT NULL UNIQUE,
  publisher                TEXT,
  category                 TEXT,
  asset_name               TEXT NOT NULL,
  package_size             INTEGER NOT NULL,
  package_mtime            INTEGER NOT NULL,
  -- 미리보기 (lazy)
  preview_asset_count      INTEGER,
  preview_image_count      INTEGER,
  preview_sound_count      INTEGER,
  preview_inspected_at     INTEGER,
  -- 임포트 결과
  pack_id                  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  import_state             TEXT NOT NULL,   -- 'discovered'|'previewed'|'import_pending'|'imported'|'failed'|'skipped'
  import_error             TEXT,
  imported_at              INTEGER,
  -- 메타
  first_seen_at            INTEGER NOT NULL,
  last_scanned_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unity_imports_pack ON unity_imports(pack_id);
CREATE INDEX IF NOT EXISTS idx_unity_imports_state ON unity_imports(import_state);
```

`Config` 신규 필드:
```python
unity_asset_store_cache_path: Optional[str] = None    # D3 우선순위 1
unity_remote_optin_enabled: bool = False              # D10
unity_remote_optin_session: Optional[str] = None      # D10 (v2 에서 사용)
active_project_id: Optional[int] = None               # D12
preference_usage_weight: float = 0.1                  # D14
```

마이그레이션 idempotent — `CREATE TABLE IF NOT EXISTS` + `Store.initialize()` 에서 `PRAGMA table_info(unity_imports)` 로 컬럼 존재 검사 후 누락 컬럼만 `ADD COLUMN`. `save_config` / `load_config` 는 dataclass 기본값으로 backward compat.

### 4.16 트레이 메뉴 동작 = 스캔 트리거만 + 알림 (D16)

**결정** —

- 트레이 메뉴에 "Unity 캐시 스캔" 액션 추가. 클릭 → `UnityAssetStoreScanner.run_once()`.
- 스캔 완료 후 신규 발견 N건 ≥ 1 이면 Windows 토스트 알림 "Unity 캐시에 새 패키지 N개 — 웹 UI 에서 확인하세요" + 클릭 → `http://127.0.0.1:9874/unity-asset-store` 열기.
- 트레이에 "현재 프로젝트: <name>" 표시 + 클릭 시 서브메뉴(기존 프로젝트 목록, 빠른 전환). 풀 UI(신규 생성 / 핀 / 블록)는 웹.

### 4.17 skipped 영구, mtime 변경 시 되돌림 (D17)

**결정** —

- 사용자가 "건너뜀" 누른 row 는 다음 스캔에서도 `state='skipped'` 유지. 단 `package_mtime` 이 바뀌면 → `discovered` 로 되돌림 + `preview_*_count` NULL 화.
- 이미 `imported` 된 패키지의 mtime 변경 → `discovered` 로 되돌림(자동 재임포트 X). 페이지에 "업데이트됨, 다시 임포트?" 표시.
- 사용자가 "다시 후보로" 누름 → `state='discovered'` 강제.

## 5. 모듈 계획

### 5.1 신규 모듈

| 경로 | 책임 |
|---|---|
| `src/gah/core/unity_import/__init__.py` | 빈 패키지 마커 |
| `src/gah/core/unity_import/types.py` | 7 frozen dataclass: `UnityPackagePath(abs_path, publisher, category, asset_name, size, mtime)` / `UnityPackageEntry(guid, pathname, internal_kind: "image"|"sound", size)` / `UnityPackagePreview(asset_count, image_count, sound_count, sample_pathnames: list[str])` / `UnityScanResult(scanned, new, updated, unchanged, removed, cache_path, warnings)` / `UnityImportResult(pack_id, pack_name, asset_count, state, error)` / `UnityImportRecord` (DB row 미러) |
| `src/gah/core/unity_import/cache_paths.py` | `detect_cache_path(config) -> Path \| None` — D3 우선순위 검출 |
| `src/gah/core/unity_import/unitypackage.py` | `parse_pathnames(package_path) -> dict[guid, UnityPackageEntry]` / `extract_targets(package_path, dest_dir, target_guids) -> ExtractResult` — D4 |
| `src/gah/core/unity_import/scanner.py` | `UnityAssetStoreScanner.run_once(force=False, filter=None) -> UnityScanResult` — 디렉터리 walk + DB 비교 + state 머신 (D2, D17) |
| `src/gah/core/unity_import/importer.py` | `UnityImporter.import_package(unity_import_id) -> UnityImportResult` — tarfile.extract + pack.json 생성 + DB 갱신 (D5). 백그라운드 큐 + SSE 진행 emit |
| `src/gah/core/unity_import/remote_optin.py` | `UnityRemoteOptInClient` skeleton — D10 |
| `src/gah/web/routers/unity_asset_store.py` | `/unity-asset-store` GET (HTML) + `/api/unity-packages` 라우터 그룹 (scan / list / preview / import / skip / restore) + SSE 진행 stream |
| `src/gah/web/routers/projects.py` | `/projects` GET / `/projects/<id>` GET (HTML) + `/api/projects` POST (신규 생성) + `/api/active-project` GET/PUT + `/api/assets/<id>/adopt` POST |
| `src/gah/web/templates/unity_asset_store.html` | Unity 페이지 본문 |
| `src/gah/web/templates/projects_list.html` | `/projects` 본문 |
| `src/gah/web/templates/project_detail.html` | `/projects/<id>` 본문 |
| `src/gah/web/templates/_header_project_dropdown.html` | 글로벌 헤더 드롭다운 fragment (D12) |
| `src/gah/web/templates/_modal_new_project.html` | "+ 새 프로젝트" 모달 fragment |
| `src/gah/web/templates/_unity_package_row.html` | Unity 페이지 표 row fragment (HTMX swap 대상) |
| `src/gah/web/templates/_preference_panel.html` | `/projects/<id>` 자산별 선호도 패널 fragment |

### 5.2 수정 모듈

| 경로 | 변경 |
|---|---|
| `src/gah/core/store.py` | (1) `Store.initialize()` 에 `unity_imports` CREATE TABLE + 컬럼 존재 검사 (D15). (2) Unity 관련 API: `insert_unity_import` / `upsert_unity_import` / `update_unity_state` / `list_unity_imports(filter, offset, limit)` / `get_unity_import_by_id` / `get_unity_import_by_path`. (3) 활성 프로젝트: `get_active_project_id()` (Config 위임), `set_active_project_id(id?)`. (4) 프로젝트 페이지 쿼리: `upsert_project(external_id, display_name)` (이미 있는지 확인 후 추가), `list_projects_with_summary()`, `get_project_asset_usage(project_id, offset, limit)`, `get_project_pack_distribution(project_id, top_n=5)`, `get_project_asset_preferences(project_id, sort, search, offset, limit)`. (5) `record_asset_use` 가 `source="user_web"` 도 받도록 enum 확장 (M3 의 `'explicit'|'implicit_top1'|'manual'` 에 추가). |
| `src/gah/config.py` | D15 의 신규 필드 5개 추가. `load_config` / `save_config` 의 backward compat (기본값으로 채움). |
| `src/gah/app.py` | (1) 부팅 직후 `UnityAssetStoreScanner.run_once()` 별도 스레드 실행 (D6). (2) `UnityImporter` 백그라운드 큐 초기화. (3) 트레이 메뉴에 "Unity 캐시 스캔" + "현재 프로젝트" 서브메뉴 추가 (D16). |
| `src/gah/tray.py` | 트레이 메뉴 항목 확장. |
| `src/gah/mcp/models.py` | `ScanUnityAssetStoreCacheRequest` / `ScanUnityAssetStoreCacheResult` / `ListUnityPackagesRequest` / `ListUnityPackagesResult` Pydantic 모델. |
| `src/gah/mcp/tools.py` | `tool_scan_unity_asset_store_cache(deps, req)` + `tool_list_unity_packages(deps, req)`. |
| `src/gah/mcp/server.py` | `register_all_tools` 에 2 도구 추가 (18 → **20**). `INSTRUCTIONS` 갱신. 로그 `tools=18` → `tools=20`. |
| `src/gah/web/app.py` (또는 `server.py`) | 신규 라우터 2개 등록 (`unity_asset_store` + `projects`). 글로벌 헤더 fragment 를 base 템플릿에 포함. SSE active-project broadcast 라우트. |
| `src/gah/web/templates/base.html` | 사이드바 메뉴 신규 2개 + 글로벌 헤더 fragment 포함. |
| `src/gah/web/routers/library.py` | 자산 카드의 "채택" 버튼 hook 갱신 — 활성 프로젝트 없으면 disabled (D13). 검색 호출에 활성 프로젝트 `project_id` 자동 포함. |
| `src/gah/web/routers/feedback.py` | 활성 프로젝트로 `report_feedback` 호출. |
| `src/gah/web/routers/picks.py` | Claude pending-pick 의 사용자 채택 endpoint(`PUT /api/user-pick/{rid}`) 가 활성 프로젝트로 `record_asset_use(source="claude_pick")` 호출하도록 갱신. M5 가 이미 `project_id` 전달 흐름은 만들었으나 활성 프로젝트 컨텍스트와 fallback 일관화 필요. |
| `src/gah/web/static/css/main.css` | 글로벌 헤더 드롭다운 / Unity 페이지 표 / 프로젝트 페이지 카드 / 선호도 막대 / 상태 칩 스타일. |
| `src/gah/web/static/css/themes.css` | 상태 칩 / 선호도 막대 light/dark 색상. |
| `src/gah/web/static/js/app.js` (또는 alpine.js component) | 활성 프로젝트 state + 드롭다운 토글 + 채택 버튼 disabled 상태 동기화 + SSE active-project broadcast 수신. |
| `docs/MCP_USAGE_GUIDE.md` | 19, 20번째 도구 설명 + Claude Code 워크플로 예시 ("Unity 에셋 보유 안내" 흐름) 추가. |
| `DESIGN.md` | §4.9 / §5.4 / §6.11 / §11 Milestone 7 → 완료 표시. §6.11 단일 도구가 2 도구로 분리됨 명시. 활성 프로젝트 / 프로젝트 페이지 / 자산별 선호도 시각화 명세 신규 §4.10 ~ §4.12 추가 (또는 §3 에 흡수). |
| `CLAUDE.md` | §2 진행 현황 표 — M7 행 (대기 → 진행 → 완료). §8 다음 작업 갱신 (M8). |
| `HANDOFF.md` | M7 완료 인계 — 자동 테스트 통과 카운트 + 시나리오 + 다음 작업 (M8). |
| `pyproject.toml` | **변경 없음** (신규 의존성 0). |

### 5.3 테스트 (~125 신규 케이스)

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_unity_import_types.py` | ~7 | 7 frozen dataclass 동등성 / hashable / 직렬화 |
| `tests/test_unity_cache_paths.py` | ~6 | Config 우선 / env 다음 / Unity Pref 다음 / 기본 / 모두 없음 → None / 존재하지 않는 경로 → None |
| `tests/test_unity_unitypackage.py` | ~12 | 작은 fixture .unitypackage 파싱 / pathname 텍스트 추출 / 이미지 6 확장자만 필터 / 사운드 3 확장자만 필터 / PSD 제외 / extract_targets 가 dest_dir 에 물리 복사 / 디렉터리 구조 보존 / 빈 .unitypackage / 손상된 .unitypackage 처리 / gzip 헤더 검증 / 큰 파일 (mock) / 한글 pathname |
| `tests/test_unity_scanner.py` | ~10 | 디렉터리 walk 가 .unitypackage 만 픽업 / 신규 → discovered / mtime 동일 → unchanged / mtime 변경 + state=imported → discovered 되돌림 (D17) / mtime 변경 + state=skipped → discovered 되돌림 / 사라진 파일 → removed 카운트 (state 변경 X) / filter publisher_glob / filter asset_name_glob / 빈 캐시 디렉터리 / 권한 없는 디렉터리 → warning |
| `tests/test_unity_importer.py` | ~8 | tarfile.extract → library/<pack_name>/<원본> 복원 / pack.json 자동 생성 / 물리 복사 검증 / 임포트 후 state=imported / 실패 시 state=failed + import_error / 동시 임포트 락 / 라이브러리 인테이크 흐름 트리거 / imported_at 기록 |
| `tests/test_unity_remote_optin.py` | ~3 | is_enabled() 기본 False / fetch_owned_assets() → NotImplementedError / Config 토글 활성 시 동작 변화 (skeleton 만) |
| `tests/test_store_m7_unity.py` | ~10 | unity_imports CREATE TABLE 마이그레이션 idempotent / preview 컬럼 nullable / insert / upsert / update_state / list filter + offset + limit / get_by_id / get_by_path / state 머신 invariant / 마이그레이션 두 번 실행 |
| `tests/test_store_m7_projects.py` | ~10 | upsert_project (신규/기존) / list_projects_with_summary / get_project_asset_usage / get_project_pack_distribution / get_project_asset_preferences + 정렬 4종 / 검색 / 페이지네이션 / I-5 격리 (project_A weight 가 project_B 점수 영향 X) / preference_score 공식 / 빈 프로젝트 |
| `tests/test_store_m7_config.py` | ~5 | Config 신규 필드 5개 로드/저장 / backward compat (기본값) / active_project_id None/Some / Config 라운드트립 / save_config 변경 후 load_config |
| `tests/test_mcp_tools_m7.py` | ~10 | scan_unity_asset_store_cache 정상 / 캐시 없음 → 503 / 권한 없음 → 403 / list_unity_packages 정상 / state 필터 / filter glob / include_preview / offset+limit / import_url 포함 / invalid_state → 400 |
| `tests/test_mcp_integration.py` (수정) | 0 신규 / 갱신 | `tools/list` 응답 18 → **20** 도구. |
| `tests/test_web_routers_unity.py` | ~8 | `/unity-asset-store` GET 200 / 발견 목록 표시 / preview API / import API + SSE progress / skip API / restore API / focus query 하이라이트 / 빈 캐시 안내 |
| `tests/test_web_routers_projects.py` | ~8 | `/projects` GET / 활성 프로젝트 강조 / `/projects/<id>` GET / 사용 이력 표 / 채택 팩 분포 / 자산별 선호도 패널 / 정렬 4종 / 검색 + 페이지네이션 |
| `tests/test_web_active_project.py` | ~8 | GET /api/active-project None 응답 / PUT 변경 / POST /api/projects 신규 / POST /api/assets/<id>/adopt + 활성 프로젝트 / 활성 None 시 adopt → 400_no_active_project / SSE broadcast / Config 영속 / 글로벌 헤더 fragment 렌더 |
| `tests/test_web_card_adopt_button.py` | ~5 | 활성 프로젝트 있음 → 버튼 enabled / 없음 → disabled + tooltip / 클릭 → POST adopt / 응답 후 카드 ✓ 표시 / source="user_web" 기록 |
| `tests/test_isolation_invariants.py` | ~5 | I-1 (discovered 자산 not in assets) / I-2 (preview 부작용 없음) / I-3 (라이브러리 라우터 unity_imports 조회 X — 코드 인스펙션 + 동작 검증) / I-4 (Unity 라우터 assets 조회 X) / I-5 (프로젝트 간 선호도 격리, 시나리오 테스트) |

**합계 ~125 신규 active 케이스**.

baseline 887 + ~125 = **~1012 active 목표**.

## 6. 작업 phase

| Phase | 기간 | 산출물 |
|---|---:|---|
| **0 — 스캐폴딩 + 테스트 fixture** | 0.5일 | `core/unity_import/` 패키지 + `types.py` (7 dataclass) + 작은 `.unitypackage` fixture 생성 helper(tests/fixtures/) + 7 테스트 파일의 red 케이스 작성 |
| **1A — cache_paths.py** | 0.5일 | D3 우선순위 검출 + ~6 테스트 |
| **1B — unitypackage.py** | 1일 | parse_pathnames + extract_targets + ~12 테스트 |
| **1C — scanner.py** | 1일 | state 머신 walk + ~10 테스트 |
| **1D — importer.py** | 1일 | tarfile.extract + pack.json 생성 + 인테이크 트리거 + ~8 테스트 |
| **2A — Store unity_imports + Config 마이그레이션** | 0.5일 | CREATE TABLE + Config 신규 필드 + idempotent 마이그레이션 + ~15 테스트 |
| **2B — Store projects 쿼리 + 트레이 메뉴 + 부팅 자동 스캔 hook** | 0.5일 | list_projects_with_summary / get_project_asset_preferences 등 + 트레이 메뉴 + 부팅 시 scanner.run_once + ~13 테스트 |
| **3A — MCP Pydantic 모델 + 도구 구현** | 0.5일 | 4 모델 + 2 도구 + 에러 매핑 + import_url builder + ~10 테스트 |
| **3B — MCP server 등록 + INSTRUCTIONS + integration** | 0.5일 | register_all_tools 18 → 20 + mcp_integration 20 도구 검증 |
| **4A — `/unity-asset-store` 라우터 + SSE + remote skeleton** | 1일 | 라우터 + scan/preview/import/skip/restore API + SSE 진행 + Config 토글 placeholder + ~8 테스트 |
| **4B — `/unity-asset-store` UI + 사이드바 메뉴** | 0.5일 | 페이지 HTML + 표 + 상태 칩 + focus 하이라이트 + ~5 테스트 |
| **5 — 활성 프로젝트 컨텍스트 + 채택 버튼 통합** | 1일 | 글로벌 헤더 드롭다운 + 신규 프로젝트 모달 + 라우터 + SSE broadcast + 채택 버튼 hook + 라이브러리/피드백/픽 라우터 갱신 + ~13 테스트 |
| **6A — `/projects` 라우터 + 페이지 HTML** | 0.5일 | 목록 페이지 + ~4 테스트 |
| **6B — `/projects/<id>` 사용 이력 + 채택 팩 분포** | 0.5일 | 상세 페이지 본문 1, 2 + ~4 테스트 |
| **6C — `/projects/<id>` 자산별 선호도 패널** | 1일 | 선호도 점수 공식 + 표 + 정렬/검색/페이지네이션 + I-5 회귀 테스트 + ~8 테스트 |
| **7 — 격리 invariant 회귀 테스트 + 문서 마감 + verification** | 0.5일 | `test_isolation_invariants.py` (I-1~I-5 모두) + `M7_verification.md` + DESIGN/CLAUDE/HANDOFF/MCP_USAGE_GUIDE 갱신 |
| **합계** | **~10일** | |

> Phase 5 가 cross-cutting 이라 Phase 4 와 Phase 6 사이에 둠. M5/M6 의 phase 순서와 약간 다르지만 활성 프로젝트가 프로젝트 페이지의 기반이라 순서가 자연스러움.

## 7. 핵심 결정 요약 (체크리스트)

- [x] **D1**: 베이스라인 = DESIGN §4.9.1 + §5.4 + §6.11 그대로.
- [x] **D2**: 스캔 / 미리보기 / 임포트 3단계 분리 + state 머신.
- [x] **D3**: 캐시 경로 검출 우선순위 (Config → env → Unity Pref → 기본).
- [x] **D4**: `.unitypackage` 파서 = 표준 tarfile + gzip, 이미지/사운드 6 확장자만.
- [x] **D5**: 임포트 = 물리 복사, library/<pack_name>/ 일반 인테이크 흐름.
- [x] **D6**: 부팅 1회 자동 스캔 + 수동, 임포트는 100% 사용자 클릭.
- [x] **D7**: 라이브러리 ↔ Unity 후보 격리 invariant I-1~I-4.
- [x] **D8**: 프로젝트 간 선호도 격리 invariant I-5.
- [x] **D9**: MCP 2 도구 (scan + list). 18 → **20**.
- [x] **D10**: publisher 패널 skeleton, 기본 비활성, 403_remote_disabled.
- [x] **D11**: 웹 페이지 신규 2 (/unity-asset-store + /projects + /projects/<id>).
- [x] **D12**: 활성 프로젝트 = 서버 측 Config, 글로벌 헤더 드롭다운, SSE broadcast.
- [x] **D13**: 채택 버튼 활성 프로젝트 연동 + 비활성 시 disabled.
- [x] **D14**: 자산별 선호도 점수 = sum(feedback.weight) + 0.1 * usage_count.
- [x] **D15**: 마이그레이션 idempotent (unity_imports CREATE TABLE + Config 신규 필드).
- [x] **D16**: 트레이 메뉴 = 스캔만, 새 발견 N건 Windows 토스트 알림.
- [x] **D17**: skipped 영구, mtime 변경 시 discovered 되돌림 (자동 재임포트 X).

## 8. v1 의도적 미룬 항목 (v2 또는 M8+ 흡수)

- **publisher 패널 실제 HTTP 구현** — `kharma_session` 쿠키 기반 비공식 엔드포인트. v1 skeleton 만, v2 검토 (DESIGN §4.9.2).
- **자동 동기화 스케줄러** — 매일 1회 / 부팅 외 추가 자동 스캔. v1 은 부팅 1회 + 수동만. M8.
- **캐시에서 사라진 .unitypackage 자동 제거** — v1 은 통보만(removed 카운트). v2 에서 사용자 토글 GUI + 실제 제거.
- **다중 캐시 경로** — 회사 계정 / 개인 계정 분리 시. v1 은 단일 경로. v2.
- **UPM 패키지(`.tgz` / scoped registry) 임포트** — Unity 의 새 패키지 형식. v1 은 `.unitypackage` 만. v2.
- **사용자 별칭 매핑 GUI** — Unity 프로젝트 경로 별칭. v1 은 external_id = 절대경로. v2.
- **`get_active_project` / `set_active_project` / `get_project_preferences` MCP 도구** — 사용자 의도가 "웹화면 전용" 이라 v1 X. v2 검토.
- **PSD/TGA 확장자 임포트** — Unity 자주 쓰지만 GAH 분석기 미지원. v2 에서 분석기 확장 + 동시 임포트 확장.
- **자산별 선호도 직접 입력 UI** — 라이브러리 카드에서 좋아요/싫어요 버튼. v1 은 `report_feedback` MCP + 기존 feedback 라우터만. v2.
- **`search_queries` 로그 시각화** — `/projects/<id>` 본문 4. v2.
- **프로젝트별 자산 export (JSON)** — `/projects/<id>` 다운로드 버튼. v2.
- **임포트 완료 후 되돌리기** — 사용자가 임포트한 팩을 "라이브러리에서 빼기" 시 unity_imports 자동 되돌림. v1 은 라이브러리 페이지에서 일반 팩 삭제 우회. v2.
- **디스크 사용량 표시** — 팩 카드의 size. v2 / M8.
- **GUI 에서 frame size 입력** — M6 미룬 항목, M7 도 미루어 v2.

## 9. 외부 출처 (1차)

- [Unity Manual — Asset Store 개요](https://docs.unity3d.com/Manual/AssetStore.html)
- [Unity Manual — Asset Store cache location](https://docs.unity3d.com/Manual/upm-config-cache-as.html)
- [UnityCommunity wiki — Move Unity caches](https://github.com/UnityCommunity/UnityLibrary/wiki/Move-Unity-caches-and-asset-store-files-into-another-drive)
- [Python `tarfile` — gzip-compressed tar](https://docs.python.org/3/library/tarfile.html)
- [Python `gzip` — Support for gzip files](https://docs.python.org/3/library/gzip.html)

DESIGN.md §14 + §4.9 의 출처 표 그대로 참고.
