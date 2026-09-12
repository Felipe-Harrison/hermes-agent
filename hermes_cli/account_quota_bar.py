"""Compact provider-quota bar for the CLI status bar (fork addition, not upstream).

Kept in its own module for the same reason as ``cli_mcps_mixin.py``: an isolated file survives
upstream refactors of ``cli_status_bar_mixin.py`` / ``cli.py`` with zero merge friction.

Renders the FIRST window of ``agent.account_usage.fetch_account_usage()`` (Anthropic's "Current
session" 5h window, Codex's "Session" window, OpenRouter's "API key quota") as a short bar:

    ◉ ████████░░ 76%  ·  resets 18:20

The fetch hits a real provider endpoint (Anthropic OAuth /usage, Codex /usage, OpenRouter
/credits), so it NEVER runs on the status-bar repaint path (every keystroke repaints). Instead a
background daemon thread refreshes a process-local cache once per completed turn
(``schedule_quota_bar_refresh``, called from ``cli.py::_tui_after_turn``); the status bar only
ever reads the cached label + percent (``cached_quota_bar``), which is empty until the first
refresh completes.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

_BAR_WIDTH = 10
_REFRESH_TIMEOUT_SECONDS = 15.0

# Per-agent-identity cache: (provider, base_url) -> (label, used_percent). Keyed by route so a
# mid-session model/provider switch doesn't show a stale bar from the previous provider.
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[str, float]] = {}
_refresh_in_flight: set[tuple[str, str]] = set()


def _bar_glyphs(used_percent: float, width: int = _BAR_WIDTH) -> str:
    """Short filled/empty block bar: ``████████░░`` (no partial-cell glyph — 10 cells is coarse
    enough that rounding to the nearest full cell reads cleanly)."""
    pct = max(0.0, min(100.0, used_percent))
    filled = round(pct / 100.0 * width)
    return "█" * filled + "░" * (width - filled)


def _format_reset_short(dt) -> str:
    """``18:20`` — 24h local clock, no timezone name (status bar has no room for it)."""
    try:
        from hermes_time import get_timezone
        tz = get_timezone()
    except Exception:
        tz = None
    local = dt.astimezone(tz) if tz is not None else dt.astimezone()
    return local.strftime("%H:%M")


def format_quota_bar_segment(window) -> str:
    """One ``AccountUsageWindow`` -> ``◉ ████████░░ 76%  ·  resets 18:20`` (no reset suffix when
    the window carries none)."""
    used = float(window.used_percent)
    bar = f"◉ {_bar_glyphs(used)} {max(0, round(used))}%"
    return f"{bar}  ·  ↻ {_format_reset_short(window.reset_at)}" if window.reset_at else bar


def _route_key(provider: str, base_url: Optional[str]) -> tuple[str, str]:
    return (provider, base_url or "")


def cached_quota_bar(provider: str, base_url: Optional[str]) -> tuple[str, Optional[float]]:
    """Cached ``(label, used_percent)`` for the given route, or ``("", None)`` before the first
    successful refresh. ``used_percent`` drives the caller's threshold-based color."""
    if not provider:
        return "", None
    with _cache_lock:
        return _cache.get(_route_key(provider, base_url), ("", None))


def _refresh_worker(
    provider: str, base_url: Optional[str], api_key: Optional[str], on_update: Optional[Callable[[], None]],
) -> None:
    key = _route_key(provider, base_url)
    try:
        from agent.account_usage import fetch_account_usage

        snapshot = fetch_account_usage(provider, base_url=base_url, api_key=api_key)
        window = next((w for w in (snapshot.windows if snapshot else ()) if w.used_percent is not None), None)
        label = format_quota_bar_segment(window) if window is not None else ""
        used_percent = float(window.used_percent) if window is not None else None
    except Exception:
        label = ""
        used_percent = None
    with _cache_lock:
        if label:
            _cache[key] = (label, used_percent)
        _refresh_in_flight.discard(key)
    # The idle prompt is never repainted on a timer (cli_tui_mixin.py's process loop comment);
    # input/agent events invalidate explicitly. A background fetch finishing several seconds
    # after the turn already returned is exactly such an event — without this call the label
    # sits correctly in cache but the status bar never redraws to show it until the NEXT
    # keystroke or turn.
    if label and on_update is not None:
        try:
            on_update()
        except Exception:
            pass


def schedule_quota_bar_refresh(
    provider: str, base_url: Optional[str], api_key: Optional[str], *, on_update: Optional[Callable[[], None]] = None,
) -> None:
    """Fire a background refresh for this route, unless one is already in flight. Never blocks
    and never raises — a stuck/slow provider endpoint just leaves the cache at its last value.
    ``on_update`` (typically ``self._app.invalidate``) is called once the fetch succeeds, so the
    status bar redraws even if no other event triggers a repaint in the meantime."""
    if not provider:
        return
    key = _route_key(provider, base_url)
    with _cache_lock:
        if key in _refresh_in_flight:
            return
        _refresh_in_flight.add(key)
    thread = threading.Thread(
        target=_refresh_worker, args=(provider, base_url, api_key, on_update), name="quota-bar-refresh", daemon=True,
    )
    thread.start()


def reset_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
        _refresh_in_flight.clear()
