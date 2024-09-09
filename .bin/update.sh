#!/usr/bin/env bash

echo "########################################################################"
echo "Running OS package updates..."
sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
echo ""

echo "########################################################################"
echo "Running 'brew' package updates..."
brew update && brew upgrade
echo ""
