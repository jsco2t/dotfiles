# -----------------------------------------------------------
# zshrc
# -----------------------------------------------------------

#
# local binpaths
#
if [ -d "$HOME/.local/bin" ]; then
    PATH="$PATH:$HOME/.local/bin"
    export PATH
fi

if [ -d "$HOME/.bin" ]; then
    PATH="$PATH:$HOME/.bin"
    export PATH
fi

if [ -d "$HOME/go/bin" ]; then
    PATH="$PATH:$HOME/go/bin"
    export PATH
fi


#
# linux brew support
#
if [ -d /home/linuxbrew/.linuxbrew/bin ]; then
    PATH="$PATH:/home/linuxbrew/.linuxbrew/bin"
    export PATH
fi

#
# macos brew support
#
if [ -d "/opt/homebrew" ]; then
  PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
  PATH="$PATH:/opt/homebrew/bin"
  PATH="$PATH:/opt/homebrew/sbin"
  export PATH
  export CPPFLAGS="-I/opt/homebrew/opt/openjdk/include"
fi

#
# env configuration
#
export LANG=en_US.UTF-8
LANGUAGE=en_US.UTF-8
LC_ALL=en_US.UTF-8
export EDITOR=nvim
export PATH="$PATH:/usr/local/bin:/usr/local/go/bin"

#
# rust environment
#
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

#
# ui customizations
#
export CLICOLOR=1
export COLORTERM=truecolor
eval "$(starship init zsh)"

#
# aliases
#
export COLOR_MODE='--color=auto'
alias python=python3
alias pip=pip3
alias ll='ls -l ${COLOR_MODE}' # long
alias ls='ls -laF ${COLOR_MODE}'
alias k=kubectl

#
# nvm (node version manager) support
#
export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" # This loads nvm

#
# command completion support
#
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh


# to install `krew`, run:
# (
#  set -x; cd "$(mktemp -d)" &&
#  OS="$(uname | tr '[:upper:]' '[:lower:]')" &&
#  ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')" &&
#  KREW="krew-${OS}_${ARCH}" &&
#  curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" &&
#  tar zxvf "${KREW}.tar.gz" &&
#  ./"${KREW}" install krew
#)
export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"

#
# dotfiles support
#
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

#
# bat customizations
#   to see built in themes `bat --list-themes`
#
export BAT_THEME=Coldark-Dark

#
# local overrides
#

# local env customizations
if [[ -f "$HOME/.zshrc.local" ]]; then
  source "$HOME/.zshrc.local"
fi
