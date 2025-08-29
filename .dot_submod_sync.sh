#!/bin/bash

alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases

dot submodule sync --recursive
dot submodule update --init --recursive
