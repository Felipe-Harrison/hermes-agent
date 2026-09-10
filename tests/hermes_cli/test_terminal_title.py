"""Tests for the CLI's terminal tab/window title feedback (custom fork addition, not
upstream). Mirrors the ui-tui frontend's marker scheme: ⚠ waiting on the user (approval /
clarify / sudo / secret / slash-confirm), ⏳ busy (running or reasoning), ✓ idle, plus the
session name (when one is set) -- so several open Hermes tabs are distinguishable at a glance.
"""

import hermes_cli.cli_terminal_title_mixin as title_mod
from hermes_cli.cli_terminal_title_mixin import CLITerminalTitleMixin


class _Stub(CLITerminalTitleMixin):
    _agent_running = False
    _pet_reasoning = False
    _approval_state = None
    _clarify_state = None
    _sudo_state = None
    _secret_state = None
    _slash_confirm_state = None
    session_id = "abc123"

    def _get_status_bar_session_title(self):
        return ""


class _Named(_Stub):
    def _get_status_bar_session_title(self):
        return "Encontrar GitHub do projeto"


def _capture(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(title_mod, "_set_terminal_title", calls.append)
    return calls


def test_idle_marker_with_no_session_name_omits_the_separator(monkeypatch):
    """No explicit/auto-derived title yet: just the marker + 'Hermes', no bare session id."""
    calls = _capture(monkeypatch)
    _Stub()._update_terminal_title()
    assert calls == ["✓ Hermes"]


def test_busy_marker_is_hourglass(monkeypatch):
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._agent_running = True
    stub._update_terminal_title()
    assert calls == ["⏳ Hermes · Encontrar GitHub do projeto"]


def test_awaiting_input_marker_outranks_busy(monkeypatch):
    """A blocking overlay (approval here) means the turn is paused on the user, which must
    win over "busy" even if the agent is still technically running."""
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._agent_running = True
    stub._approval_state = {"response_queue": object()}
    stub._update_terminal_title()
    assert calls == ["⚠ Hermes · Encontrar GitHub do projeto"]


def test_session_title_is_shown_when_present(monkeypatch):
    calls = _capture(monkeypatch)
    _Named()._update_terminal_title()
    assert calls == ["✓ Hermes · Encontrar GitHub do projeto"]


def test_long_session_name_is_truncated(monkeypatch):
    calls = _capture(monkeypatch)

    class LongNamed(_Stub):
        def _get_status_bar_session_title(self):
            return "x" * 80

    LongNamed()._update_terminal_title()
    assert len(calls) == 1
    # marker + " Hermes · " prefix + at most _MAX_TITLE_SESSION_LEN chars of name.
    rendered_name = calls[0].split("· ", 1)[1]
    assert len(rendered_name) <= title_mod._MAX_TITLE_SESSION_LEN
    assert rendered_name.endswith("…")


def test_unchanged_state_does_not_rewrite_the_title(monkeypatch):
    """The spinner loop polls every ~0.1-0.2s; without dedup that would hammer the terminal
    with the same OSC sequence dozens of times a second while idle."""
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._update_terminal_title()
    stub._update_terminal_title()
    stub._update_terminal_title()
    assert calls == ["✓ Hermes · Encontrar GitHub do projeto"]


def test_state_change_after_no_op_still_updates(monkeypatch):
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._update_terminal_title()
    stub._agent_running = True
    stub._update_terminal_title()
    assert calls == ["✓ Hermes · Encontrar GitHub do projeto", "⏳ Hermes · Encontrar GitHub do projeto"]


def test_set_terminal_title_is_a_noop_when_stdout_is_not_a_tty(monkeypatch):
    """Redirected stdout (tests, CI, `| tee log`) must never raise or print garbage."""
    import io

    monkeypatch.setattr(title_mod.sys, "__stdout__", io.StringIO())
    title_mod._set_terminal_title("✓ Hermes")  # must not raise
