<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# mcp

## Purpose
MCP stdio 서버 + 도구 함수. `assetcache-mcp` / `python -m assetcache --mcp` 가 진입점. Claude Code 같은 MCP 클라이언트가 자식 프로세스로 spawn 해 자연어 에셋 검색을 한다. 트레이 프로세스와 SQLite WAL + `busy_timeout=5000` 으로 공존 (M2.1).

**현재 20 도구** — find_asset / suggest_packs / suggest_animation_frames / list_assets / get_asset / list_packs / list_labels / list_label_axes / describe_label / record_asset_use / report_feedback / save_search / run_saved_search / list_saved_searches / delete_saved_search / set_project_pin / request_rescan / scan_unity_asset_store_cache / list_unity_packages / request_user_pick.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | 패키지 마커 |
| `server.py` | `FastMCP` (mcp SDK) 기반 stdio 서버 빌더 + `run_stdio()` 진입점 + 도구 register + INSTRUCTIONS 문자열 (Claude Code 워크플로 + label_query 문법 + diversity 옵션 + 시트 + Unity 안내) |
| `tools.py` | 20 도구 함수 본체 — `ToolDeps` (store + search + usage + registry + queue + config + paths) + `McpToolError` (code + message). Write 도구는 `store.write_lock` 안에서 실행 |
| `models.py` | 도구별 입출력 Pydantic 모델. `extra="forbid"` 로 unknown field 검출, `Literal[...]` 화이트리스트, 응답은 dict/list 평탄화 (JSON-RPC 직렬화 단순) |

## For AI Agents

### Working In This Directory
- **20 도구 추가 시** — `models.py` (Request/Result) + `tools.py` (`tool_*` 함수) + `server.py` (register) + INSTRUCTIONS 문자열 모두 갱신. 회귀 `tests/test_mcp_tools*.py` 도 같이.
- **`extra="forbid"`** — 모든 모델에 적용. unknown field 는 ValidationError 로 즉시 거부 (Claude Code 측 오용 빠르게 노출).
- **write 도구는 `store.write_lock` 필수** — `record_asset_use`, `report_feedback`, `save_search`, `set_project_pin`, `request_rescan`. GUI ↔ stdio 동시 write 충돌 흡수.
- **`request_user_pick`** — pending-pick 패턴 (project memory `project_m5_pending_pick_pattern`). httpx loopback + asyncio.Future + SSE. GUI 가 안 떠 있으면 timeout.
- **`queue=None` 환경** — MCP 단독 실행 (트레이 미기동). `request_rescan` 은 mark_pending 만 하고 OK + warnings 응답.
- **INSTRUCTIONS 문자열** — Claude Code 에 제일 먼저 노출되는 워크플로 가이드. 새 도구 추가 시 여기 step 도 갱신해야 발견 가능.

### Testing Requirements
- 단위: `tests/test_mcp_tools.py` + 마일스톤별 `tests/test_mcp_tools_m{N}.py`.
- 모델: `tests/test_mcp_models.py` — Pydantic 검증.
- subprocess 통합: `tests/test_mcp_integration.py` (`mcp_integration` 마커 옵트인) — 실제 `python -m assetcache --mcp` 기동.

### Common Patterns
- 도구 함수 시그니처: `tool_{name}(deps: ToolDeps, req: {Name}Request) -> {Name}Result`. 동기 함수 (FastMCP 가 async 래핑).
- 에러 응답은 `McpToolError("404_not_found", "...")` raise — server.py 가 JSON-RPC 에러로 변환.
- diversity 옵션 (`none` / `mmr` / `round_robin`) 은 `HybridSearcher` 의 SearchRequest 에 전달.

## Dependencies

### Internal
- `../core/store.py` — DB.
- `../core/search.py` — HybridSearcher.
- `../core/usage_tracker.py` — feedback / 채택 기록.
- `../core/labels.py` — LabelRegistry.
- `../core/label_query.py` — label_query 미니 문법 파서.
- `../core/suggest_packs.py` — suggest_packs 본체.
- `../config.py` + `../logging_setup.py`.

### External
- `mcp>=1.27,<2` (FastMCP).
- pydantic>=2.6.

<!-- MANUAL: 도구 수가 변할 때마다 docs/MCP_USAGE_GUIDE.md + 루트 AGENTS.md / CLAUDE.md 의 "20 도구" 숫자도 같이 갱신. -->
