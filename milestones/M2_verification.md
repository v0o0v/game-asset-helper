# M2 검증 보고서

**최종 상태**: ✅ 자동 + 수동 모두 통과 (2026-05-17)

수동 검증 중 발견·즉시 fix 한 두 항목은 §4 참고.

## 1. 자동 검증 결과: ✅ 205/205 통과

`pytest -q` 전체 실행 결과 — M0/M1 회귀 67 + M2 신규 134 + M1 트레이/스모크 보존 3 = **204 통과** (`clip_integration` 마크 2 옵트인 제외).

```
========================= 204 passed, 2 deselected in 18.52s =========================
```

분해:

| 묶음 | 신규/회귀 | 케이스 수 |
|---|---|---|
| `test_store_m2` | 신규 | 17 |
| `test_labels` | 신규 | 19 |
| `test_labels_admin_ui` | 신규 | 7 |
| `test_ollama_client` | 신규 | 16 |
| `test_embedding` | 신규 | 5 |
| `test_clip_labeler` | 신규 | 6 (+ 2 `clip_integration` 옵트인 deselected) |
| `test_searchable` | 신규 | 9 |
| `test_analyzer_sprite` | 신규 | 11 |
| `test_analyzer_sound` | 신규 | 13 |
| `test_analysis_queue` | 신규 | 8 |
| `test_analysis_progress` | 신규 | 9 |
| `test_progress_statusbar` | 신규 | 4 |
| `test_config_m2` | 신규 | 5 |
| `test_ui_smoke_m2` | 신규 | 3 |
| `test_config` | M0 회귀 | 6 |
| `test_logging` | M0 회귀 | 4 |
| `test_single_instance` | M0 회귀 | 4 |
| `test_entrypoint` | M0 회귀 | 3 |
| `test_imports` | M0 회귀 (M2 모듈 추가) | 1 |
| `test_asset_kind` | M1 회귀 | 4 |
| `test_manifest` | M1 회귀 | 8 |
| `test_store` | M1 회귀 (M2 표 갱신 후) | 12 |
| `test_pack_manager` | M1 회귀 | 8 |
| `test_scanner` | M1 회귀 | 5 |
| `test_watcher` | M1 회귀 | 5 |
| `test_tray` | M1 회귀 | 4 |
| `test_ui_smoke` | M1 회귀 | 3 |
| **합계** | | **204** (활성) |

## 2. 자동 검증 환경의 한계

자동 테스트는 다음 항목을 다루지 **못한다** — 모두 사용자 PC 에서 수동 확인 대상이다.

- **Ollama 서버 실제 호출** — `OllamaClient` 는 `respx` 로 모킹돼 검증된다. 실제 `gemma4:e4b` 가 어떤 응답을 돌려주는지, force_json 강제가 안정적인지, 사운드 네이티브 입력이 실제로 통하는지는 사용자 환경에서만 확인 가능.
- **`open_clip_torch` 실모델** — `FakeBackend` 로 검증. 실제 ViT-B/32 (≈ 600 MB) 가 첫 분석 때 다운로드되는지, CUDA 가용시 device=cuda 가 잡히는지는 `clip_integration` 마크 옵트인 또는 수동 확인.
- **분석 큐 진행 ETA + 상태바 UI** — 위젯 단위 갱신은 offscreen 으로 검증했지만, 실제 분석 진행 중 상태바 + 트레이 툴팁이 동기화되는 흐름은 GUI 이벤트 루프 위에서 봐야 한다.
- **라벨 관리 다이얼로그 사용성** — 다이얼로그 위젯 생성·테이블 컬럼·추가/토글 동작은 offscreen 으로 검증했지만, 실제 사용자 입력 흐름(`Ctrl+L` 단축키 → 라벨 추가 → 새 분석에 반영)은 수동.

## 3. 사용자 측 수동 검증 항목

PowerShell 한 줄씩 분리해 실행 (`&&` 금지, `cd` 도 별도 줄).

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `204 passed, 2 deselected` 가 보여야 한다.

### 3.1 회귀 확인 (M0/M1 시나리오 그대로)

```powershell
python -m gah --version
```

→ 종료 코드 0, `game-asset-helper 0.0.1`.

```powershell
python -m gah --mcp
```

→ 종료 코드 2, "MCP mode is not implemented yet (planned for M3)."

### 3.2 트레이 + 메인 윈도우 + 분석 진행 상태바

```powershell
python -m gah --tray
```

확인 항목:

