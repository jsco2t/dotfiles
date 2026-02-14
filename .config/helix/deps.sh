#!/usr/bin/env bash
set -euo pipefail

# Helix editor language tooling dependencies
# Works on macOS and Linux
#
# Strategy: Language-native installers (go, cargo, npm, uv/pipx, rustup) as primary.
# These always fetch the latest version and work identically across platforms.
# brew is used only as a fallback for tools without a language-native installer.
#
# Python tools are installed via uv, which is auto-installed if missing.
# uv installs each tool in an isolated venv, avoiding conflicts with
# the system Python — which on macOS is old and blocks global pip installs.
# Falls back to pipx or pip if uv installation fails.
#
# Idempotency: Safe to re-run at any time.
#   - go/cargo/npm always install the latest version (re-running IS upgrading)
#   - uv/pipx install if missing; upgrade only with --upgrade flag
#   - brew installs if missing; upgrades only with --upgrade flag
#   - rustup updates toolchain only with --upgrade flag
#
# More info: https://github.com/helix-editor/helix/wiki/Language-Server-Configurations

UPGRADE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install language tooling dependencies for the Helix editor.

Options:
  --upgrade, -u   Upgrade all dependencies to latest versions
                  (Without this flag, already-installed pip/brew packages are skipped)
  --help, -h      Show this help message
EOF
}

for arg in "$@"; do
    case "$arg" in
        --upgrade|-u) UPGRADE=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

