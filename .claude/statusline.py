#!/usr/bin/env python3
"""
Claude Code status line script.
Reads JSON from stdin, writes a compact one-line status to stdout.

Output format:
  <model> | <branch> | ctx <bar> <pct>%
      | <account-usage | sess> | [<overage>] | sb:<on|off>

Usage bars (context %, the 5h / 7d / spend windows, and the API-mode sess bar)
render a small fixed-width gauge plus the numeric percentage, warming from
green -> yellow -> orange -> red as they approach the cap. The gauge fills with
`█`, marks the current position with a single fixed-width `│` tick, and tracks
the remainder with `░`. The 5h and 7d windows always append the time until
reset in decimal notation — hours for 5h, days for 7d — e.g.
`5h ████│ 88% (4.7h)`, `7d ██│░░ 40% (6.1d)`.

Billing mode decides the middle segment(s):

* Subscription (the DEFAULT whenever you are logged in to a Claude account):
  show account utilization — the 5h / 7d windows Claude Code reports. This is
  your claude.ai plan usage, never a dollar figure. Until a window is known
  (the very first launch, or just after a window resets) a neutral `usage --`
  placeholder is shown instead of dollars.

* API billing: show `sess <bar> <pct>% $spent/$cap` — this session's own cost
  (Claude Code's `cost.total_cost_usd`, the number `/usage` prints as "Total
  cost") against a dollar cap (default $50, override with `session_usd`). This
  is the right signal only when you are actually billed per API call.

Why the split: the 5h / 7d windows are "absent until the first response
carrying the rate-limit headers is observed, and always absent for API-key,
Bedrock, and Vertex sessions" (Claude Code's own schema). The old script keyed
the dollar bar on that absence, so every launch flashed `sess $X/$50` for a
moment before the account bars arrived. Billing mode is now decided up front
from your login (oauthAccount in ~/.claude.json) plus the Bedrock/Vertex env
vars, so the dollar bar appears only under genuine API billing.

Remaining launch flicker is removed by caching the last-seen 5h / 7d windows in
~/.claude/statusline-cache.json: the next launch renders the bars immediately
from cache instead of the placeholder, and each cached window is dropped once
its `resets_at` passes. The account/billing verdict is cached in the same file,
keyed on ~/.claude.json's mtime+size, so that file is parsed only when it
changes.

Overage indicator (hidden unless triggered): flags that you have gone into
overage / extra-usage billing. It lights up when a gateway `spend_limit` window
exceeds 100% (definitive), or — as a proxy for plan accounts — when a 5h / 7d
window reaches the threshold (default 99%, the point Claude Code itself treats
as the max_5x limit) AND your account has extra usage enabled
(oauthAccount.hasExtraUsageEnabled). Note: Claude Code does not put
real-time overage state in the status-line payload for non-gateway accounts (it
lives behind the anthropic-ratelimit-unified-overage-status header), so the
plan-account form is an inference, not ground truth.

Config — all optional, in ~/.claude/statusline-budget.json:
  session_usd        dollar cap for the API-mode sess bar (default 50)
  billing_mode       "auto" (default) | "subscription" | "api" — force the mode
  overage_indicator  true (default) | false — enable/disable the indicator
  overage_threshold  window percent that trips the proxy (default 99)
  overage_label      text of the indicator (default "⚠ overage")

Color: set NO_COLOR=1 to disable all coloring (https://no-color.org/).
"""

import json
import os
import subprocess
import sys
import time


SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")
CLAUDE_JSON_PATH = os.path.expanduser("~/.claude.json")
CACHE_PATH = os.path.expanduser("~/.claude/statusline-cache.json")

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


def session_budget_usd(config: dict) -> float:
    """Dollar cap for the API-mode session spend bar.

    Uses `session_usd` from statusline-budget.json when present and positive;
    otherwise DEFAULT_SESSION_BUDGET_USD so the bar always renders.
    """
    try:
        cap = float(config.get("session_usd", DEFAULT_SESSION_BUDGET_USD))
        if cap > 0:
            return cap
    except (TypeError, ValueError):
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


