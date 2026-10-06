# git-cred-scrub

`git-cred-scrub` finds credentials embedded in git config and, with `--fix`,
strips them. It is one stdlib-only Python 3 script, and it never prints a
secret: URLs appear as `https://***@host/path`, and header and helper values
are never shown. `~/.local/bin/git-cred-scrub` is a symlink to
`cred-scrub/git-cred-scrub`.

Use it once to migrate off inline personal access tokens (PATs) and onto a
credential helper, then whenever you suspect a token landed in a config file.

## Usage

```sh
git-cred-scrub ~/src/repo ~/.dotfiles      # dry run on given repos
git-cred-scrub --scan ~/src                # dry run on every repo below ~/src
git-cred-scrub --fix --scan ~/src          # strip what it found
```

A `REPO` is a repository's top-level directory or its git dir, so a bare repo
such as `~/.dotfiles` works too. `--scan DIR` walks `DIR` at any depth and finds
work trees (a `.git` directory or file) and bare repos. Paths and `--scan` can
be combined, and `--scan` can repeat.

Every run also checks the global config (`~/.config/git/config` and
`~/.gitconfig`) and the store helper's files (`~/.git-credentials`,
`~/.config/git/credentials`, and any file a store helper names with `--file`),
whichever repos you pass.

## What it reports

| Finding | Where |
| --- | --- |
| userinfo in `remote.<name>.url` or `remote.<name>.pushurl` | repo, global |
| userinfo in `submodule.<name>.url` | repo |
| userinfo in the base of `url.<base>.insteadOf` or `pushInsteadOf` | repo, global |
| an `Authorization` header in `http.extraHeader` or `http.<url>.extraHeader` | repo, global |
| `credential.helper = store` (any `credential.*.helper`) | repo, global |
| a non-empty `~/.git-credentials` or other store file | home |

Each repo's config includes its `config.worktree` files and its submodule
configs under `.git/modules`, nested submodules included. Every file that a
scanned config pulls in through `include.path` or `includeIf.<condition>.path`
is scanned and fixed too, whatever its condition, because the token sits in
that file on disk. `git submodule init` copies a submodule's URL into
`submodule.<name>.url`, and it resolves a relative `.gitmodules` URL against
the origin URL, userinfo included, so that key is checked like a remote URL.
Userinfo counts only in `http`, `https`, `ftp` and `ftps`
URLs, because those are the transports that send it as a credential; an SSH or
scp-style user name such as `git@host:repo` is not a finding. Other extra
headers and other credential helpers are not findings either.

## What --fix changes

`--fix` rewrites config through `git config --file` and nothing else:

- It strips the userinfo from each remote and submodule URL and keeps the
  scheme, host, port, path, and the order of multi-valued keys exactly.
- It renames each `url.<base>` section to the same base without userinfo, so
  the `insteadOf` and `pushInsteadOf` rules keep working.
- It unsets only the `Authorization` values of each `extraHeader` key; other
  headers stay.
- It unsets only the `store` values of each `credential.*.helper` key; other
  helpers stay. When nothing but empty `helper =` resets would remain in that
  key, it unsets the resets too. A lone reset in `~/.gitconfig` would otherwise
  clear the helpers set in `~/.config/git/config`, which git reads first, and
  git would prompt on every operation.

`--fix` never modifies, creates, or deletes `~/.git-credentials` or any other
store file, and it never creates a global config file. It re-reads each file
it changed and reports an error if a finding survived.

## Output and exit codes

The report groups findings by file and ends with the hosts whose credentials
were exposed, then how to re-authenticate. In `--fix` mode each finding is
tagged `[fixed]`, `[NOT FIXED]`, or `[report only]`.

| Exit | Meaning |
| --- | --- |
| `0` | No credentials found. |
| `1` | Credentials remain: every finding in a dry run; the store files after `--fix`. |
| `2` | Error: a path that is missing or not a repo, an unreadable directory under `--scan`, or a fix that failed. |

## After scrubbing

Revoke every token at each host the report lists. Scrubbing a config file does
not invalidate a token that was already exposed. Then re-authenticate without
putting a token in a URL:

- For `github.com` and `gist.github.com`, run `gh auth login`. gh's credential
  helper serves both hosts.
- For any other host, create a new token, then run
  `git ls-remote https://HOST/OWNER/REPO.git` in a terminal. Git Credential
  Manager prompts once and stores the new token.

Delete `~/.git-credentials` yourself once its tokens are revoked. Also delete
every other store file the `--fix` report lists: once its helper is gone, later
runs cannot find it. Never copy an old token into the new helper.

## Tests

```sh
python3 test_git_cred_scrub.py -v
```

The tests build throwaway repos with obviously fake tokens under a temp dir and
run the tool with a temp `HOME`, so they never read your real global config.
They assert that no fake token reaches stdout or stderr. One test also dry-runs
this dotfiles checkout and the sibling `devbox-provision` checkout, and skips
when neither has an embedded origin credential; set
`GIT_CRED_SCRUB_LIVE_REPOS` (paths separated by `:`) to point it elsewhere.

## Maintainer notes

- The tool needs git 2.30 or later, because it removes store helpers with
  `git config --fixed-value`.
- Values never enter argv where git allows it: URL keys are rewritten with
  `--replace-all` and no value pattern, and Authorization headers are matched
  by a case-insensitive POSIX regex. Renaming an `insteadOf` base must name its
  section, so that one command carries the old base in argv for its lifetime.
- git's error messages and unexpected exception text pass through `sanitize()`,
  which redacts URL userinfo and masks every secret seen during the scan. A
  traceback is never printed, because `CalledProcessError` and similar
  exceptions embed argv.
- Userinfo runs to the last `@` of the authority, so an unencoded `@` in a
  password cannot leave part of the secret in the host.
- An unscoped `http.extraHeader` names no host, so the revoke list uses the
  hosts of the same file's remotes, or says the host is unknown.