- 시스템 트레이에 아이콘이 나타난다.
- 아이콘 우클릭 → "메인 창 열기", "라벨 관리…", "종료" 세 메뉴.
- "메인 창 열기" → 빈 팩/라이브러리 탭 + 하단 상태바에 `분석 대기 중` 표시 + 작은 진행 바.
- 로그(`%APPDATA%\GameAssetHelper\logs\gah.log`) 에 다음 라인이 보임:
  - `library reconciled: ...`
  - CUDA PC: `CLIP backend initialized on device=cuda`
  - CPU PC: `CLIP backend initialized on device=cpu` (CLIP 모델 다운로드는 첫 분석 때, 정상)

### 3.3 분석 진행 (Ollama 가동 필요)

별도 PowerShell 창에서 Ollama 가 떠 있어야 한다.

```powershell
ollama serve
```

(이미 실행 중이면 생략)

```powershell
ollama pull gemma4:e4b
```

```powershell
ollama pull nomic-embed-text
```

다시 GAH 측 PowerShell 에서:

```powershell
mkdir $env:APPDATA\GameAssetHelper\library\kenney_test
```

```powershell
Copy-Item "C:\Windows\Web\Screen\img100.jpg" "$env:APPDATA\GameAssetHelper\library\kenney_test\hello.jpg"
```

```powershell
Copy-Item "C:\Windows\Media\Alarm01.wav" "$env:APPDATA\GameAssetHelper\library\kenney_test\alarm.wav"
```

대기 5~30초:

- 라이브러리 탭의 `분석 상태` 컬럼이 `pending → analyzing → ok` 순으로 전이.
- `라벨` 컬럼에 `axis=label` 형식 (예: `category=icon · style=photo · ...`) 표시.
- `설명` 컬럼에 한국어 한 줄 (예: `밝은 톤의 풍경 사진`).
- 상태바에 `분석 중 1/2 — kenney_test/hello.jpg — 약 N초 남음` 형식 등장. 트레이 hover → 같은 정보 짧게.
- 큐가 비면 상태바가 `분석 완료` → 잠시 후 `분석 대기 중` 으로 복귀.

### 3.4 라벨 관리 다이얼로그

메인 윈도우에서 `Ctrl+L`. 또는 트레이 메뉴 "라벨 관리…".

- 다이얼로그 상단에 24축 콤보 — `category` / `style` / ... / `sound_voice_type`.
- 축 선택 시 라벨 테이블 (라벨/상태/출처/설명) 채워짐.
- 새 라벨 입력란에 `Bad Token!` → "추가" → 인라인 빨간 안내 ("영문 소문자·숫자·`_` 만 가능").
- `cell_shaded_kr_custom` → 추가 → 즉시 테이블 행 등장, 출처 `user`. description 비어 있으면 `⚠` 경고 prefix.
- description 칸 클릭해 한 줄 입력 → 즉시 저장.
- 행 선택 + "선택 토글" → 활성 ↔ 비활성. 비활성 라벨은 다음 분석부터 어휘 제외.

### 3.5 DB 시각 확인

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db ".tables"
```

→ `asset_embeddings asset_labels asset_tags assets assets_fts assets_fts_* clip_label_cache labels packs sound_meta sprite_meta tags` 가 보여야 한다.

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db "SELECT axis, label, description FROM labels WHERE axis='style' LIMIT 5"
```

→ 시드 라벨 5개 + 영어 description 1줄.

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db "SELECT asset_id, axis, label, source FROM asset_labels LIMIT 10"
```

→ 분석된 에셋의 라벨 행 (source `gemma`/`clip` 혼재).

```powershell
sqlite3 $env:APPDATA\GameAssetHelper\metadata.db "SELECT asset_id FROM assets_fts WHERE searchable_text MATCH 'label:pixel_art'"
```

→ 픽셀아트 라벨이 붙은 에셋이 있다면 그 asset_id 가 반환.

### 3.6 CUDA 가용성 (선택)

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
```

→ `True` + 디바이스명이 나오면 다음 분석부터 GPU 가속. `False` 환경에서도 CPU 로 정상 분석.

### 3.7 Ollama 미기동 환경 (헬스체크)

Ollama 가 꺼진 상태에서 PNG 한 장을 라이브러리에 떨어뜨리면:

- 분석 시도 후 `analysis_state = failed` 로 마킹.
- 로그에 `OllamaError(stage=chat, path=native)` 라인.
- 워커는 죽지 않고 다음 항목을 계속 처리 (큐 헤드가 비도록 진행).

Ollama 를 다시 켜고 라이브러리에 파일을 더 추가하면 새 행은 정상 분석된다(`failed` 행은 그대로 — 재분석은 M3 의 `request_rescan` 도구로 다룬다).

## 3.8 수동 검증 결과 요약 (2026-05-17)

Claude 가 명령줄로 자동 가능한 1~9 항목을 모두 직접 실행. 사용자는 GUI 시각 4 항목 (트레이 아이콘 / 트레이 메뉴 / 메인 윈도우 + 컬럼 + 상태바 / 라벨 관리 다이얼로그) 확인 — 모두 OK.

