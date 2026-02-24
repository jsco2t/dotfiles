#!/usr/bin/env bash
set -euo pipefail

# Yazi file manager dependencies
# Works on macOS, Debian, and Rocky Linux
#
# Strategy:
#   macOS  — brew for everything
#   Debian — apt for jq, yq, fd-find, ripgrep, fzf; brew for zoxide, yazi
#   Rocky  — dnf (+ EPEL) for jq, yq, fd-find, ripgrep, fzf; brew for zoxide, yazi
#
# Idempotency: Safe to re-run at any time.
#   - Native package managers skip already-installed packages
#   - brew installs if missing; upgrades only with --upgrade flag

UPGRADE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install dependencies for the Yazi file manager.

Options:
  --upgrade, -u   Upgrade all dependencies to latest versions
                  (Without this flag, already-installed brew packages are skipped)
  --help, -h      Show this help message
EOF
}

for arg in "$@"; do
    case "$arg" in
        --upgrade | -u) UPGRADE=true ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            usage
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

has() { command -v "$1" &>/dev/null; }
info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$1"; }
success() { printf '\033[1;32m✓\033[0m %s\n' "$1"; }

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
        warn "brew not found — skipping $pkg (install Homebrew: https://brew.sh)"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Detect OS
# ---------------------------------------------------------------------------

OS="$(uname -s)"
DISTRO=""

if [[ "$OS" == "Linux" && -f /etc/os-release ]]; then
    DISTRO=$(. /etc/os-release && echo "$ID")
fi

info "Detected: OS=$OS DISTRO=${DISTRO:-n/a}"

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

case "$OS" in
    Darwin)
        info "Installing all dependencies via brew..."
        for pkg in jq yq fd ripgrep fzf zoxide yazi; do
            brew_install "$pkg" || true
        done
        success "All dependencies installed."
        ;;

    Linux)
        # -- Native packages via system package manager -----------------------
        NATIVE_PKGS=(jq yq fd-find ripgrep fzf)

        case "$DISTRO" in
            debian | ubuntu)
                info "Installing native packages via apt..."
                sudo apt-get update -qq
                sudo apt-get install -y "${NATIVE_PKGS[@]}"
                success "Native packages installed via apt."
                ;;
            rocky | rhel | centos | almalinux)
                info "Enabling EPEL repository..."
                sudo dnf install -y epel-release
                info "Installing native packages via dnf..."
                sudo dnf install -y "${NATIVE_PKGS[@]}"
                success "Native packages installed via dnf."
                ;;
            *)
                warn "Unsupported Linux distro: $DISTRO — falling back to brew for all packages"
                for pkg in jq yq fd ripgrep fzf; do
                    brew_install "$pkg" || true
                done
                ;;
        esac

        # -- zoxide and yazi via brew (not in standard repos) ------------------
        info "Installing zoxide and yazi via brew..."
        brew_install zoxide || true
        brew_install yazi || true
        success "zoxide and yazi installed via brew."
        ;;

    *)
        warn "Unsupported OS: $OS"
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
if $UPGRADE; then
    info "Upgrade complete. All tools updated to latest versions."
else
    info "Install complete. Run with --upgrade to update existing tools."
fi

info "Installing plugins..."
ya pkg add yazi-rs/plugins:git
ya pkg add yazi-rs/plugins:vcs-files
