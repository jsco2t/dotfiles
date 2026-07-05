#!/usr/bin/env python3
"""
Claude Code status line script.
Reads JSON from stdin, writes a compact one-line status to stdout.

Output format:
  <model> | <branch> | ctx:<used>% | 5h:<level>[(<reset>)] | 7d:<level>[(<reset>)] | sb:<on|off>

Rate limit thresholds (applied to both 5-hour and 7-day windows):
  none  = no data (not a subscriber, or before first API response)
  low   = 0–49% used
  med   = 50–79% used
  high  = 80–100% used  → also shows time until reset, e.g. 5h:high(1h23m)

Color: segments that track a limit (context %, 5h window, 7d window) warm
from green -> yellow -> orange -> red as they approach the cap; sandbox-off
shows orange as a heads-up. Set NO_COLOR=1 to disable all coloring.
"""

import json
import os
import subprocess
import sys
import time


SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")

# --- Color -----------------------------------------------------------------
# 256-color SGR codes; widely supported by modern terminals. Honors the
# NO_COLOR convention (https://no-color.org/).
RESET = "\033[0m"
USE_COLOR = os.environ.get("NO_COLOR") is None

C_GREEN = "38;5;34"    # well within limits
C_YELLOW = "38;5;220"  # getting up there
C_ORANGE = "38;5;208"  # close to the limit
C_RED = "38;5;196"     # at / near the cap
C_GRAY = "38;5;244"    # no data / informational
C_MODEL = "38;5;44"    # neutral accent (model)
C_BRANCH = "38;5;141"  # neutral accent (git branch)

# 5-hour level -> color. Warms toward red as usage climbs.
LEVEL_COLOR = {"none": C_GRAY, "low": C_GREEN, "med": C_ORANGE, "high": C_RED}


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


def rate_limit_level(used_pct) -> str:
    """Map a used percentage (0–100) to a display level label."""
    if used_pct is None:
        return "none"
    if used_pct < 50:
        return "low"
    if used_pct < 80:
        return "med"
    return "high"


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


def build_rate_segment(label: str, window) -> str:
    """Build a colored rate-limit segment string for one rate window.

    label  -- display prefix, e.g. '5h' or '7d'
    window -- dict with 'used_percentage' and 'resets_at', or None
    """
    used_pct = window.get("used_percentage") if window else None
    level = rate_limit_level(used_pct)
    color = LEVEL_COLOR.get(level, C_GRAY)
    if level == "high" and window:
        reset_str = format_reset(window.get("resets_at"))
        label_text = f"{label}:{level}({reset_str})" if reset_str else f"{label}:{level}"
    else:
        label_text = f"{label}:{level}"
    return colorize(label_text, color)


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

    # Context window usage — color warms as it fills.
    ctx_pct = data.get("context_window", {}).get("used_percentage")
    if ctx_pct is not None:
        ctx_str = colorize(f"ctx:{ctx_pct:.0f}%", pct_color(ctx_pct))
    else:
        ctx_str = colorize("ctx:--", C_GRAY)

    # Rate limits — 5-hour and 7-day windows.
    rate_limits = data.get("rate_limits") or {}
    five_hour = rate_limits.get("five_hour")
    seven_day = rate_limits.get("seven_day")
    five_str = build_rate_segment("5h", five_hour)
    seven_str = build_rate_segment("7d", seven_day) if seven_day is not None else None

    # Sandbox — on is green (protected); off is orange (heads-up).
    sandbox_on = get_sandbox_enabled()
    sb_str = colorize("sb:on", C_GREEN) if sandbox_on else colorize("sb:off", C_ORANGE)

    # Assemble parts
    parts = [model_str]
    if branch:
        parts.append(branch)
    parts.append(ctx_str)
    parts.append(five_str)
    if seven_str is not None:
        parts.append(seven_str)
    parts.append(sb_str)

    sys.stdout.write(" | ".join(parts) + "\n")


if __name__ == "__main__":
    main()
