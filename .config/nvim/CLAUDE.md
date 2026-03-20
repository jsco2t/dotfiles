# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a personal Neovim configuration built on [LazyVim](https://www.lazyvim.org/) with [Lazy.nvim](https://github.com/folke/lazy.nvim) as the plugin manager.

### Key Structure
- `init.lua` — Entry point, loads `config.lazy`
- `lua/config/lazy.lua` — Lazy.nvim bootstrap and plugin spec (extras, defaults, performance)
- `lua/config/options.lua` — Options that differ from LazyVim defaults (loaded before plugins)
- `lua/config/keymaps.lua` — Custom keymaps (loaded on VeryLazy)
- `lua/config/autocommands.lua` — Custom autocommands (loaded on VeryLazy)
- `lua/plugins/` — User plugin specs (merged with LazyVim defaults)

### Language Support

Configured via LazyVim extras in `lua/config/lazy.lua`:
- **Go** (`lang.go`) — gopls, gofumpt, goimports
- **Rust** (`lang.rust`) — rust-analyzer
- **Python** (`lang.python`) — pyright, ruff
- **Markdown** (`lang.markdown`) — marksman
- **JSON** (`lang.json`) — jsonls + schemastore
- **YAML** (`lang.yaml`) — yamlls
- **TOML** (`lang.toml`) — taplo
- **Docker** (`lang.docker`) — dockerls, docker-compose-ls

Custom (no LazyVim extra):
- **Bash/Shell** (`plugins/lang-bash.lua`) — bashls, shellcheck, shfmt

### Plugin Customizations (`lua/plugins/`)
- `colorscheme.lua` — onedark theme (darker variant, custom purple)
- `disabled.lua` — Disables noice.nvim and bufferline
- `lang-bash.lua` — Bash LSP, linting, formatting

### File Explorer
- Uses **snacks.explorer** (LazyVim default for install_version 8)
- Toggle: `<leader>e`

### Development Commands
- `:Lazy` — Plugin manager UI
- `:Lazy update` — Update all plugins
- `:Mason` — Tool installer UI
- `:ConformInfo` — Check formatter status
- `./reset-nvim.sh` — Reset nvim data, state, and cache

### Configuration Notes
- Leader key: `<space>`
- Nerd Font required for icons
- Local config file support via `exrc` option
- Spell checking enabled
- SSH-aware: animations disabled over SSH, clipboard handled by LazyVim
- No DAP configured (preference for CLI debugging)
- Disabled plugins: noice.nvim, bufferline, netrwPlugin
