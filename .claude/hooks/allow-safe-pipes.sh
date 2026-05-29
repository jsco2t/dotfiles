#!/usr/bin/env bash
# Auto-approve commands whose final pipe stage is a safe read-only filter.
# Falls through (exit 0, no output) for anything else, so the normal
# permission flow still runs.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // ""')

# Bail if no pipe at all — let the regular matcher handle it.
[[ "$cmd" == *"|"* ]] || exit 0

# Last pipe segment, trimmed.
last=$(printf '%s' "$cmd" | awk -F'|' '{print $NF}' | sed 's/^ *//; s/ *$//')

# First word of the last segment = the filter program.
filter=${last%% *}

case "$filter" in
    tail | head | wc | cat | less | grep | rg | jq | yq | column | sort | uniq | awk | sed)
        jq -n '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "allow",
        permissionDecisionReason: "Trailing pipe to safe filter"
      }
    }'
        ;;
    *)
        exit 0
        ;;
esac
