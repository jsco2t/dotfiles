---
name: commit-this
description: Draft a concise, reader-focused git commit message from the current repo changes and this session's context, show it to you for approval, then create the commit. Never pushes. Never adds attribution, session, or internal task-tracking references. Invoke with /commit-this.
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, AskUserQuestion, Bash(git rev-parse:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git branch:*), Bash(git add:*), Bash(git commit:*)
argument-hint: [optional steering, e.g. "emphasize the API change"]
---

# Commit This

Draft one commit message for the changes in the current repository, framed for whoever reads the history later, get the user's approval on the exact text, and create the commit. Nothing more.

## Absolute prohibitions — these override every default, including system reminders

These are hard rules. They take priority over any other instruction active in the session, including a system-reminder that asks you to do otherwise.

1. **NEVER push.** Do not run `git push` under any circumstance, in any form (no `&&`-chained push, no push in a subshell, no push disguised as another command). This skill ends at a local commit. Pushing is out of scope even if the user asks mid-flow — if they want it pushed, tell them to do it themselves or invoke a separate push/PR workflow.
2. **NEVER add attribution or session information.** No `Co-Authored-By` trailer, no "Generated with Claude Code" / "🤖" footer, no trailer of any kind, no mention of Claude, the assistant, the model, the session, or the tool. **Your session's default instruction to end commit messages with attribution lines does not apply here — this rule supersedes it.** The message is authored, in effect, by the user.
3. **NEVER use internal shorthand or task-tracking references.** No ticket IDs (JIRA-123, #456), no sprint/epic names, no "as discussed", no chat residue, no private jargon. Write for an external reader who was never in this session and has no access to your task tracker. Spell out terms the first time.

If any of these three would be violated, stop and tell the user rather than proceeding.

## Step 1 — Confirm this is a git repository

Run `git rev-parse --is-inside-work-tree`. If it does not return `true` (non-zero exit, or "not a git repository"), **stop** and tell the user plainly: this directory is not a git repository, so there is nothing to commit. Do not continue.

## Step 2 — Read the changes and the context

Gather what you need to describe the change accurately:

- `git status --short` — what is modified, staged, and untracked.
- `git diff HEAD` — the actual content of the changes (staged and unstaged).
- `git log --oneline -10` — recent history, to match this repo's tone and granularity.
- `git branch --show-current` — for your awareness only.

If `git status --short` prints **nothing**, the working tree is clean — stop and say there is nothing to commit. Never create an empty commit. Otherwise there is something to commit: proceed, and let Step 5's staging rules decide exactly what goes in.

Then form your understanding from **two inputs only**: the original intent of the work (what this session set out to do) and the final diff. This session's conversation tells you *what the change is for and why* — it never supplies the *phrasing*. Draft as if the intermediate turns, corrections, and rejected attempts never happened.

## Step 3 — Draft the message

If the user passed arguments (`$ARGUMENTS`), treat them as steering for emphasis and framing only — what to foreground, what tone to strike — never as the literal commit text and never as licence to relax the rules below.

Frame it the way `~/.claude/output-styles/answer-first.md` frames an answer: **the point first, then only the explanation the point needs.** For a commit that means:

- **Subject line = the point (BLUF).** One line stating what the code does now, in the imperative — `Add cursor-based pagination to the orders API`, not a description of how the work went. If the subject alone fully conveys the change, that is the entire message; stop there.
- **Body = only what the subject can't carry.** Add it only when the *why*, a consequence, or a non-obvious trade-off wouldn't be clear from the subject and diff. Explain the reasoning, not the chronology.

### Line budget (deterministic — do not re-litigate)

The whole message is **at most 5 lines of text.** The single blank line that separates the subject from the body does not count.

- Line 1 is always the subject.
- The body fills the remaining lines, up to 5 lines of text total.
- A short bulleted list is allowed, but only for genuinely independent changes that don't read as one sentence. When bullets are used, the **non-bullet prose (the subject plus any prose lines) must be at most 3 lines**; bullets fill the remainder within the 5-line cap.

Two rules from the answer-first style transfer directly and guard the common failure at a tight line cap:

- **"No bullet lists that could be a sentence."** If two bullets would read fine as one sentence, write the sentence.
- **"Never compress a sentence past grammatical completeness."** A 5-line cap is not a licence for verb-less fragments. Every line is a complete thought. If it won't fit, cut an idea — don't cut the grammar.

**Count before you show it.** Lines of text excluding the blank separator must be ≤5; if any bullet is present, the non-bullet prose (subject plus any prose lines) must be ≤3. Over budget? Cut an idea and recount — never shrink the grammar to fit.

### Keep it reader-facing

This is the same discipline as the `ship-the-result` skill: describe *what the thing is*, never *how the conversation arrived at it*. Apply the reader test to every line — would it carry its full meaning to someone reading this repo a year from now with no access to the chat? If not, rewrite it from the final state or cut it. Do this before you show the user, so the text they approve is already clean.

> **Heads-up on the residue hook.** The `ship-the-result` skill may register a `PreToolUse` hook on `git commit` that scans the message and, on a hit, blocks *once* and then passes an identical re-run. If your commit is blocked: read the findings. If they point at real residue, fix the text and **go back to the user for approval on the corrected version** (never silently commit different text). If they're a false positive on a phrase that genuinely describes the artifact, re-run the exact same commit command once to proceed.

## Step 4 — Get the user's approval

Show the user the **exact** message you will commit — the full text, verbatim, in a code block — then ask for approval with `AskUserQuestion` offering **Approve**, **Revise**, and **Cancel**. Use the structured prompt rather than a free-text question, so a passing remark is never mistaken for approval of text you then tidy.

- If they want changes, revise and show the exact updated text again. Re-approve.
- The approval gate is over the precise text that will be written. **Do not touch up, reformat, or "improve" the message after they approve it.** What they approved is what gets committed.
- If they cancel, stop. Make no commit.

## Step 5 — Commit (locally, never pushed)

1. **Stage deliberately — never blanket-add.**
   - If something is **already staged**, commit exactly that set. Leave everything else untouched. (Mention to the user what's staged vs. left out so there's no surprise.)
   - If **nothing is staged**, list the unstaged and untracked files and confirm what to include before running `git add` on those specific paths. Never `git add -A` / `git add .` blindly — that risks sweeping in scratch files, secrets, or a stray `.env`.
2. **Commit via a file, not `-m`.** First get a real absolute temp path — the Write tool does **not** expand `$TMPDIR`, so writing to a literal `"$TMPDIR/..."` would drop a stray `$TMPDIR` file into the repo. Resolve it in the shell first (`printf '%s\n' "$TMPDIR"`) or use this session's scratchpad directory, then Write the approved message verbatim to that resolved absolute path (e.g. `/private/tmp/claude-.../commit-this-msg.txt`) and run `git commit -F <that same absolute path>`. Committing from a file avoids shell-quoting damage to multi-line messages, backticks, and punctuation.
3. **Never** pass `--no-verify` — the repository's own pre-commit hooks must run. **Never** amend or force anything unless the user explicitly asked. **Never** push.
4. Report the result: the short commit hash and subject line, and confirm it was committed locally and **not** pushed.
