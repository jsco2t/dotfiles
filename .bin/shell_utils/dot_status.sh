#!/bin/bash
#
# Show dotfiles repo status from the $HOME directory perspective.
#
/usr/bin/git --git-dir="$HOME/.dotfiles/" --work-tree="$HOME" status

