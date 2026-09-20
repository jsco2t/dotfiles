#!/usr/bin/env bash
# Auto-approve commands composed ENTIRELY of safe, read-only programs —
# including pipelines (|) and &&/||/; chains. Falls through (exit 0, no
# output) for anything else, so the normal permission flow still runs.
#
# Safety stance: when in doubt, FALL THROUGH (prompt). A false negative is
# just an extra prompt; a false positive auto-runs something unintended.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // ""')

LOG="$HOME/.claude/hooks/allow-safe-pipes.log"
log() { printf '%s\t%s\t%s\n' "$(date '+%H:%M:%S')" "$1" "${2//$'\n'/ }" >> "$LOG" 2>/dev/null || true; }

[[ -n "$cmd" ]] || exit 0

# Read-only / navigation programs that are safe to auto-approve.
is_safe() {
    case "$1" in
        tail | head | cat | less | more | grep | egrep | fgrep | rg | jq | yq | \
            column | sort | uniq | awk | sed | cut | tr | nl | tac | rev | wc | \
            fold | paste | comm | diff | join | strings | ls | pwd | cd | echo | \
            printf | true | false | dirname | basename | realpath | readlink | \
            stat | file | date | du | df | tree | which | type)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

# Constructs we cannot reason about per-stage — refuse to auto-approve.
#   $(...) / `...` : can hide arbitrary commands inside a safe-looking stage.
case "$cmd" in
    *'$('* | *'`'*) log "fallthrough-cmdsubst" "$cmd"; exit 0 ;;
esac
#   background '&' : would launch an extra command we never inspect. Strip the
#   common safe redirection/operator forms first, then bail if any '&' remains.
scan=$cmd
scan=${scan//'2>&1'/ }
scan=${scan//'&>'/ }
scan=${scan//'>&'/ }
scan=${scan//'&&'/ }
case "$scan" in
    *'&'*) log "fallthrough-background" "$cmd"; exit 0 ;;
esac

# Turn every control operator into a newline so each stage is its own line.
# (Pure bash: BSD/macOS sed does NOT expand \n to a newline in replacements.)
stages=$cmd
stages=${stages//'||'/$'\n'}
stages=${stages//'&&'/$'\n'}
stages=${stages//'|'/$'\n'}
stages=${stages//';'/$'\n'}

while IFS= read -r stage; do
    read -ra toks <<< "$stage" || true   # whitespace-split; drops blank tokens
    (( ${#toks[@]} )) || continue     # blank stage (e.g. between operators)

    # First token that isn't a leading VAR=value assignment = the program.
    prog=""
    for t in "${toks[@]}"; do
        case "$t" in
            [A-Za-z_]*=*) continue ;;       # env assignment prefix — skip
            *) prog=$t; break ;;
        esac
    done
    [[ -n "$prog" ]] || continue            # stage was only assignments

    prog=${prog##*/}                        # /usr/bin/grep -> grep
    if ! is_safe "$prog"; then
        log "fallthrough-unsafe=$prog" "$cmd"
        exit 0
    fi
done <<< "$stages"

log "allow" "$cmd"
jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    permissionDecisionReason: "All pipeline/chain stages are safe read-only commands"
  }
}'
