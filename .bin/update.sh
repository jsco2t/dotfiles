#!/usr/bin/env bash

echo ""
echo "########################################################################"
echo "Running OS package updates..."

case "$(uname -s)" in
Linux)

  if [ -f /etc/os-release ]; then
    source /etc/os-release

    if [ "$ID" == "rocky" ]; then
      echo "[INFO] OS detected as Rocky Linux, using DNF"
      sudo dnf update && sudo dnf upgrade
    else
      echo "[INFO] OS defaulting to debian based OS"
      sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
    fi

  else
    echo "[INFO] OS defaulting to debian based OS"
    sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
  fi
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
