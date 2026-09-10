"""CLI slash-command handler for /mcps (custom fork addition, not upstream).

Kept in its own module so future upstream refactors of hermes_cli/cli_info_mixin.py
never touch this file, minimizing merge conflicts against NousResearch/hermes-agent.
"""

from __future__ import annotations

from rich import box as rich_box
from rich.table import Table

# status -> (icon, Rich style name); anything unmapped renders uncolored.
_STATUS_STYLE = {
    "connected": ("✓", "green"), "failed": ("✗", "red"),
    "connecting": ("…", "yellow"), "disabled": ("○", "dim"),
    "configured": ("○", "dim"),
}

# Longest a server name renders before truncation, so one long name (e.g. a verbose
# aws-* server id) can't blow out the whole panel's width.
_MAX_NAME_WIDTH = 32


class CLIMcpsMixin:
    """Provides `HermesCLI._handle_mcps_command` (the /mcps slash command)."""

    def _handle_mcps_command(self, cmd_original: str = ""):
        """Show status of every configured MCP server: name, transport, tool count, and
        connection status (connected / disabled / connecting / failed / configured), in a
        panel matching the rest of the CLI's chrome (``╭─ ⚕ Hermes ─╮`` style boxes).

        Takes no arguments; ``cmd_original`` is accepted (and ignored) because the CLI's
        dispatch fallback for commands without an explicit ``_SLASH_DISPATCH`` entry always
        passes the raw command text.
        """
        from cli import ChatConsole
        from rich.panel import Panel
        from hermes_cli.mcp_startup import start_background_mcp_discovery, wait_for_mcp_discovery
        from tools.mcp_tool_discovery import get_mcp_status

        # /mcps is often the very first thing typed after opening the CLI, before any turn ran
        # ensure_mcp_discovery_before_agent_build() -- without this, every server would still read
        # as the "never attempted yet" configured placeholder instead of its real connection state.
        # Idempotent: a no-op if discovery already started/finished.
        import logging
        start_background_mcp_discovery(logger=logging.getLogger("cli"), thread_name="cli-mcps-command-discovery")
        wait_for_mcp_discovery(timeout=10.0)

        entries = get_mcp_status()
        width = self._scrollback_box_width() if hasattr(self, "_scrollback_box_width") else 80

        if not entries:
            body = (
                "No MCP servers configured.\n\n"
                "Add one with:\n"
                "  hermes mcp add <name> --url <endpoint>\n"
                "  hermes mcp add <name> --command <cmd> --args <args...>"
            )
            ChatConsole().print(Panel(body, title="[bold]⚕ MCP Servers[/]", title_align="left",
                                       border_style="cyan", width=width))
            return

        table = Table(box=rich_box.MINIMAL, show_edge=False, pad_edge=False)
        table.add_column("Name", overflow="ellipsis", no_wrap=True, max_width=_MAX_NAME_WIDTH)
        table.add_column("Transport", no_wrap=True)
        table.add_column("Tools", justify="right", no_wrap=True)
        table.add_column("Status", no_wrap=True, max_width=45)

        for entry in entries:
            icon, style = _STATUS_STYLE.get(entry["status"], ("?", ""))
            status_cell = f"[{style}]{icon} {entry['status']}[/]" if style else f"{icon} {entry['status']}"
            if entry["status"] == "failed" and entry.get("error"):
                status_cell += f"\n[dim red]{entry['error']}[/]"
            table.add_row(entry["name"], entry["transport"], str(entry["tools"]), status_cell)

        ChatConsole().print(Panel(table, title="[bold]⚕ MCP Servers[/]", title_align="left",
                                   border_style="cyan", width=width))