has()     { command -v "$1" &>/dev/null; }
info()    { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn()    { printf '\033[1;33mWARN:\033[0m %s\n' "$1"; }
success() { printf '\033[1;32m✓\033[0m %s\n' "$1"; }

# Install a Python CLI tool via uv > pipx > pip (respects --upgrade flag)
# uv and pipx create isolated venvs per tool — no system Python pollution.
python_install() {
    local pkg="$1"
    if has uv; then
        if $UPGRADE; then
            uv tool upgrade "$pkg" 2>/dev/null || uv tool install "$pkg"
        else
            uv tool install "$pkg" 2>/dev/null || true
        fi
    elif has pipx; then
        if $UPGRADE; then
            pipx upgrade "$pkg" 2>/dev/null || pipx install "$pkg"
        else
            pipx install "$pkg" 2>/dev/null || true
        fi
    elif has pip3 || has pip; then
        local pip_cmd="pip3"
        has pip3 || pip_cmd="pip"
        warn "Using $pip_cmd (consider installing uv: https://docs.astral.sh/uv/)"
        if $UPGRADE; then
            "$pip_cmd" install --upgrade "$pkg"
        else
            "$pip_cmd" install "$pkg"
        fi
    else
        warn "No Python installer found — skipping $pkg"
        return 1
    fi
}

# Install an npm global package (respects --upgrade flag)
npm_install() {
    local pkg="$1"
    if npm ls -g "$pkg" &>/dev/null; then
        if $UPGRADE; then
            npm i -g "$pkg"
        else
            return 0
        fi
    else
        npm i -g "$pkg"
    fi
}

# Install a brew package (respects --upgrade flag)
brew_install() {
    local pkg="$1"
    if has brew; then
        if brew list "$pkg" &>/dev/null; then
            if $UPGRADE; then
                brew upgrade "$pkg" 2>/dev/null || true
            else
                return 0
            fi
        else
            brew install "$pkg"
        fi
    else
        warn "brew not found — skipping $pkg (install Homebrew or find an alternative)"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Bootstrap uv (Python tool installer)
# ---------------------------------------------------------------------------

if ! has uv; then
    info "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer places uv in ~/.local/bin — add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    if has uv; then
        success "uv installed"
    else
        warn "uv install succeeded but binary not found on PATH"
    fi
fi

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

info "Checking prerequisites..."

MISSING=()
has go      || MISSING+=("go")
has cargo   || MISSING+=("cargo (install via rustup)")
has rustup  || MISSING+=("rustup")
has npm     || MISSING+=("npm")

if [[ ${#MISSING[@]} -gt 0 ]]; then
    warn "Missing toolchains (some sections will be skipped):"
    for m in "${MISSING[@]}"; do
        warn "  - $m"
    done
fi

# ---------------------------------------------------------------------------
# Toolchain upgrades (only with --upgrade)
# ---------------------------------------------------------------------------

if $UPGRADE; then
    info "Upgrading toolchains..."
    has rustup && rustup update
fi

# ---------------------------------------------------------------------------
# Go tools
# ---------------------------------------------------------------------------

if has go; then
    info "Installing Go tools..."

    # LSP
    go install golang.org/x/tools/gopls@latest
    # Debugger
    go install github.com/go-delve/delve/cmd/dlv@latest
    # Formatter (formats + manages imports)
    go install golang.org/x/tools/cmd/goimports@latest
    # Stricter formatter
    go install mvdan.cc/gofumpt@latest
    # Linters
    go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
    go install honnef.co/go/tools/cmd/staticcheck@latest
    # YAML formatter
    go install github.com/google/yamlfmt/cmd/yamlfmt@latest
    # General-purpose language server (used for markdown linting integration)
    go install github.com/mattn/efm-langserver@latest
    # Helm chart LSP
    go install github.com/mrjosh/helm-ls@latest

    success "Go tools done"
else
    warn "go not found — skipping Go tools"
fi

# ---------------------------------------------------------------------------
# Cargo tools
# ---------------------------------------------------------------------------

if has cargo; then
    info "Installing Cargo tools..."

    # TOML LSP + formatter
    cargo install taplo-cli --locked --features lsp
    # Grammar-aware spell checker
    cargo install harper-ls --locked
    # Code formatter (markdown, json, toml, and more)
    cargo install dprint --locked
    # Markdown LSP (wiki-links, references, backlinks)
    # Not on crates.io — must install from git
    cargo install --locked --git https://github.com/Feel-ix-343/markdown-oxide.git markdown-oxide

    success "Cargo tools done"
else
    warn "cargo not found — skipping Cargo tools"
fi

# ---------------------------------------------------------------------------
# Rustup components
# ---------------------------------------------------------------------------

if has rustup; then
    info "Installing Rustup components..."

    rustup component add rust-analyzer

    success "Rustup components done"
else
    warn "rustup not found — skipping Rustup components"
fi

# ---------------------------------------------------------------------------
# npm tools
# ---------------------------------------------------------------------------

if has npm; then
    info "Installing npm tools..."

    npm_install @ansible/ansible-language-server  # Ansible LSP
    npm_install vscode-langservers-extracted       # JSON, HTML, CSS LSPs
    npm_install dockerfile-language-server-nodejs  # Dockerfile LSP
    npm_install @microsoft/compose-language-service # Docker Compose LSP
    npm_install yaml-language-server               # YAML LSP
    npm_install markdownlint-cli                   # Markdown linter
    npm_install prettier                           # Multi-language formatter

    success "npm tools done"
else
    warn "npm not found — skipping npm tools"
fi

# ---------------------------------------------------------------------------
# Python tools (via uv > pipx > pip)
# ---------------------------------------------------------------------------

info "Installing Python tools..."

python_install python-lsp-server  # Python LSP
python_install black              # Python formatter

success "Python tools done"

# ---------------------------------------------------------------------------
# brew-only tools (no language-native installer available)
# ---------------------------------------------------------------------------

info "Installing brew-only tools..."

# Terraform LSP (HashiCorp official — no go install support)
brew_install hashicorp/tap/terraform-ls || true
# Markdown LSP (written in F#/.NET — no language installer)
brew_install marksman || true

success "All done."

if $UPGRADE; then
    echo ""
    info "Upgrade complete. All tools updated to latest versions."
else
    echo ""
    info "Install complete. Run with --upgrade to update existing tools."
fi
