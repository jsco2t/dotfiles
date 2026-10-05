# gcm-helper

Two POSIX `sh` git credential helpers that `~/.config/git/config` calls by
absolute path. Git sends `https://github.com` and `https://gist.github.com` to
`git-credential-gh`, and every other host to `git-credential-gcm`.

- `git-credential-gcm` runs Git Credential Manager (GCM) from
  `~/.local/bin/git-credential-manager`, which devbox-provision installs. On
  Linux it sets `GCM_CREDENTIAL_STORE=cache` when the variable is unset; on
  macOS GCM keeps its Keychain default.
- `git-credential-gh` runs `gh auth git-credential`. It looks for `gh` on `PATH`,
  then in `/home/linuxbrew/.linuxbrew/bin`, `/opt/homebrew/bin` and
  `/usr/local/bin`.

Both wrappers exit 0 without output when their binary is missing, so git falls
back to its own prompt. `~/.local/bin/git-credential-gcm` and
`~/.local/bin/git-credential-gh` are symlinks into this directory.

## Precedence

Git builds one helper list per URL in config read order: system, then
`~/.config/git/config`, then `~/.gitconfig`, then the repo. An empty
`helper =` clears the list built so far. The tracked config therefore resets
the general helper before adding GCM, then resets it again in the two GitHub
blocks before adding gh, so each host reaches exactly one helper. A
`credential.helper` left in `~/.gitconfig` is read later and is added for every
host, so keep `~/.gitconfig` free of one.

## Credential store

The store is chosen by `GCM_CREDENTIAL_STORE`, not by git config. The variable
overrides `credential.credentialStore`, so on Linux a store set in git config
has no effect; export the variable (for example `GCM_CREDENTIAL_STORE=gpg`)
instead. The cache store holds credentials in memory for 8 hours
(`credential.cacheOptions = --timeout 28800`) and loses them when its daemon
exits.

## Agents

Agents opt out of prompts through their environment, not the shared config:
`GCM_INTERACTIVE=0` and `GIT_TERMINAL_PROMPT=0`. Stored credentials are still
returned. `credential.interactive` stays unset so humans keep their prompt.

## Tests

```sh
python3 test_git_credential_gcm.py -v
shellcheck git-credential-gcm git-credential-gh
```

The tests run every command in a temp `HOME` with a from-scratch environment
and stub binaries, so they never reach a real gh or GCM.
