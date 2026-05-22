# 개발 환경 셋업 + 자주 쓰는 명령

이 파일은 [CLAUDE.md](../CLAUDE.md) §6 + §7 에서 분리됨. 한 번 익히면 다시 안 봐도 되는 내용이라 별도 파일로.

## 1. 개발 환경 셋업 (새 PC에서)

```powershell
git clone https://github.com/v0o0v/assetcache-mcp.git
```

```powershell
cd assetcache-mcp
```

```powershell
python -m venv $env:USERPROFILE\.venvs\gah
```

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
pip install -e .[dev]
```

```powershell
pytest -q
```

`pytest -q` 가 떨어지는 baseline 은 [`milestones/HISTORY.md`](../milestones/HISTORY.md) 의 가장 최근 마일스톤 verification 참고 (현재 main = **1559 passed + 1 skipped + 57 deselected**, M11.3).

옵트인 마커:
- `pytest -m mcp_integration` — 실 `python -m assetcache --mcp` subprocess + JSON-RPC (20 도구)
- `pytest -m llm_integration` — Gemini + OpenAI 옵트인 케이스. 각 backend 별 환경변수 셋업 필요 (M11.9 에서 Claude/OpenRouter/HuggingFace 통합 테스트 제거)

## 2. 자주 쓰는 명령

테스트 전체:

```powershell
pytest -q
```

테스트 한 파일만:

```powershell
pytest tests/test_config.py -v
```

트레이 모드 실행:

```powershell
python -m assetcache --tray
```

버전 확인:

```powershell
python -m assetcache --version
```

MCP stdio 서버 모드:

```powershell
python -m assetcache --mcp
```

격리 데이터 디렉토리로 실행 (검증용):

```powershell
python -m assetcache --tray --data-dir "$env:TEMP\acmcp_test"
```
