#!/usr/bin/env bash

echo ""
echo "########################################################################"
echo "Running OS package updates..."

case "$(uname -s)" in
Linux)
  sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
  ;;
*)
  echo -n "Platform unsupported for OS package updates..."
  ;;
esac

echo ""

echo "########################################################################"
echo "Running 'brew' package updates..."
brew update && brew upgrade
echo ""
