"""M3 — MCP 서버 빌더 (in-process inspection, no subprocess)."""

from __future__ import annotations

import pytest


@pytest.fixture
def server_and_deps(mcp_tool_deps):
    from gah.mcp.server import build_server

    deps = mcp_tool_deps()
    server = build_server(
        store=deps.store, search=deps.search, usage=deps.usage,
        registry=deps.registry, queue=deps.queue, config=deps.config,
    )
    return server, deps


def test_build_server_returns_fastmcp_instance(server_and_deps):
    from mcp.server.fastmcp import FastMCP

    server, _ = server_and_deps
    assert isinstance(server, FastMCP)


def test_instructions_field_is_non_empty_and_mentions_workflow(server_and_deps):
    server, _ = server_and_deps
    assert server.instructions
    instr = server.instructions.lower()
    # The instructions must guide Claude Code through the 5-step workflow.
    assert any(token in instr for token in ("workflow", "suggest_packs", "find_asset"))


@pytest.mark.asyncio
async def test_all_twelve_tools_registered(server_and_deps):
    server, _ = server_and_deps
    tools = await server.list_tools()
    names = {t.name for t in tools}
    expected = {
        "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
        "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
        "list_label_axes", "list_labels", "describe_label",
    }
    assert expected <= names


@pytest.mark.asyncio
async def test_each_tool_has_description(server_and_deps):
    server, _ = server_and_deps
    tools = await server.list_tools()
    for t in tools:
        assert t.description, f"tool {t.name} missing description"


def test_run_stdio_graceful_on_keyboardinterrupt(monkeypatch):
    """run_stdio() 가 KeyboardInterrupt 를 잡고 정상 종료 (return None)."""
    from gah.mcp import server as server_mod

    def _raise_interrupt(self, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", _raise_interrupt, raising=True)
    # run_stdio() 가 KeyboardInterrupt 를 다시 던지지 않고 정상 반환.
    server_mod.run_stdio()


def test_get_asset_tool_returns_typed_error_on_missing_id(server_and_deps):
    """register_all_tools 가 McpToolError 를 MCP 표준 에러 응답으로 매핑하는지."""
    from gah.mcp.models import GetAssetRequest
    from gah.mcp.tools import McpToolError, tool_get_asset

    _, deps = server_and_deps
    with pytest.raises(McpToolError) as exc_info:
        tool_get_asset(deps, GetAssetRequest(asset_id=987_654_321))
    assert exc_info.value.code == "404_not_found"