# --- Billing mode, account facts, and the sidecar cache --------------------
# Billing mode is decided up front (not from whether `rate_limits` happens to be
# present this render), so the dollar `sess` bar can never flash during the gap
# before the first API response populates the account windows. The account facts
# and the last-seen windows are cached in CACHE_PATH; see the module docstring.
_WINDOW_NAMES = ("five_hour", "seven_day", "spend_limit")


def _read_json(path: str) -> dict:
    """Load a small JSON object, or {} on any error / non-object."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(cache: dict) -> None:
    """Persist the sidecar cache atomically; failures are non-fatal."""
    tmp = f"{CACHE_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _env_truthy(name: str) -> bool:
    """True when an env var is set to something other than a false-y token."""
    val = os.environ.get(name)
    return val is not None and val.strip().lower() not in ("", "0", "false", "no", "off")


def _parse_account() -> dict:
    """Read oauthAccount facts from ~/.claude.json. {} keys default when absent."""
    src = _read_json(CLAUDE_JSON_PATH)
    oauth = src.get("oauthAccount")
    if isinstance(oauth, dict) and oauth.get("accountUuid"):
        return {
            "has_oauth": True,
            "billing_type": oauth.get("billingType"),
            "has_extra_usage": bool(oauth.get("hasExtraUsageEnabled")),
        }
    return {"has_oauth": False, "billing_type": None, "has_extra_usage": False}


def get_account(cache: dict):
    """Account facts, cached against ~/.claude.json's mtime+size.

    Returns (account_dict, dirty). ~/.claude.json is parsed only when its
    mtime/size changes, so the status line does not re-read it every render.
    """
    acc = cache.get("account") or {}
    try:
        st = os.stat(CLAUDE_JSON_PATH)
        sig = [st.st_mtime, st.st_size]
    except OSError:
        sig = None
    if sig is not None and acc.get("sig") == sig and "has_oauth" in acc:
        return acc, False
    fresh = _parse_account()
    fresh["sig"] = sig
    cache["account"] = fresh
    return fresh, True


def resolve_billing_mode(account: dict, config: dict) -> str:
    """"subscription" or "api", decided before any window data is consulted.

    Order: explicit `billing_mode` override -> Bedrock/Vertex env (real API
    billing) -> presence of a logged-in oauthAccount -> API. A bare
    ANTHROPIC_API_KEY deliberately does NOT flip the verdict: it is commonly
    exported for SDK scripts while Claude Code still runs on a subscription, and
    keying on it would reintroduce the very flicker this is meant to remove.
    """
    override = str(config.get("billing_mode", "auto")).lower()
    if override in ("subscription", "api"):
        return override
    if _env_truthy("CLAUDE_CODE_USE_BEDROCK") or _env_truthy("CLAUDE_CODE_USE_VERTEX"):
        return "api"
    return "subscription" if account.get("has_oauth") else "api"


def _window_fresh(entry: dict, now: int) -> bool:
    """A cached window is usable until its reset moment passes."""
    resets_at = entry.get("resets_at")
    if resets_at is None:
        return True
    try:
        return now < int(resets_at)
    except (TypeError, ValueError):
        return True


def resolve_windows(rate_limits: dict, cache: dict, now: int):
    """Merge live stdin windows over the last-seen cache.

    Live windows win and refresh the cache; windows missing from stdin fall back
    to the cached value until their `resets_at` passes (then they are dropped).
    This is what lets the bars render immediately on the next launch instead of
    flashing a placeholder while the first API response is in flight. Returns
    (windows_dict, dirty).
    """
    cached = dict(cache.get("windows") or {})
    result = {}
    dirty = False
    for name in _WINDOW_NAMES:
        live = rate_limits.get(name) if isinstance(rate_limits, dict) else None
        if isinstance(live, dict) and live.get("used_percentage") is not None:
            entry = {
                "used_percentage": live.get("used_percentage"),
                "resets_at": live.get("resets_at"),
            }
            # Guard against a concurrent idle session: an idle client republishes
            # the last value it observed, so within one window (same resets_at,
            # where usage only ever climbs) never let a stale render regress the
            # cached percentage.
            prev = cached.get(name)
            if (prev and prev.get("resets_at") == entry["resets_at"]
                    and prev.get("used_percentage") is not None
                    and prev["used_percentage"] > entry["used_percentage"]):
                entry["used_percentage"] = prev["used_percentage"]
            result[name] = entry
            if cached.get(name) != entry:
                cached[name] = entry
                dirty = True
        else:
            prev = cached.get(name)
            if prev and _window_fresh(prev, now):
                result[name] = prev
            elif prev is not None:
                cached.pop(name, None)
                dirty = True
    if dirty:
        cache["windows"] = cached
    return result, dirty


def _win_pct(window):
    """used_percentage of a resolved window dict, or None."""
    return window.get("used_percentage") if isinstance(window, dict) else None


def build_overage_segment(billing_mode: str, account: dict, windows: dict, config: dict):
    """Red overage indicator, or None when not in overage / disabled.

    Definitive: a gateway `spend_limit` window past 100%. Proxy (plan accounts,
    which never receive real-time overage state): a 5h/7d window at/over the
    threshold while the account has extra usage enabled — i.e. past the included
    allotment and not blocked, so the overflow is billed. Correct whether or not
    the platform caps window utilization at 100%.
    """
    if not config.get("overage_indicator", True):
        return None
    try:
        threshold = float(config.get("overage_threshold", 99))
    except (TypeError, ValueError):
        threshold = 99.0

    spend_pct = _win_pct(windows.get("spend_limit"))
    triggered = spend_pct is not None and spend_pct > 100
    if not triggered and billing_mode == "subscription" and account.get("has_extra_usage"):
        for name in ("five_hour", "seven_day"):
            pct = _win_pct(windows.get(name))
            if pct is not None and pct >= threshold:
                triggered = True
                break
    if not triggered:
        return None
    return colorize(str(config.get("overage_label", "⚠ overage")), C_RED)


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.stdout.write("(status: bad input)\n")
        return

    now = int(time.time())
    config = _read_json(BUDGET_PATH)
    cache = _read_json(CACHE_PATH)
    dirty = False

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

    # Billing mode — decided from the login, not from window presence this render.
    account, acc_dirty = get_account(cache)
    dirty = dirty or acc_dirty
    billing_mode = resolve_billing_mode(account, config)

    # Rate-limit windows: live stdin merged over the last-seen cache.
    rate_limits = data.get("rate_limits") or {}
    windows, win_dirty = resolve_windows(rate_limits, cache, now)
    dirty = dirty or win_dirty
    five_str = build_rate_segment("5h", windows.get("five_hour"), "h")
    seven_str = build_rate_segment("7d", windows.get("seven_day"), "d")
    spend_str = build_rate_segment("spend", windows.get("spend_limit"))

    # Per-session dollar spend — shown ONLY under API billing, where it is the
    # real signal. Gate on key presence, not truthiness: $0.00 at session start
    # is legitimate data, not a missing field.
    spend_seg = None
    if billing_mode == "api" and "cost" in data:
        cost_usd = (data.get("cost") or {}).get("total_cost_usd")
        if cost_usd is not None:
            spend_seg = build_spend_segment(float(cost_usd), session_budget_usd(config))

    # Overage indicator — hidden unless triggered.
    overage_str = build_overage_segment(billing_mode, account, windows, config)

    # Sandbox — on is green (protected); off is orange (heads-up).
    sandbox_on = get_sandbox_enabled()
    sb_str = colorize("sb:on", C_GREEN) if sandbox_on else colorize("sb:off", C_ORANGE)

    # Assemble parts
    parts = [model_str]
    if branch:
        parts.append(branch)
    parts.append(ctx_str)

    if billing_mode == "api":
        # API billing: the dollar bar is the real signal. Still surface a gateway
        # window if one happens to be reported.
        if spend_seg is not None:
            parts.append(spend_seg)
        for seg in (five_str, seven_str, spend_str):
            if seg is not None:
                parts.append(seg)
    else:
        # Subscription: account usage only, never dollars. Until any window is
        # known (first-ever launch, or just after a reset) show a neutral
        # placeholder rather than falling back to the dollar bar.
        window_segs = [seg for seg in (five_str, seven_str, spend_str) if seg is not None]
        if window_segs:
            parts.extend(window_segs)
        else:
            parts.append(colorize("usage --", C_GRAY))

    if overage_str is not None:
        parts.append(overage_str)
    parts.append(sb_str)

    sys.stdout.write(" | ".join(parts) + "\n")

    if dirty:
        _write_cache(cache)


if __name__ == "__main__":
    main()
