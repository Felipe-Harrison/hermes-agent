"""Terminal tab/window title feedback for the interactive CLI (custom fork addition, not
upstream). Mirrors the ui-tui frontend's title scheme (see
ui-tui/packages/hermes-ink/src/ink/hooks/use-terminal-title.ts): a status marker plus the
session name, so a user with several Hermes tabs open can tell at a glance which ones are
still working and which are waiting on them.

Kept in its own module so future upstream refactors of cli.py/cli_status_bar_mixin.py never
touch this file, minimizing merge conflicts against NousResearch/hermes-agent.
"""

from __future__ import annotations

import sys

from agent.pet.constants import PetState

# PetState -> title marker. Mirrors ui-tui's `marker` (approval/sudo/secret/clarify -> "⚠",
# busy -> "⏳", else "✓"); WAITING is the only state that maps to the overlay marker, every
# other "the turn is doing something" state reads as busy.
_TITLE_MARKER_BY_STATE = {
    PetState.WAITING: "⚠",
    PetState.RUN: "⏳",
    PetState.REVIEW: "⏳",
}
_DEFAULT_MARKER = "✓"

_MAX_TITLE_SESSION_LEN = 40


def _set_terminal_title(title: str) -> None:
    """Emit OSC 0 (set tab + window title). Silently a no-op on terminals that don't
    understand OSC sequences (classic conhost) or when stdout isn't a real console.

    Written directly to the real stdout, bypassing prompt_toolkit/_cprint: a title update is
    not scrollback content and must never appear as printed text or get recorded in output
    history.
    """
    try:
        stream = sys.__stdout__
        if stream is None or not stream.isatty():
            return
        stream.write(f"\x1b]0;{title}\x07")
        stream.flush()
    except Exception:
        pass


class CLITerminalTitleMixin:
    """Provides `HermesCLI._update_terminal_title`, polled from the TUI's existing spinner
    loop (``_tui_spinner_loop``) and called explicitly at the start/end of a turn."""

    _terminal_title_last_state = None  # dedup key so idle polling doesn't rewrite every tick

    def _update_terminal_title(self) -> None:
        """Refresh the terminal tab/window title if the derived state changed since the last
        call: `<marker> Hermes · <session name>`, or `<marker> Hermes` when no name is set.

        Marker: ⚠ waiting on approval/sudo/secret/clarify/slash-confirm, ⏳ busy (running or
        reviewing), ✓ idle. Session name: the current session title (explicit /title, else the
        auto-derived one already shown in the status bar); omitted entirely when neither is set.
        """
        try:
            from agent.pet.state import derive_pet_state

            awaiting_input = bool(
                getattr(self, "_approval_state", None)
                or getattr(self, "_clarify_state", None)
                or getattr(self, "_sudo_state", None)
                or getattr(self, "_secret_state", None)
                or getattr(self, "_slash_confirm_state", None)
            )
            busy = getattr(self, "_agent_running", False)
            reasoning = getattr(self, "_pet_reasoning", False)

            name = ""
            get_title = getattr(self, "_get_status_bar_session_title", None)
            if callable(get_title):
                name = str(get_title() or "").strip()
            if len(name) > _MAX_TITLE_SESSION_LEN:
                name = name[: _MAX_TITLE_SESSION_LEN - 1] + "…"

            state_key = (awaiting_input, busy, reasoning, name)
            if state_key == self._terminal_title_last_state:
                return
            self._terminal_title_last_state = state_key

            state = derive_pet_state(awaiting_input=awaiting_input, busy=busy, reasoning=reasoning)
            marker = _TITLE_MARKER_BY_STATE.get(state, _DEFAULT_MARKER)
            title = f"{marker} Hermes · {name}" if name else f"{marker} Hermes"
            _set_terminal_title(title)
        except Exception:
            pass
