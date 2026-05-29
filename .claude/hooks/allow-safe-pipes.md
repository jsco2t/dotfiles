# Setup

Update `~/.claude/settings.json` to include:

```
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/allow-safe-pipes.sh",
        "timeout": 3
      }]
    }]
  }
}
```

## Project Specific Config

Worth adding the following to the `CLAUDE.md/AGENTS.md` file:

```
## Shell command style

Prefer running commands as separate Bash tool calls rather than chaining
them with `&&`, `||`, `;`, or pipes. Each command should be its own
invocation so the permission matcher can authorize them individually.

Exceptions where chaining is fine:
- Pipes that are part of a single logical operation (`grep ... | wc -l`,
  `cat foo | jq .bar`) — these only make sense as one command.
- `cd <dir> && <cmd>` when the directory change must scope to that one
  command and not persist.

When in doubt, run them separately.
```
