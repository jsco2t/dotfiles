#
# env configuration
#
export LANG=en_US.UTF-8
export CLICOLOR=1
export EDITOR=nvim
export PATH="$HOME/.bin:/usr/local/go/bin:$HOME/.local/bin:$HOME/go/bin:/usr/local/bin:$HOME/.dotnet/tools:$HOME/.rd/bin:$PATH"
DOTNET_CLI_TELEMETRY_OPTOUT=1
if [[ -f "$HOME/.zshrc.local" ]]; then
  source "$HOME/.zshrc.local"
fi
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

if [ -d "/opt/homebrew" ]; then
  export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
  export PATH="$PATH:/opt/homebrew/bin"
  export PATH="$PATH:/opt/homebrew/sbin"
  export PATH=/opt/homebrew/opt/openjdk@11/bin:$PATH
  export CPPFLAGS="-I/opt/homebrew/opt/openjdk/include"
fi

#
# linux brew support
#
if [ -d /home/linuxbrew/.linuxbrew/bin ]
then
  PATH="$PATH:/home/linuxbrew/.linuxbrew/bin"
fi
export PATH

#
# tools / utilities
#
eval "$(starship init zsh)"

#
# nvm (node version manager) support
#
export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" # This loads nvm

#
# dotfiles management
#
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

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
# bat customizations
#   to see built in themes `bat --list-themes`
#
export BAT_THEME=Coldark-Dark

