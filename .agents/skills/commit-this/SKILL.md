---
name: commit-this
description: "Draft a concise git commit message from repository changes and session intent, obtain approval of the exact text and file scope, then create a local commit. Excludes attribution, session residue, and internal task references; pushing is outside this workflow."
---

# Commit This

Create one local commit from the agreed changes. Preserve staged and unrelated
work. This workflow does not push, amend, force, or bypass hooks.

1. Verify the current directory is a Git repository. Inspect `git status --short`,
   staged and unstaged diffs, untracked files relevant to the request, and recent
   subjects (`git log --oneline -10`). On an unborn branch, compare against the
   index/working tree rather than assuming `HEAD` exists. Stop on a clean tree.
2. Establish commit scope before drafting: if files are staged, use that exact
   set. If none are staged, propose specific paths and obtain selection unless
   the user already specified them. Avoid blanket `git add .` or `git add -A`.
   Read selected untracked files; ordinary diff output omits them.
3. Draft from the final scoped diff and the session's original purpose. Steering
   affects emphasis, not literal phrasing. Lead with an imperative subject that
   describes the resulting behavior. Add a body only for necessary reasoning,
   consequences, or trade-offs; omit conversational history and rejected attempts.
4. Use at most five nonblank lines. If bullets are needed for independent changes,
   non-bullet prose has at most three lines within that total. Keep complete
   thoughts; cut ideas rather than grammar. Do not add attribution, tool/model/
   session references, ticket IDs, sprint/epic names, private shorthand, or chat
   residue. Match repository conventions where compatible with these rules.
5. Show the exact message in a code block and the included file scope. Request
   approval of that concrete result unless the exact text and scope are already
   approved. Offer approve/revise/cancel through an available user-input tool or
   a concise chat question. Revise and re-approve any changed text.
6. Stage only selected paths if needed. Recheck the index diff against the
   reviewed scope; stop for unexpected changes. Write the approved text verbatim
   to a resolved absolute temporary file and run `git commit -F <file>`.
   Let repository hooks run. If a hook fails, inspect the failure and report it;
   do not bypass it or blindly retry. Re-approve any required message change.
7. Verify the resulting commit and report its short hash, subject, and local
   status. If hooks altered committed content, disclose that difference.
