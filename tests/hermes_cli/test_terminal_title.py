"""Tests for the CLI's terminal tab/window title feedback (custom fork addition, not
upstream). Mirrors the ui-tui frontend's marker scheme: 🫡 waiting on the user (approval /
clarify / sudo / secret / slash-confirm), 🧠 running a tool, 🧐 reasoning, 🍌 fresh session
(no turn has completed yet), ✅ idle after the model finished responding, plus the session
name (when one is set) -- so several open Hermes tabs are distinguishable at a glance.
"""

import time

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
    _last_turn_finished_at = None
    session_id = "abc123"

    def _get_status_bar_session_title(self):
        return ""


class _Named(_Stub):
    def _get_status_bar_session_title(self):
        return "Encontrar GitHub do projeto"


class _NamedDone(_Named):
    """A turn has already completed at least once (mirrors real sessions after turn #1)."""

    _last_turn_finished_at = time.time() - 10


def _capture(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(title_mod, "_set_terminal_title", calls.append)
    return calls


def test_fresh_session_marker_with_no_session_name_omits_the_separator(monkeypatch):
    """No explicit/auto-derived title yet, and no turn has completed: just the fresh-session
    marker + 'Hermes', no bare session id."""
    calls = _capture(monkeypatch)
    _Stub()._update_terminal_title()
    assert calls == ["🍌 Hermes"]


def test_busy_marker_is_brain(monkeypatch):
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._agent_running = True
    stub._update_terminal_title()
    assert calls == ["🧠 Hermes · Encontrar GitHub do projeto"]


def test_awaiting_input_marker_outranks_busy(monkeypatch):
    """A blocking overlay (approval here) means the turn is paused on the user, which must
    win over "busy" even if the agent is still technically running."""
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._agent_running = True
    stub._approval_state = {"response_queue": object()}
    stub._update_terminal_title()
    assert calls == ["🫡 Hermes · Encontrar GitHub do projeto"]


def test_fresh_session_marker_is_shown_before_any_turn_completes(monkeypatch):
    calls = _capture(monkeypatch)
    _Named()._update_terminal_title()
    assert calls == ["🍌 Hermes · Encontrar GitHub do projeto"]


def test_done_marker_is_shown_after_a_turn_has_completed(monkeypatch):
    """Once `_last_turn_finished_at` is set (a turn has finished at least once), idle shows
    the done marker instead of the fresh-session one, even later in the same idle stretch."""
    calls = _capture(monkeypatch)
    _NamedDone()._update_terminal_title()
    assert calls == ["✅ Hermes · Encontrar GitHub do projeto"]


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
    assert calls == ["🍌 Hermes · Encontrar GitHub do projeto"]


def test_state_change_after_no_op_still_updates(monkeypatch):
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._update_terminal_title()
    stub._agent_running = True
    stub._update_terminal_title()
    assert calls == ["🍌 Hermes · Encontrar GitHub do projeto", "🧠 Hermes · Encontrar GitHub do projeto"]


def test_state_change_from_fresh_to_done_after_first_turn_completes(monkeypatch):
    """Same stub instance: idle before any turn (🍌), busy during it (🧠), then done (✅) once
    `_last_turn_finished_at` gets set at turn end -- the marker must flip even though
    `awaiting_input`/`busy`/`reasoning` are all back to their idle values in both idle calls."""
    calls = _capture(monkeypatch)
    stub = _Named()
    stub._update_terminal_title()
    stub._agent_running = True
    stub._update_terminal_title()
    stub._agent_running = False
    stub._last_turn_finished_at = time.time()
    stub._update_terminal_title()
    assert calls == [
        "🍌 Hermes · Encontrar GitHub do projeto",
        "🧠 Hermes · Encontrar GitHub do projeto",
        "✅ Hermes · Encontrar GitHub do projeto",
    ]


def test_set_terminal_title_is_a_noop_when_stdout_is_not_a_tty(monkeypatch):
    """Redirected stdout (tests, CI, `| tee log`) must never raise or print garbage."""
    import io

    monkeypatch.setattr(title_mod.sys, "__stdout__", io.StringIO())
    title_mod._set_terminal_title("✅ Hermes")  # must not raise
