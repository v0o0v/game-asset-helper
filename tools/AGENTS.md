<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# tools

## Purpose
개발자용 일회성 inspection / 셋업 스크립트. 패키지에 포함되지 않으며 (`pyproject.toml` 의 `setuptools.packages.find` 가 `src/` 만 검색), 사용자에게 노출되지 않는다. 마일스톤 검증 중 일회성 점검이 필요할 때 사용.

## Key Files
| File | Description |
|------|-------------|
| `inspect_m6.py` | M6 spritesheet 검증 — 격자 검출 / 8칸 미리보기 / 사이드카 JSON 파싱 결과를 콘솔에 덤프 |
| `setup_m6_test.py` | M6 회귀 환경 셋업 — fixture 파일 build + DB 초기화 |

## For AI Agents

### Working In This Directory
- **일회성** — 이 디렉터리의 스크립트는 마일스톤 검증 중 1~2회 돌리고 끝. 회귀에 포함되지 않으며, 마일스톤 종료 후 도태되면 삭제해도 OK.
- **scripts/ 와 차이** — `scripts/` 는 LIVE 검증 / 빌드 보조처럼 **반복 호출**되는 도구. `tools/` 는 마일스톤 점검 / 디버그용 **일회성**.
- 새 inspection 스크립트는 `inspect_m{N}.py` / `setup_m{N}_test.py` 명명 — 어느 마일스톤 산출물인지 추적 용이.
- 실행: `python tools/inspect_m6.py ...` (venv 활성화 후).

### Testing Requirements
- 회귀 없음.

### Common Patterns
- 콘솔 덤프 + assert 없음 — 사람이 출력 보고 판단.
- pythonpath 의존 — `pyproject.toml [tool.pytest.ini_options].pythonpath = ["src"]` 가 pytest 전용이라, 스크립트 실행 시엔 venv install (`pip install -e .`) 이 되어 있어야 `import assetcache` 가능.

## Dependencies

### Internal
- `src/assetcache/core/sheet/` (inspect_m6).

### External
- Pillow (시각 확인용 dump).

<!-- MANUAL: 마일스톤 검증 후 도태된 스크립트는 삭제해도 회귀 영향 없음. -->
