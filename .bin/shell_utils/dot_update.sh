#!/bin/bash
#
# Auto-commit dotfile changes with obfuscated snapshot message.
# IMPORTANT: Only operates on files already tracked by the dotfiles repo.
#            Never adds untracked files — that is a manual user activity.
#
(
  cd "$HOME" || exit 1
  dot() { /usr/bin/git --git-dir="$HOME/.dotfiles/" --work-tree="$HOME" "$@"; }

  # Stash local changes to tracked files before pulling, so rebase can proceed.
  # This handles both staged-but-uncommitted and unstaged modifications.
  needs_stash=false
  if ! dot diff --quiet || ! dot diff --cached --quiet; then
    needs_stash=true
    dot stash push --quiet
  fi

  dot pull --rebase --quiet
  pull_rc=$?

  if $needs_stash; then
    dot stash pop --quiet
  fi

  if [[ $pull_rc -ne 0 ]]; then
    echo "dot_update: pull --rebase failed (rc=$pull_rc)" >&2
    exit 1
  fi

  # Stage ONLY already-tracked files. Never use 'add -A' or 'add .'
  # as that would sweep in every untracked file under $HOME.
  dot add -u

  # Nothing to commit if the index is clean after staging tracked changes
  dot diff --cached --quiet && exit 0

  tag=$(openssl rand -hex 4)
  host=$(hostname | shasum -a 256 | cut -c1-8)

  dot commit --quiet -m "snapshot ${tag}-${host}"
  dot push --quiet
)

