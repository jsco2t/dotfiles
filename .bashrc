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
	PATH="/opt/homebrew/bin:$PATH"
	PATH="/opt/homebrew/sbin:$PATH"
	export PATH
	export CPPFLAGS="-I/opt/homebrew/opt/openjdk/include"
fi

#
# env customizations
#
LANG=en_US.UTF-8
LANGUAGE=en_US.UTF-8
LC_ALL=en_US.UTF-8
export editor=vim
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
eval "$(starship init bash)"

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
# node version manager
#
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                   # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion" # This loads nvm bash_completion

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
# command completion support
#
[ -f "$HOME/.fzf.bash" ] && source "$HOME/.fzf.bash"

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
# direnv support
#
if [ -x "$(command -v direnv)" ]; then
	eval "$(direnv hook bash)"
fi

#
# local overrides
#

# local env customizations
if [ -f "$HOME/.bashrc.local" ]; then
	. "$HOME/.bashrc.local"
fi
. "$HOME/.cargo/env"