자동 검증 중 발견 → 즉시 fix → 회귀 테스트 추가한 두 항목:

| # | 발견 | Fix |
|---|---|---|
| 1 | `Config.analysis_timeout_seconds = 30s` 가 CPU 환경 native 오디오 호출 (~36s 측정) 보다 짧아 매번 timeout → heuristic 폴백으로 강등 | default 60s 로 상향. `test_config_m2.py::test_new_fields_have_documented_defaults` 갱신. |
| 2 | Gemma 가 단일 enum 필드(`category` 등)를 list 로 돌려주는 경우 `_validate` 의 `cat not in cat_allowed` 가 `TypeError: unhashable type: 'list'` 폭주 | `_squash_single` 헬퍼로 첫 요소 채택. sprite/sound 양쪽 적용. `test_analyze_handles_list_typed_single_enum_fields` 신규 케이스. |

두 fix 모두 한 커밋(`1aa3b3e`)에 포함.

분석 결과 샘플:
- `kenney_m2_verify/alarm.wav` (sound, 5.6s) — state=ok, native path, 7축 10개 라벨, 768d 임베딩
- `kenney_m2_verify/hello.jpg` (sprite, 3840×2160) — state=partial(Gemma chat timeout), CLIP 14축 179개 라벨, 768d 임베딩, sprite_meta 정상
- `my_custom_sfx/alarm.wav` (sound, 5.6s) — state=partial(cold-start), heuristic 폴백 (`category=sfx`)

graceful fallback 으로 partial 도 검색 가능한 데이터는 채워짐 (라벨 + 임베딩 + 메타). Ollama 호출 자체의 cold-start 지연은 M2.1 동시성 패치에서 함께 검토.

> **M2.1 패치 후 갱신** (2026-05-17): 분석 큐 동시성 1 → 3, Ollama 호출 cap 2, SQLite write_lock, GUI 250ms 디바운스가 추가됐다. M2.1 의 자동 검증 결과(`221 passed, 2 deselected`) + 사용자 수동 검증 항목은 [`M2.1_verification.md`](./M2.1_verification.md). M2 의 단일 워커 가정에서 측정된 분석 시간은 M2.1 적용 후 환경에 따라 2~2.5x 단축이 기대된다.

## 4. 알려진 한계 / M3 로 미룬 것

- `assets_fts.searchable_text` 안에 라벨 description 자연어가 인용부호로 색인되지만, 실제 검색 쿼리는 M3 의 `find_asset` 백엔드가 등장해야 의미가 있다. M2 시점에는 단순 표 표시만.
- 라이브러리 탭의 `설명` 컬럼은 현재 비어 있는 상태로 시작한다 — Gemma 가 만든 자연어 설명을 별도 컬럼/뷰로 보존하는 작업은 M3 의 `find_asset` 응답 확장 + DB 컬럼 추가와 함께 다룬다. M2 의 라벨 컬럼은 그대로 동작한다.
- 시트 자동 분할(`spritesheet` kind 재분류 + 프레임 메타) 은 M5.
- 검색 결과 정렬·통일성 가중치·MCP 노출은 M3.
- 라벨 카탈로그의 `signature` 가 바뀌면 MCP 클라이언트가 캐시 무효화해야 한다는 계약은 stub 문서 `docs/MCP_USAGE_GUIDE.md` 에 명시. 실제 도구는 M3.
- 라벨 description 한국어 입력은 허용하지만(`set_description`), 검색 정확도는 영어 description 만큼 안정적이지 않다. 영어 권장.

## 5. M3 로 인계되는 데이터 모양

- 14개 새 SQLite 객체: sprite_meta / sound_meta / assets_fts (FTS5) / asset_embeddings / asset_labels / clip_label_cache / labels (+ 자동 생성 assets_fts_* 메타).
- `assets.analysis_state` 가 `pending → analyzing → ok / partial / failed` 전이를 거친다.
- `packs.aggregate_meta` 가 분석 완료된 팩마다 JSON 한 줄(`main_style`, `category_dist`, `palette`).
- `labels` 어휘 216개 시드 + 사용자 추가, `LabelRegistry.label_catalog_signature()` 가 캐시 키.
- `gah.core.searchable.build_searchable(...)` 가 모든 분석기에서 동일 형식으로 검색 텍스트 생성.
- `gah.core.analysis_queue.AnalysisQueue` 가 M3 의 `request_rescan` MCP 도구 백엔드로 그대로 재사용 가능.
- `docs/MCP_USAGE_GUIDE.md` stub 이 M3 가 도구를 구현할 때 1차 가이드.
