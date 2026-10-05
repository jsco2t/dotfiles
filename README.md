# dotfiles

linux/macos environment files

## Overview

You can cherry-pick individual files from this repository as needed. Alternatively this repository is setup in such a way
that with some git _"trickery"_ you can source _dot files_ directly from this repository. If you choose to go down this latter
route it is highly recommended that you fork this repo before using it for your local machines. For clarity this repository is
purpose built for development environments (usually ephemeral-ish) that I work within. As such, some of the configuration
defined in these _dot files_ may not meet your needs/requirements. 

The remainder of this readme is dedicated to using `git` to automate the lifecycle management of these files on a local
machine. 

### Background

The general idea for this _dot files_ management pattern came from a post from [Atlassian](https://www.atlassian.com/git/tutorials/dotfiles) 
(which came from discussions on HackerNews). The high level concept is that you use a _git repository_ (with a custom name) in your 
home directory to allow you to easily pull updated dot files from a git repo. This local repository is configured in such a way that 
it only tracks files which are **explicitly** added to it. Meaning, by default, it ignores all the files in your home directory 
(or sub directories) unless it is told to manage those files as part of your _dot files_. 
 
## Initial Setup

The following are a set of bash script commands to run in your home directory (the root of your home directory). Note that there are two lines below (for `user.name` and `user.email`) that need to be fixed prior to running the script. It's suggested the script file be named `.dotsetup.sh` as that will automatically be git-ignored.

```bash
# alias a customized git command to "dot" to make it easier to work with the repo:
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases

# Have git ignore the `.dotfiles` folder as that's where the git repo config has been placed
rm -fr .gitignore
echo ".dotfiles" >> .gitignore
echo ".dotsetup.sh" >> .gitignore

# clone and configure the repo:
rm -fr .dotfiles
rm -fr .git
git clone --bare https://github.com/jsco2t/dotfiles.git $HOME/.dotfiles

# configure user for repo
dot config --local status.showUntrackedFiles no
dot config --local user.name "user name"
dot config --local user.email "email@address"

# post-clone cleanup
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases

dot fetch
dot reset --hard
dot pull origin main
```

If you are going to be performing development (ex: creating branches for development) you may want to clone the repository as a non-bare repo. The following should accomplish this. 

```bash
# alias a customized git command to "dot" to make it easier to work with the repo:
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/'
shopt -s expand_aliases

# Have git ignore the `.dotfiles` folder as that's where the git repo config has been placed
rm -fr .gitignore
echo ".dotfiles" >> .gitignore
echo ".dotsetup.sh" >> .gitignore

# clone and configure the repo:
rm -fr .dotfiles
rm -fr .git
git init --separate-git-dir=$HOME/.dotfiles -b main
dot remote add origin https://github.com/jsco2t/dotfiles.git

dot config --local status.showUntrackedFiles no
dot config --local user.name "user name"
dot config --local user.email "email@address"

alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases
dot fetch
dot reset --hard origin/main
dot branch --set-upstream-to=origin/main main
dot pull origin main
```

You will then need to add the following into your `.bashrc` (or `.zshrc`):

```bash
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
```

If this has worked as expected - you should be able to open a **new** shell and run:

``` bash
dot pull
```

And the `pull` command should work as expected.

## Working with the `dotfiles` repo

To help formalize working with this repository the `git` command is aliased to `dot` with the necessary configuration to work with the dotfiles repo. What this means in practice is that when working with the dotfiles repo you need to use `dot` instead of `git` (`dot add`, `dot commit`, `dot push`, `dot pull`...etc).

## Git credentials

Git sends `https://github.com` and `https://gist.github.com` to the credential helper of gh (the GitHub CLI) and every
other HTTPS host to Git Credential Manager (GCM), so no token has to live in a remote URL. The tracked
`~/.config/git/config` wires this up (`.config/git/config:15-30`), and
[devbox-provision](https://github.com/jsco2t/devbox-provision), the companion repo that installs tools, puts GCM at
`~/.local/bin/git-credential-manager`. The wrappers and the precedence rules are described in more detail in
[`.local/bin/gcm-helper/README.md`](.local/bin/gcm-helper/README.md).

### Helpers

Git calls both helpers by absolute path, so they work in shells that lack `~/.local/bin` or the Homebrew bin on `PATH`:

- `~/.local/bin/git-credential-gh` runs `gh auth git-credential` for github.com and gist.github.com.
- `~/.local/bin/git-credential-gcm` runs GCM for every other host.

Each wrapper exits silently when its binary is missing, and git then falls back to its own prompt. Every `[credential]`
block in the tracked config starts with an empty `helper =`, which clears the helpers set before it, so each host reaches
exactly one helper. Keep `credential.helper` out of `~/.gitconfig`: git reads that file after the tracked config and would
add the helper for every host.

### Where credentials are stored

On Linux GCM uses the `cache` store, which keeps credentials in the memory of git's credential-cache daemon for 8 hours
or until the daemon exits. On macOS GCM uses the Keychain, which keeps them until you delete them.

On Linux the GCM wrapper sets `GCM_CREDENTIAL_STORE=cache` when the variable is unset
(`.local/bin/gcm-helper/git-credential-gcm:18-21`), and `credential.cacheOptions = --timeout 28800` sets the 8-hour
timeout (`.config/git/config:22`). The cache writes no credential to disk, so keep your tokens in a password manager: you
re-enter them after the timeout or a reboot. On macOS the wrapper leaves the variable alone and GCM uses its Keychain
default.

To pick another store, export `GCM_CREDENTIAL_STORE` before git runs (for example `gpg`, which survives reboots but needs
a GPG key and a TTY; see GCM's [credential store docs](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/credstores.md)).
Setting `credential.credentialStore` in git config has no effect on Linux, because the variable always wins.

### First-time setup

1. Create `~/.gitconfig` if it does not exist:

   ```bash
   touch ~/.gitconfig
   ```

   gh (`gh auth login`, `gh auth setup-git`) and GCM both write settings with `git config --global`. When
   `~/.gitconfig` is missing, git sends those writes to `~/.config/git/config` instead, which is the tracked file: gh
   would rewrite the GitHub blocks there, and GCM's writes would show up as dotfiles changes.

2. Sign in to GitHub with `gh auth login`. If gh adds its own helper to `~/.gitconfig`, that entry takes over for the two
   GitHub hosts; it names gh by absolute path, so it works without gh on `PATH` too.

3. Sign in to each other host once, from a terminal, using a newly created token:

   ```bash
   git ls-remote https://gitlab.example.com/group/repo.git
   ```

   GCM prompts for a username and token, and git stores them only after the server accepts them.

### Per-host settings

Put host blocks in `~/.gitconfig`, not in the tracked config, because they name your hosts and user names. Pin
`provider` for every self-hosted host: otherwise GCM probes the host over HTTP and writes the provider it detects to
`~/.gitconfig` itself. A `username` makes GCM prompt for the token only.

```ini
# Any HTTPS host: username plus token.
[credential "https://git.example.org"]
	provider = generic
	username = your-username

# GitLab (gitlab.com or self-hosted): skip straight to the token prompt.
[credential "https://gitlab.example.com"]
	provider = gitlab
	gitLabAuthModes = pat
	username = your-username

# Bitbucket Cloud with an Atlassian API token.
[credential "https://bitbucket.org"]
	bitbucketAuthModes = basic
	bitbucketValidateStoredCredentials = false
	username = your-username
```

Bitbucket needs `bitbucketValidateStoredCredentials = false` because GCM re-checks stored credentials against Bitbucket's
REST API, an API token fails that check, and GCM then prompts on every operation
([GCM issue #1991](https://github.com/git-ecosystem/git-credential-manager/issues/1991); the workaround is community-reported).

### Agents

Start agents with prompts turned off, so a missing credential fails fast instead of hanging:

```bash
export GCM_INTERACTIVE=0 GIT_TERMINAL_PROMPT=0
```

`GCM_INTERACTIVE=0` makes GCM return an error instead of prompting, and `GIT_TERMINAL_PROMPT=0` stops git's own fallback
prompt. Stored credentials are still returned, so an agent works while the store holds a token; when the cache expires,
run `git ls-remote` yourself to refill it. Set these variables only in the agent's environment, not in your shell profile,
and never put `credential.interactive = false` in the shared config: either would take your prompt away too.

### Removing embedded tokens

`git-cred-scrub` finds credentials embedded in git config and, with `--fix`, strips them. It checks remote and
`submodule.<name>.url` URLs, `url.<base>.insteadOf` bases, `Authorization` extra headers, and `credential.helper = store`.
It reads each repo's config, its `<git dir>/config.worktree` files, its submodule configs, the global config, and every
file those pull in through `include.path` or `includeIf.<condition>.path`. It reports `~/.git-credentials` without ever
editing it. When `--fix` removes a store helper and only an empty `helper =` reset would remain in that key, it drops the
reset too, because a lone reset in `~/.gitconfig` would clear the helpers set in the tracked config. It never prints a
secret; URLs appear as `https://***@host/path`.

```bash
git-cred-scrub ~/src/repo ~/.dotfiles   # dry run on the given repos
git-cred-scrub --scan ~/src             # dry run on every repo below ~/src
git-cred-scrub --fix --scan ~/src       # strip what it found
```

After scrubbing:

1. Revoke every token at each host the report lists. Scrubbing a file does not invalidate a token that was already
   exposed.
2. Sign in again: `gh auth login` for GitHub, and a new token plus `git ls-remote` for any other host (see
   [First-time setup](#first-time-setup)). Never copy an old token into a helper.
3. Delete `~/.git-credentials` and every other store file the report lists.

Exit codes and the full list of findings are in [`.local/bin/cred-scrub/README.md`](.local/bin/cred-scrub/README.md).

### Limits

The helpers keep tokens out of files and URLs, not away from your own processes. Any process running as you, an agent
included, can run `git credential fill` and get a host's stored token back in plain text for as long as the store holds
it. `GCM_INTERACTIVE=0` does not prevent this, because it only blocks prompts. Give each token the narrowest scope and the
shortest expiry the host allows.
