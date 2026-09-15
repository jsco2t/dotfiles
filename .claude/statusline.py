#!/usr/bin/env python3
"""
Claude Code status line script.
Reads JSON from stdin, writes a compact one-line status to stdout.

Output format:
  <model> | <branch> | ctx <bar> <pct>% | [sess <bar> <pct>% $spent/$cap]
      | [5h ...] | [7d ...] | [spend ...] | sb:<on|off>

Usage bars (context %, the per-session spend bar, and the 5h / 7d / spend
rate-limit windows) render a small fixed-width gauge plus the numeric
percentage, warming from green -> yellow -> orange -> red as they approach the
cap. The gauge fills with `█`, marks the current position with a single
fixed-width `│` tick, and tracks the remainder with `░`. The 5h and 7d windows
always append the time until reset in decimal notation — hours for 5h, days for
7d — e.g. `5h ████│ 88% (4.7h)`, `7d ██│░░ 40% (6.1d)`. (The spend window
appends its reset only near the cap, in the compact m/h/d form.)

The `sess` segment tracks this session's own cost — Claude Code's
`cost.total_cost_usd`, the same number `/usage` prints as "Total cost" — against
a dollar cap that defaults to $50 and is overridable via `session_usd` in
~/.claude/statusline-budget.json. It is a fallback: shown only when neither the
5h nor the 7d utilization window can be determined, since those platform bars
are more accurate and take precedence when present. That makes it the live
budget signal on enterprise / gateway accounts where `rate_limits` is null and
the 5h / 7d windows are unavailable. (It is gated on 5h/7d only, so it can still
appear alongside a `spend` window on an account that populates just that one.)

The rate-limit segments appear only when Claude Code actually provides the data
(`rate_limits.five_hour` / `.seven_day` / `.spend_limit`). On accounts where
`rate_limits` is null — e.g. some enterprise / gateway deployments — the windows
are omitted rather than shown empty, and light up automatically if the data
starts flowing (spend_limit is the one most likely to populate on such accounts).

Color: set NO_COLOR=1 to disable all coloring (https://no-color.org/).
"""

import json
import os
import subprocess
import sys
import time


SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")

# --- Color -----------------------------------------------------------------
# 256-color SGR codes; widely supported by modern terminals.
RESET = "\033[0m"
USE_COLOR = os.environ.get("NO_COLOR") is None

C_GREEN = "38;5;34"    # well within limits
C_YELLOW = "38;5;220"  # getting up there
C_ORANGE = "38;5;208"  # close to the limit
C_RED = "38;5;196"     # at / near the cap
C_GRAY = "38;5;244"    # no data / informational
C_MODEL = "38;5;44"    # neutral accent (model)
C_BRANCH = "38;5;141"  # neutral accent (git branch)


def colorize(text: str, code: str) -> str:
    """Wrap text in an SGR color code, unless coloring is disabled."""
    if not USE_COLOR or not code:
        return text
    return f"\033[{code}m{text}{RESET}"


def pct_color(pct) -> str:
    """Pick a spectrum color for a 0–100 usage percentage."""
    if pct is None:
        return C_GRAY
    if pct < 50:
        return C_GREEN
    if pct < 70:
        return C_YELLOW
    if pct < 85:
        return C_ORANGE
    return C_RED


# --- Progress bar ----------------------------------------------------------
# A compact fixed-width gauge: whole `█` cells show how full the bar is, a
# single thin `│` tick marks the leading edge (current usage), and `░` is the
# unfilled track. The tick is always exactly one character wide, so the marker
# never changes size with the percentage.
BAR_WIDTH = 5
_BAR_FULL = "█"     # filled cell
_BAR_MARK = "│"     # fixed-width leading-edge marker (current position)
_BAR_TRACK = "░"    # unfilled track


def make_bar(pct, width: int = BAR_WIDTH) -> str:
    """Render a width-cell gauge for a 0–100 percentage.

    Whole `█` cells show the filled extent, a single fixed-width `│` tick marks
    the current position at the fill's leading edge, and the remainder is `░`
    track. Values are clamped to [0, 100]; a None percentage yields an empty
    track. At 100% the bar is solid with no tick — the fill has reached the end.
    """
    if pct is None:
        return _BAR_TRACK * width
    p = max(0.0, min(100.0, float(pct)))
    filled = int(p / 100.0 * width)  # whole cells fully filled (floor)
    if filled >= width:
        return _BAR_FULL * width
    return _BAR_FULL * filled + _BAR_MARK + _BAR_TRACK * (width - filled - 1)


