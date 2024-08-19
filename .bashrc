# .bashrc

# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# User specific environment
if ! [[ "$PATH" =~ "$HOME/.local/bin:$HOME/.bin:" ]]
then
    PATH="$HOME/.local/bin:$HOME/.bin:$PATH"
fi
export PATH

# Uncomment the following line if you don't like systemctl's auto-paging feature:
# export SYSTEMD_PAGER=

# User specific aliases and functions
if [ -d ~/.bashrc.d ]; then
        for rc in ~/.bashrc.d/*; do
                if [ -f "$rc" ]; then
                        . "$rc"
                fi
        done
fi

unset rc

#
# user customizations
#

# env
LANG=en_US.UTF-8
LANGUAGE=en_US.UTF-8
LC_ALL=en_US.UTF-8
export editor=vim
export PATH="$PATH:/usr/local/bin:/usr/local/go/bin:/usr/local/nvim-linux64/bin:$HOME/go/bin"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

. "$HOME/.cargo/env"

# ui
export CLICOLOR=1
export COLORTERM=truecolor
eval "$(starship init bash)"

# aliases
export COLOR_MODE='--color=auto'
alias python=python3
alias pip=pip3
alias ll='ls -l ${COLOR_MODE}' # long
alias ls='ls -laF ${COLOR_MODE}'
alias k=kubectl

# history
export HISTFILE=~/.bash_history
export HISTFILESIZE=100000
export HISTSIZE=1000
export HISTCONTROL=ignoredups:ignorespace
export HISTTIMEFORMAT="[%F %T] "
export HISTIGNORE="cd *:history"
shopt -s histappend

#
# dotfiles support
#
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

