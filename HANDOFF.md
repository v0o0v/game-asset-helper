# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-16
**마지막 완료 마일스톤**: M0 (뼈대)
**다음 작업**: M1 (워처 + Pack Manager + DB)

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤이 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

설계 문서(`DESIGN.md`)는 완성되어 있고, M0(뼈대)는 자동 18개 테스트 + 수동 트레이/단일 인스턴스 검증까지 모두 통과한 상태. 다음은 M1(폴더 워처 + 팩 매니저 + SQLite 스키마)을 같은 TDD 사이클로 시작한다.

## 2. 검증된 사실 (M0 시점)

자동 — `pytest -v` 결과 18/18 통과 (0.25s).

```
tests/test_config.py            6 passed
tests/test_entrypoint.py        3 passed
tests/test_imports.py           1 passed
tests/test_logging.py           4 passed
tests/test_single_instance.py   4 passed
```

수동 검증 (사용자 PC, 2026-05-16):

- `python -m gah --version` → 종료 코드 0, 버전 출력 ✅
- `python -m gah --mcp` → 종료 코드 2, "not implemented" ✅
- `python -m gah --tray` → 시스템 트레이 아이콘 표시, `data_dir=C:\Users\v0o0v\AppData\Roaming\GameAssetHelper` ✅
- 두 번째 `python -m gah --tray` → "이미 실행 중입니다" 후 즉시 종료 ✅

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |

**금기**: Microsoft Store Python(`%APPDATA%` 가상화 문제), Cowork 작업 폴더 내부의 venv(권한 충돌).

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

→ `18 passed` 확인. 그러면 M0 기준점은 유지되고 있다는 뜻.

venv가 없는 새 PC라면 [`CLAUDE.md §6`](./CLAUDE.md) 의 셋업 절차 그대로.

## 5. M1 시작 절차

[`CLAUDE.md §8`](./CLAUDE.md) 에 핵심 산출물 목록이 있다. 정확한 작업 순서는 [`milestones/README.md`](./milestones/README.md) 의 마일스톤 사이클을 따른다.

요약:

1. [`milestones/M0_plan.md`](./milestones/M0_plan.md) 를 템플릿으로 `M1_plan.md` 작성. 목표·산출물·작업 단위·테스트 전략·검증 기준.
2. `M1_todo.md` 작성 — TDD 순서 체크리스트.
3. `tests/test_watcher.py`, `tests/test_pack_manager.py`, `tests/test_store.py` 등 실패 테스트 먼저.
4. `src/gah/core/` 아래 구현. 모듈 배치는 [`DESIGN.md §7`](./DESIGN.md) 의 트리를 따른다.
5. `M1_verification.md` 작성.

`DESIGN.md` 의 다음 섹션을 M1 진행 중 참조:

- §4.1 Folder Watcher & Pack Manager
- §5.1 `packs` / `assets` / `tags` / `asset_tags` 스키마 (M1 범위)
- §5.2 팩 매니페스트 (`pack.json`)
- §7 폴더 구조

M1 범위 밖 (M2~M6에서 처리):
- 실제 메타데이터 분석 (Pillow/librosa/Gemma 호출) — M2
- 임베딩/검색/MCP — M3
- 시트 자동 분할 — M4
- Unity Asset Store 임포트 — M5
- GUI 마감 — M6

## 6. 의도적으로 남겨둔 자리

- `src/gah/config.py` 의 `Config` 데이터클래스에는 M0가 안 쓰는 필드(`consistency_weight` 등)가 이미 들어 있다. M1+ 에서 활용.
- `src/gah/__main__.py` 의 `--mcp` 분기는 종료 코드 2로 자리만 잡혀 있다. M3에서 본체 연결.

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
