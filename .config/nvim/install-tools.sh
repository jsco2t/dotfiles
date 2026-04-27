#!/usr/bin/env bash
# Install LSP servers, formatters, and linters.
# Run this once to set up your development toolchain.
# These replace what Mason used to install automatically.

set -euo pipefail

OS="$(uname -s)"

pkg_install() {
  case "$OS" in
    Darwin)
      brew install "$@"
      ;;
    Linux)
      if command -v apt-get &>/dev/null; then
        sudo apt-get install -y "$@"
      elif command -v dnf &>/dev/null; then
        sudo dnf install -y "$@"
      elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm "$@"
      elif command -v zypper &>/dev/null; then
        sudo zypper install -y "$@"
      else
        echo "ERROR: No supported package manager found. Install manually: $*" >&2
        return 1
      fi
      ;;
    *)
      echo "ERROR: Unsupported OS: $OS" >&2
      return 1
      ;;
  esac
}

# Map tool names to distro-specific package names where they differ.
# Homebrew and Arch use the same names for all of these.
shellcheck_pkg() { pkg_install shellcheck; }
shfmt_pkg() { pkg_install shfmt; }

taplo_pkg() {
  case "$OS" in
    Darwin) brew install taplo ;;
    Linux)
      if command -v cargo &>/dev/null; then
        cargo install taplo-cli --locked
      else
        echo "ERROR: Install cargo first, then re-run (taplo needs cargo on Linux)" >&2
        return 1
      fi
      ;;
  esac
}

marksman_pkg() {
  case "$OS" in
    Darwin) brew install marksman ;;
    Linux)
      local url="https://github.com/artempyanykh/marksman/releases/latest/download/marksman-linux-x64"
      echo "Downloading marksman binary..."
      curl -fsSL "$url" -o /usr/local/bin/marksman && chmod +x /usr/local/bin/marksman
      ;;
  esac
}

stylua_pkg() {
  case "$OS" in
    Darwin) brew install stylua ;;
    Linux)
      if command -v cargo &>/dev/null; then
        cargo install stylua --locked
      else
        echo "ERROR: Install cargo first, then re-run (stylua needs cargo on Linux)" >&2
        return 1
      fi
      ;;
  esac
}

echo "=== Go tools ==="
go install golang.org/x/tools/gopls@latest
go install golang.org/x/tools/cmd/goimports@latest
go install mvdan.cc/gofumpt@latest

echo "=== Rust tools ==="
rustup component add rust-analyzer

echo "=== Python tools ==="
# ruff is a Rust binary; brew has it on macOS, cargo on Linux
case "$OS" in
  Darwin) brew install ruff ;;
  Linux)
    if command -v cargo &>/dev/null; then
      cargo install ruff --locked
    else
      echo "ERROR: Install cargo first, then re-run (ruff needs cargo on Linux)" >&2
    fi
    ;;
esac

echo "=== Shell tools ==="
shellcheck_pkg
shfmt_pkg

echo "=== TOML tools ==="
taplo_pkg

echo "=== Markdown tools ==="
marksman_pkg

echo "=== npm tools ==="
npm install -g pyright                         # Python type checker LSP
npm install -g bash-language-server
npm install -g vscode-langservers-extracted    # jsonls
npm install -g yaml-language-server
npm install -g dockerfile-language-server-nodejs
npm install -g @microsoft/compose-language-service
npm install -g markdownlint-cli2

echo "=== Lua tools ==="
stylua_pkg

echo ""
echo "All tools installed. Start nvim to install plugins via vim.pack."
