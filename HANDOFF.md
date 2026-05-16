# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-16
**마지막 완료 마일스톤**: M1 (워처 + Pack Manager + DB)
**다음 작업**: M2 (분석 파이프라인 — Pillow / librosa / Ollama 클라이언트)

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤이 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

설계(`DESIGN.md`) 위에 M0(뼈대)와 M1(워처 + 팩 매니저 + SQLite 4테이블 + GUI 팩/라이브러리 탭)이 자동 63 테스트 통과 + 수동 시나리오 항목까지 정리됐다. 다음은 M2(Pillow/librosa 기술 특성, Ollama Gemma 4 멀티모달, 임베딩) 를 같은 TDD 사이클로 시작한다.

## 2. 검증된 사실 (M1 시점)

자동 — `pytest -v` 결과 **63/63 통과** (1.14s, Windows 10 / Python 3.12.10).

```
tests/test_asset_kind.py           4 passed
tests/test_config.py               6 passed (M0)
tests/test_entrypoint.py           3 passed (M0)
tests/test_imports.py              1 passed (모듈 목록은 M1 신규 포함)
tests/test_logging.py              4 passed (M0)
tests/test_manifest.py             8 passed
tests/test_pack_manager.py         8 passed
tests/test_scanner.py              5 passed
tests/test_single_instance.py      4 passed (M0)
tests/test_store.py               12 passed
tests/test_ui_smoke.py             3 passed
tests/test_watcher.py              5 passed  (PackDebouncer 단위)
```

수동 검증 항목과 단계는 [`milestones/M1_verification.md`](./milestones/M1_verification.md) §3 참고. 사용자가 실제로 트레이를 띄우고 `library/` 에 폴더를 떨어뜨려 GUI 갱신·삭제 화해·부팅 풀스캔을 확인한다.

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL 모드) |

**금기**: Microsoft Store Python(`%APPDATA%` 가상화 문제), Cowork 작업 폴더 내부의 venv(권한 충돌).

M1에서 새로 추가된 의존성: `watchdog>=4.0`. 기존 venv를 그대로 쓰는 경우 다음 한 줄 추가 설치가 필요:

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

(편집 가능 설치라 `pyproject.toml`의 새 의존성이 알아서 따라온다. 최근 베리파이 환경에는 `watchdog 6.0.0`이 들어가 있다.)

## 4. 새 세션에서 바로 이어가는 방법

이미 venv가 설치된 PC라면:

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `63 passed` 확인. 그러면 M0+M1 기준점은 유지되고 있다는 뜻.

venv가 없는 새 PC라면 [`CLAUDE.md §6`](./CLAUDE.md) 의 셋업 절차 그대로.

## 5. M2 시작 절차

[`CLAUDE.md §8`](./CLAUDE.md) 와 [`DESIGN.md`](./DESIGN.md) 의 다음 섹션을 본떠 마일스톤 사이클을 다시 돈다.

- `DESIGN.md §4.2` Asset Analyzer (스프라이트·시트·사운드 파이프라인)
- `DESIGN.md §4.3` Embedding 인덱스 (`nomic-embed-text`)
- `DESIGN.md §5.1` 의 `sprite_meta`, `sound_meta`, `assets_fts`, `asset_embeddings` 스키마 — **M2에서 새로 추가**
- `DESIGN.md §6.x` 의 응답 JSON 스키마 (Pydantic 검증)
- `DESIGN.md §8.1/§8.2` 분석 트리거 흐름과 폴백 체인

요약:

1. [`milestones/M1_plan.md`](./milestones/M1_plan.md) 를 템플릿으로 `M2_plan.md` 작성.
2. `M2_todo.md` — TDD 순서 체크리스트.
3. `tests/test_analyzer_sprite.py`, `tests/test_analyzer_sound.py`, `tests/test_ollama_client.py`, `tests/test_store_m2.py` 등 실패 테스트 먼저.
4. `src/gah/core/analyzer/`, `src/gah/core/ollama_client.py`, `src/gah/core/embedding.py` 구현.
5. `M2_verification.md` 작성.

M2 범위 밖 (M3 이후):

- 검색·통일성·MCP 도구(`find_asset`, `suggest_packs` 등) — M3
- 시트 자동 분할·애니메이션 추정 — M4
- Unity Asset Store 임포트 — M5
- 라이브러리 탭 필터/썸네일 그리드 등 GUI 마감 — M6

## 6. M1 에서 의도적으로 남겨둔 자리

- `Store.initialize()` 는 M1 의 4 테이블만 만든다. M2 가 같은 `Store` 위에 `sprite_meta`/`sound_meta`/`assets_fts`/`asset_embeddings` 마이그레이션을 얹으면 된다. 분리는 모듈 단에서 결정 — 같은 `Store` 클래스에 메서드를 추가하거나 별도 `migrations.py` 를 둘지는 M2 plan 단계에서 정한다.
- `assets.analysis_state` 는 현재 `'pending'` 으로만 들어간다. M2 분석기가 `'analyzing' → 'ok' / 'partial' / 'failed'` 전이를 담당.
- `packs.aggregate_meta` 컬럼은 만들어 두기만 했고 항상 NULL. M2 분석 결과를 모아서 채운다.
- `Config.watch_debounce_seconds`, `Config.library_dir_override` 두 필드는 추가됐고 워처/부팅 경로에서 이미 사용 중. 비표준 라이브러리 경로를 테스트할 때 사용 가능.
- `gah.core.watcher.LibraryWatcher` 의 `on_pack_changed` 콜백은 M2 에서 그대로 "분석 큐에 넣기" 로 확장 가능. 현재는 `MainWindow.packChanged.emit` 로만 라우트.

## 7. 문서 맵

- [`README.md`](./README.md) — 사용자용 시작 안내
- [`CLAUDE.md`](./CLAUDE.md) — Claude(코드 에이전트)용 작업 가이드
- [`HANDOFF.md`](./HANDOFF.md) — 이 파일, 마일스톤 경계의 인계 스냅샷
- [`DESIGN.md`](./DESIGN.md) — 전체 아키텍처·스키마·MCP 명세
- [`milestones/`](./milestones/) — 마일스톤별 plan/todo/verification

## 8. 갱신 규칙

이 문서는 다음 시점에 반드시 업데이트한다.

1. 마일스톤이 완료될 때 (§2 검증 결과, §1 한 줄 요약, "다음 작업").
2. 환경 결정이 바뀔 때 (§3).
3. 새 금기·주의사항이 발견될 때 (§3 또는 별도 섹션).

내용을 누적하기보다 **현재 시점의 진실만** 적는다. 과거 이력은 git log에 맡긴다.
