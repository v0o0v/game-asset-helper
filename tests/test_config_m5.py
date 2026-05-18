"""Tests for M5 Config fields and UsageSource enum.

M5 features:
- 7 web GUI configuration fields (host, port, timeouts, browser behavior)
- UsageSource enum for record_asset_use source tracking
"""

import pytest
from gah.config import Config, UsageSource


def test_default_web_host():
    c = Config()
    assert c.web_host == "127.0.0.1"


def test_default_web_port():
    c = Config()
    assert c.web_port == 9874


def test_default_web_port_max_attempts():
    c = Config()
    assert c.web_port_max_attempts == 10


def test_default_claude_pick_timeout():
    c = Config()
    assert c.claude_pick_timeout_seconds == 300


def test_default_claude_pick_max_pending():
    c = Config()
    assert c.claude_pick_max_pending == 20


def test_default_web_open_browser_on_start():
    c = Config()
    assert c.web_open_browser_on_start is True


def test_default_web_log_requests():
    c = Config()
    assert c.web_log_requests is False


def test_usage_source_enum_values():
    assert UsageSource.MANUAL.value == "manual"
    assert UsageSource.MCP.value == "mcp"
    assert UsageSource.CLAUDE_PICK.value == "claude_pick"
