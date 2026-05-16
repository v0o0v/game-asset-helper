# Game Asset Helper

Unity 게임 개발 중 Claude Code가 보유 에셋(2D 스프라이트, 스프라이트 시트, 사운드)을 자연어로 요청하면 가장 적합한 후보를 돌려주는 **MCP 서버 + 윈도우즈 트레이 상주 앱**.

- 사용자가 `library/<pack>/...` 형태로 에셋 팩 폴더를 통째로 드롭하면 자동 인덱싱
- Ollama로 도는 **Gemma 4**(`gemma4:e4b`)가 이미지·오디오를 직접 보고 의미 라벨 생성
- 한 프로젝트에서 한 번 채택한 팩을 이후 검색에서 우선시해 **통일성 유지**
- Unity Asset Store 로컬 캐시(`.unitypackage`)도 자동 임포트

전체 설계는 [`DESIGN.md`](./DESIGN.md).

## 진행 현황

| 마일스톤 | 상태 | 비고 |
|---|---|---|
| M0 — 뼈대 | ✅ 완료 (18/18 테스트 통과) | 트레이 셸·설정·로깅·단일 인스턴스 |
| M1 — 워처 + Pack Manager + DB | 다음 | |
| M2 — 분석 파이프라인 | 대기 | Pillow / librosa / Gemma 4 |
| M3 — 검색 + 통일성 + MCP | 대기 | |
| M4 — 시트 분석 + 애니메이션 | 대기 | |
| M5 — Unity Asset Store 임포트 | 대기 | |
| M6 — GUI 마감 + 패키징 | 대기 | |

마일스톤 사이클(plan → todo → 테스트 → 구현 → verification) 상세는 [`milestones/README.md`](./milestones/README.md).

## 시작하기

> Windows 10 + python.org 정식 Python 3.12 기준. Microsoft Store Python은 `%APPDATA%` 가상화 이슈로 권장하지 않는다.

venv는 작업 폴더 바깥(사용자 홈)에 만든다.

```powershell
python -m venv $env:USERPROFILE\.venvs\gah
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

editable 설치 (이 디렉터리에서):

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

테스트:

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `18 passed` 가 나오면 M0 기준점 OK.

## 실행

```powershell
python -m gah --tray
```

→ 시스템 트레이에 아이콘이 뜬다. 트레이 우클릭 → 종료.

기타:

```powershell
python -m gah --version
```

```powershell
python -m gah --mcp
```

(M3에서 활성화 예정 — 현재는 종료 코드 2로 종료)

## 런타임 데이터 위치

- `%APPDATA%\GameAssetHelper\library\` — 에셋 팩(사용자가 직접 드롭)
- `%APPDATA%\GameAssetHelper\cache\` — 썸네일·스펙트로그램
- `%APPDATA%\GameAssetHelper\metadata.db` — SQLite (M1부터)
- `%APPDATA%\GameAssetHelper\config.toml`
- `%APPDATA%\GameAssetHelper\logs\gah.log`

## 문서 맵

| 문서 | 누가 보는가 |
|---|---|
| [`README.md`](./README.md) | 처음 들어오는 사람 |
| [`CLAUDE.md`](./CLAUDE.md) | Claude(코드 에이전트)가 작업 시작할 때 |
| [`HANDOFF.md`](./HANDOFF.md) | 다음 세션으로 인계할 때의 현재 스냅샷 |
| [`DESIGN.md`](./DESIGN.md) | 아키텍처·MCP 도구·데이터 스키마 |
| [`milestones/`](./milestones/) | 마일스톤별 plan·todo·verification |

## 개발 규칙

- 모든 문서는 한글, 폴더·파일 이름은 영어
- 마일스톤마다 plan → todo → 테스트 먼저 → 구현 → verification 순서
- 최신 모델·API·버전은 추측 말고 1차 출처 확인 후 반영
- 자세한 건 [`CLAUDE.md §4`](./CLAUDE.md)

## 라이선스

MIT (변경될 수 있음).
