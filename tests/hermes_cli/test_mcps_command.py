"""Tests for the CLI ``/mcps`` command (custom fork addition, not upstream).

``/mcps`` renders the cached per-server MCP status (``tools.mcp_tool_discovery.get_mcp_status``)
as a Rich panel/table matching the rest of the CLI's chrome (rounded ``╭─ ... ─╮`` boxes):
green ``connected``, red ``failed`` (with the error line), yellow ``connecting``, dim
``disabled``/``configured``. It never connects to a server itself.
"""

import io
from contextlib import redirect_stdout

from hermes_cli.cli_mcps_mixin import CLIMcpsMixin
from hermes_cli.commands import resolve_command


class _Stub(CLIMcpsMixin):
    pass


def _run(monkeypatch, entries, *, discovery_calls=None):
    monkeypatch.setattr(
        "tools.mcp_tool_discovery.get_mcp_status", lambda *a, **kw: entries
    )
    if discovery_calls is not None:
        monkeypatch.setattr(
            "hermes_cli.mcp_startup.start_background_mcp_discovery",
            lambda **kw: discovery_calls.append("start"),
        )
        monkeypatch.setattr(
            "hermes_cli.mcp_startup.wait_for_mcp_discovery",
            lambda *a, **kw: discovery_calls.append("wait"),
        )
    buf = io.StringIO()
    with redirect_stdout(buf):
        _Stub()._handle_mcps_command()
    return buf.getvalue()


def test_mcps_command_is_registered_cli_only():
    cmd = resolve_command("mcps")
    assert cmd is not None
    assert cmd.name == "mcps"
    assert cmd.cli_only is True


def test_mcps_accepts_the_raw_command_text_like_the_cli_dispatcher(monkeypatch):
    """cli.py's ``_slash_handler`` fallback (no ``_SLASH_DISPATCH`` entry) always calls
    ``handler(cmd_original)``. A handler that only accepts ``self`` raises TypeError and the
    CLI silently swallows it, looking like the command did nothing."""
    monkeypatch.setattr("tools.mcp_tool_discovery.get_mcp_status", lambda *a, **kw: [])
    buf = io.StringIO()
    with redirect_stdout(buf):
        _Stub()._handle_mcps_command("/mcps")
    assert "No MCP servers configured" in buf.getvalue()


def test_mcps_no_servers_configured_shows_hint(monkeypatch):
    out = _run(monkeypatch, [])
    assert "No MCP servers configured" in out
    assert "hermes mcp add" in out
    assert "MCP Servers" in out  # panel title


def test_mcps_lists_every_server_with_status(monkeypatch):
    entries = [
        {"name": "context7", "transport": "http", "tools": 12,
         "connected": True, "disabled": False, "status": "connected"},
        {"name": "sqlserver-local", "transport": "stdio", "tools": 0,
         "connected": False, "disabled": False, "status": "failed",
         "error": "connection refused"},
        {"name": "disabled-one", "transport": "http", "tools": 0,
         "connected": False, "disabled": True, "status": "disabled"},
    ]
    out = _run(monkeypatch, entries)
    for name in ("context7", "sqlserver-local", "disabled-one"):
        assert name in out
    assert "connected" in out
    assert "failed" in out
    assert "disabled" in out
    # The failure reason is surfaced, not swallowed.
    assert "connection refused" in out


def test_mcps_long_name_is_truncated_not_left_to_break_layout(monkeypatch):
    """A very long server id must not blow out the panel width (Rich table ellipsis)."""
    entries = [
        {"name": "aws-seglabs-cloudwatch-desenvolvimento-mcp", "transport": "stdio",
         "tools": 0, "connected": False, "disabled": False, "status": "configured"},
    ]
    out = _run(monkeypatch, entries)
    # The full un-truncated name never appears verbatim in the rendered output.
    assert "aws-seglabs-cloudwatch-desenvolvimento-mcp" not in out
    assert "aws-seglabs" in out


def test_mcps_forces_discovery_before_reading_status(monkeypatch):
    """/mcps is often the first thing typed after opening the CLI, before any turn ran
    ensure_mcp_discovery_before_agent_build() -- without an explicit kick every server would
    still read as the never-attempted "configured" placeholder instead of its real state."""
    calls = []
    _run(monkeypatch, [], discovery_calls=calls)
    assert calls == ["start", "wait"]
