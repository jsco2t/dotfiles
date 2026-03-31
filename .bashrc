# -----------------------------------------------------------
# bashrc
# -----------------------------------------------------------

#
# global environment
#
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

#
# PATH configuration
#
# All PATH modifications in one block. Platform-specific entries
# are guarded by directory existence checks.
#

# homebrew (macOS: /opt/homebrew, Linux: /home/linuxbrew)
[ -d "/opt/homebrew/opt/openjdk/bin" ] && PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
[ -d "/opt/homebrew/sbin" ] && PATH="/opt/homebrew/sbin:$PATH"
[ -d "/opt/homebrew/bin" ] && PATH="/opt/homebrew/bin:$PATH"
[ -d "/home/linuxbrew/.linuxbrew/bin" ] && PATH="/home/linuxbrew/.linuxbrew/bin:$PATH"

# pyenv (shims added here; full init is lazy-loaded below)
export PYENV_ROOT="$HOME/.pyenv"
[ -d "$PYENV_ROOT/shims" ] && PATH="$PYENV_ROOT/shims:$PATH"
[ -d "$PYENV_ROOT/bin" ] && PATH="$PYENV_ROOT/bin:$PATH"

# rust
[ -d "$HOME/.cargo/bin" ] && PATH="$HOME/.cargo/bin:$PATH"

# go
[ -d "/usr/local/go/bin" ] && PATH="$PATH:/usr/local/go/bin"
[ -d "$HOME/go/bin" ] && PATH="$PATH:$HOME/go/bin"

# user local paths
[ -d "$HOME/.local/bin" ] && PATH="$PATH:$HOME/.local/bin"
[ -d "$HOME/.bin" ] && PATH="$PATH:$HOME/.bin"

PATH="$PATH:/usr/local/bin"
export PATH

#
# environment
#
export LANG=en_US.UTF-8
LANGUAGE=en_US.UTF-8
LC_ALL=en_US.UTF-8
export EDITOR=hx

#
# ui customizations
#
export CLICOLOR=1
export COLORTERM=truecolor
eval "$(starship init bash)"

#
# tools / utilities
#
source "$HOME/.bin/shell_utils/loader"

#
# pyenv (lazy-loaded to avoid ~1.5s startup cost)
#
if [ -d "$PYENV_ROOT" ]; then
    pyenv() {
        unset -f pyenv
        eval "$(command pyenv init - bash)"
        pyenv "$@"
    }
fi

#
# direnv support
#
if [ -x "$(command -v direnv)" ]; then
    eval "$(direnv hook bash)"
fi

#
# fzf support
#
[ -f "$HOME/.fzf.bash" ] && source "$HOME/.fzf.bash"

#
# ssh agent
#
HOSTID=$(hostname)
HOSTID=$(echo "$HOSTID" | sed 's/[ -.]/_/g')
HOSTID=$(echo "$HOSTID" | tr '[:upper:]' '[:lower:]')
export SSH_AUTH_SOCK="$HOME/.ssh/ssh-agent.$HOSTID.sock"

/usr/bin/ssh-add -l >&/dev/null
if [ $? -eq 2 ]; then
    /usr/bin/ssh-agent -a "$SSH_AUTH_SOCK" >/dev/null
    if [[ "$OSTYPE" == "darwin"* ]]; then
        /usr/bin/ssh-add --apple-load-keychain
    fi
elif [ ! -S "$SSH_AUTH_SOCK" ]; then
    /usr/bin/ssh-agent -a "$SSH_AUTH_SOCK" >/dev/null
    if [[ "$OSTYPE" == "darwin"* ]]; then
        /usr/bin/ssh-add --apple-load-keychain
    fi
fi

#
# bash completion
#
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

#
# history
#
export HISTFILE=~/.bash_history
export HISTFILESIZE=100000
export HISTSIZE=1000
export HISTCONTROL=ignoredups:ignorespace
export HISTTIMEFORMAT="[%F %T] "
export HISTIGNORE="cd *:history"
shopt -s histappend

#
# aliases
#
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

#
# environment
#
export BAT_THEME=Coldark-Dark
export FUZZBALL_INSECURE=true
export GOPRIVATE=github.com/ctrliq/*,github.com/ctrl-cmd/*,gitlab.com/ciq-inc/,go.ciq.dev/*,bitbucket.org/ciqinc/*,go.ciq.dev

#
# local overrides
#
if [ -f "$HOME/.bashrc.local" ]; then
    . "$HOME/.bashrc.local"
fi