def get_git_branch(cwd: str) -> str:
    """Return the current git branch name, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", cwd,
             "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def get_sandbox_enabled() -> bool:
    """Read sandbox.enabled from ~/.claude/settings.json."""
    try:
        with open(SETTINGS_PATH) as f:
            settings = json.load(f)
        return bool(settings.get("sandbox", {}).get("enabled", False))
    except Exception:
        return False


def format_reset(resets_at) -> str:
    """Return a compact relative-time string for a Unix epoch reset timestamp.

    Examples: '45m', '1h', '2h15m', '1d6h', '2d'
    Returns empty string if resets_at is None or already in the past.
    """
    if resets_at is None:
        return ""
    secs = int(resets_at) - int(time.time())
    if secs <= 0:
        return ""
    minutes = secs // 60
    hours = minutes // 60
    days = hours // 24
    remaining_hours = hours % 24
    remaining_mins = minutes % 60
    if days > 0:
        if remaining_hours == 0:
            return f"{days}d"
        return f"{days}d{remaining_hours}h"
    if hours == 0:
        return f"{remaining_mins}m"
    if remaining_mins == 0:
        return f"{hours}h"
    return f"{hours}h{remaining_mins}m"


def format_reset_decimal(resets_at, unit: str) -> str:
    """Reset time in decimal notation for a fixed unit, e.g. '(4.7h)', '(6.1d)'.

    `unit` is 'h' (hours) or 'd' (days). Returns empty string if resets_at is
    None or already in the past. Used by the 5h / 7d windows, which always show
    their reset countdown — hours for 5h, days for 7d — rather than only near the
    cap.
    """
    if resets_at is None:
        return ""
    secs = int(resets_at) - int(time.time())
    if secs <= 0:
        return ""
    if unit == "h":
        return f"({secs / 3600:.1f}h)"
    if unit == "d":
        return f"({secs / 86400:.1f}d)"
    return ""


def build_usage_segment(label: str, pct, reset_str: str = "") -> str:
    """Build a colored `label bar pct%` segment (optionally with a reset time).

    The bar and the numeric percentage share one threshold color, so the glyph
    and the number always agree on how close to the cap the value is.
    """
    text = f"{label} {make_bar(pct)} {pct:.0f}%"
    if reset_str:
        text += f" {reset_str}"
    return colorize(text, pct_color(pct))


def build_rate_segment(label: str, window, reset_unit: str = ""):
    """Colored bar segment for one rate window, or None when data is absent.

    `window` is a dict with 'used_percentage' and 'resets_at', or None. Returns
    None (segment omitted) when the window or its percentage is missing, so a
    null `rate_limits` simply drops these segments instead of showing them
    empty.

    `reset_unit` controls the reset countdown. With 'h' or 'd' (the 5h and 7d
    windows) it is always shown in decimal notation, e.g. `(4.7h)` / `(6.1d)`.
    Left empty (the spend window) the countdown appears only once usage is high
    (>= 80%), in the compact m/h/d form.
    """
    if not window:
        return None
    used_pct = window.get("used_percentage")
    if used_pct is None:
        return None
    if reset_unit:
        reset_str = format_reset_decimal(window.get("resets_at"), reset_unit)
    elif used_pct >= 80:
        reset_str = format_reset(window.get("resets_at"))
    else:
        reset_str = ""
    return build_usage_segment(label, used_pct, reset_str)


# --- Cross-session usage fallback (scaffolding, not currently wired) --------
# Groundwork for one day reconstructing 5h/7d usage from local transcripts when
# the platform sends no `rate_limits` (enterprise/managed accounts). There is no
# statusline_usage.py module today, so build_computed_segment below is unused; it
# is kept as the landing pad for that feature. Such a bar would need a cap the
# platform does not expose, so it would draw only against a user-defined budget,
# otherwise showing the raw value. The per-session spend bar (further down) is
# the shipped, working alternative and needs none of this.
BUDGET_PATH = os.path.expanduser("~/.claude/statusline-budget.json")


def load_budget():
    """Optional user budget: {"unit":"usd"|"tokens","five_hour":N,"seven_day":M}."""
    try:
        with open(BUDGET_PATH, encoding="utf-8") as fh:
            budget = json.load(fh)
        if isinstance(budget, dict) and budget.get("unit") in ("usd", "tokens"):
            return budget
    except (OSError, ValueError):
        pass
    return None


def _human_usd(value) -> str:
    return f"${value / 1000:.1f}k" if value >= 1000 else f"${value:.0f}"


def _human_tokens(value) -> str:
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.0f}k"
    return str(int(value))


def build_computed_segment(label: str, window, budget, budget_key: str) -> str:
    """Fallback segment from transcript-derived usage (stdin had no window).

    With a matching budget -> a threshold-colored bar plus the value; otherwise a
    plain informational value (no invented cap). `window` is one window dict from
    statusline_usage (keys: cost_usd, tokens).
    """
    cost = window.get("cost_usd", 0.0)
    tokens = window.get("tokens", 0)
    if budget and budget.get(budget_key):
        cap = budget[budget_key]
        if budget["unit"] == "usd":
            pct = cost / cap * 100 if cap else 0
            text = f"{label} {make_bar(pct)} {pct:.0f}% ~{_human_usd(cost)}"
        else:
            pct = tokens / cap * 100 if cap else 0
            text = f"{label} {make_bar(pct)} {pct:.0f}% {_human_tokens(tokens)}"
        return colorize(text, pct_color(pct))
    return colorize(f"{label} ~{_human_usd(cost)}", C_MODEL)


# --- Per-session spend bar -------------------------------------------------
# The one live budget signal available on accounts with no `rate_limits` is the
# session's own cost. Claude Code computes it and passes it on stdin as
# cost.total_cost_usd (the number `/usage` prints as "Total cost"), so no pricing
# table is needed. It is drawn as a bar against a dollar cap (default $50).
DEFAULT_SESSION_BUDGET_USD = 50.0


def load_session_budget_usd() -> float:
    """Dollar cap for the session spend bar.

    Reads `session_usd` from statusline-budget.json when present and positive;
    otherwise returns DEFAULT_SESSION_BUDGET_USD so the bar always renders — even
    with no config file at all.
    """
    try:
        with open(BUDGET_PATH, encoding="utf-8") as fh:
            budget = json.load(fh)
        cap = float(budget.get("session_usd", DEFAULT_SESSION_BUDGET_USD))
        if cap > 0:
            return cap
    except (OSError, ValueError, TypeError):
        pass
    return DEFAULT_SESSION_BUDGET_USD


def _spend_usd(value: float) -> str:
    """Compact dollar string: cents below $100, whole dollars or $Nk above."""
    if value >= 1000:
        return f"${value / 1000:.1f}k"
    if float(value).is_integer():
        return f"${value:.0f}"
    return f"${value:.2f}"


def build_spend_segment(cost_usd: float, cap_usd: float) -> str:
    """`sess <bar> <pct>% $spent/$cap`, sharing one threshold color.

    The bar is clamped to the cap, but the percentage is truthful: $60 against a
    $50 cap reads `120%` with a full red bar rather than looking capped.
    """
    pct = (cost_usd / cap_usd * 100.0) if cap_usd else 0.0
    text = (
        f"sess {make_bar(pct)} {pct:.0f}% "
        f"{_spend_usd(cost_usd)}/{_spend_usd(cap_usd)}"
    )
    return colorize(text, pct_color(pct))


def shorten_model(display_name: str) -> str:
    """Trim verbose model display names to something compact."""
    # "Claude Sonnet 4.6" -> "sonnet-4.6"
    # "Claude Opus 4"     -> "opus-4"
    # "Claude Haiku 3.5"  -> "haiku-3.5"
    name = display_name.lower()
    for prefix in ("claude ", "claude-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    # Replace spaces with dashes for readability
    return name.replace(" ", "-")


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.stdout.write("(status: bad input)\n")
        return

    # Model
    model_display = data.get("model", {}).get("display_name", "")
    model_str = shorten_model(model_display) if model_display else "unknown"
    model_str = colorize(model_str, C_MODEL)

    # Git branch (use cwd from JSON)
    cwd = data.get("cwd") or data.get("workspace", {}).get("current_dir", "")
    branch = get_git_branch(cwd) if cwd else ""
    if branch:
        branch = colorize(branch, C_BRANCH)

    # Context window usage — a progress bar warming as it fills.
    ctx_pct = (data.get("context_window") or {}).get("used_percentage")
    if ctx_pct is not None:
        ctx_str = build_usage_segment("ctx", ctx_pct)
    else:
        ctx_str = colorize("ctx --", C_GRAY)

    # Per-session spend against a dollar cap (default $50). Sourced from Claude
    # Code's own session cost on stdin. Gate on key presence, not truthiness:
    # $0.00 at session start is legitimate data, not a missing field.
    spend_seg = None
    if "cost" in data:
        cost_usd = (data.get("cost") or {}).get("total_cost_usd")
        if cost_usd is not None:
            spend_seg = build_spend_segment(
                float(cost_usd), load_session_budget_usd()
            )

    # Rate limits — 5-hour, 7-day, and spend windows; each shown only when
    # present. On enterprise/gateway accounts spend_limit is the window most
    # likely to be populated, so it is read here too (see build_rate_segment).
    rate_limits = data.get("rate_limits") or {}
    five_str = build_rate_segment("5h", rate_limits.get("five_hour"), "h")
    seven_str = build_rate_segment("7d", rate_limits.get("seven_day"), "d")
    spend_str = build_rate_segment("spend", rate_limits.get("spend_limit"))

    # Sandbox — on is green (protected); off is orange (heads-up).
    sandbox_on = get_sandbox_enabled()
    sb_str = colorize("sb:on", C_GREEN) if sandbox_on else colorize("sb:off", C_ORANGE)

    # Assemble parts
    parts = [model_str]
    if branch:
        parts.append(branch)
    parts.append(ctx_str)
    # The `sess` spend bar is a fallback: show it only when neither the 5h nor
    # the 7d window could be determined. Gate on the built segment strings (None
    # when the window is absent or its percentage is null), not on `rate_limits`.
    if spend_seg is not None and five_str is None and seven_str is None:
        parts.append(spend_seg)
    if five_str is not None:
        parts.append(five_str)
    if seven_str is not None:
        parts.append(seven_str)
    if spend_str is not None:
        parts.append(spend_str)
    parts.append(sb_str)

    sys.stdout.write(" | ".join(parts) + "\n")


if __name__ == "__main__":
    main()
