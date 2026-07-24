# -----------------------------------------------------------
# zshrc
# -----------------------------------------------------------

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
eval "$(starship init zsh)"

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
        eval "$(command pyenv init - zsh)"
        pyenv "$@"
    }
fi

#
# direnv support
#
if [ -x "$(command -v direnv)" ]; then
    eval "$(direnv hook zsh)"
fi

#
# fzf support (key bindings incl. ctrl-r history search, + completion)
#
# fzf >= 0.48 supports `fzf --zsh`; older versions (e.g. Ubuntu 24.04
# ships 0.44) do not, so we feature-detect and fall back to legacy files.
#
if [ -x "$(command -v fzf)" ]; then
    if fzf_init="$(fzf --zsh 2>/dev/null)"; then
        eval "$fzf_init"
        unset fzf_init
    elif [ -f "$HOME/.fzf.zsh" ]; then
        source "$HOME/.fzf.zsh"
    elif [ -f "/usr/share/doc/fzf/examples/key-bindings.zsh" ]; then
        source "/usr/share/doc/fzf/examples/key-bindings.zsh"
    fi
fi

#
# ssh agent
#
HOSTID=$(hostname)
HOSTID=$(echo "$HOSTID" | sed 's/[ -.]/_/g')
HOSTID=$(echo "$HOSTID" | tr '[:upper:]' '[:lower:]')
export SSH_AUTH_SOCK="$HOME/.ssh/ssh-agent.$HOSTID.sock"

/usr/bin/ssh-add -l >/dev/null 2>&1
ssh_rc=$?
if [ "$ssh_rc" -eq 2 ]; then
    rm -f "$SSH_AUTH_SOCK"
    /usr/bin/ssh-agent -a "$SSH_AUTH_SOCK" >/dev/null 2>&1
    if [[ "$OSTYPE" == "darwin"* ]]; then
        /usr/bin/ssh-add --apple-load-keychain 2>/dev/null
    fi
fi

#
# zsh plugins
#
# syntax highlighting: https://github.com/zsh-users/zsh-syntax-highlighting
# autosuggestions: https://github.com/zsh-users/zsh-autosuggestions
zshBaseUtilPath="/usr/local/share"
zshAltUtilPath="/opt/homebrew/share"

if [[ -f "$zshBaseUtilPath/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]]; then
    source "$zshBaseUtilPath/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
    export ZSH_HIGHLIGHT_HIGHLIGHTERS_DIR="$zshBaseUtilPath/zsh-syntax-highlighting/highlighters"
elif [[ -f "$zshAltUtilPath/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]]; then
    source "$zshAltUtilPath/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
    export ZSH_HIGHLIGHT_HIGHLIGHTERS_DIR="$zshAltUtilPath/zsh-syntax-highlighting/highlighters"
fi

if [[ -f "$zshBaseUtilPath/zsh-autosuggestions/zsh-autosuggestions.zsh" ]]; then
    source "$zshBaseUtilPath/zsh-autosuggestions/zsh-autosuggestions.zsh"
    export ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=cyan,bold"
    export ZSH_AUTOSUGGEST_BUFFER_MAX_SIZE="15"
elif [[ -f "$zshAltUtilPath/zsh-autosuggestions/zsh-autosuggestions.zsh" ]]; then
    source "$zshAltUtilPath/zsh-autosuggestions/zsh-autosuggestions.zsh"
    export ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=cyan,bold"
    export ZSH_AUTOSUGGEST_BUFFER_MAX_SIZE="15"
fi

#
# zsh completion system
#
if [ -d "/opt/homebrew/share/zsh/site-functions" ]; then
    FPATH="/opt/homebrew/share/zsh/site-functions:${FPATH}"
elif [ -d "/home/linuxbrew/.linuxbrew/share/zsh/site-functions" ]; then
    FPATH="/home/linuxbrew/.linuxbrew/share/zsh/site-functions:${FPATH}"
fi
autoload -Uz compinit
compinit

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
if [[ -f "$HOME/.zshrc.local" ]]; then
    source "$HOME/.zshrc.local"
fi
