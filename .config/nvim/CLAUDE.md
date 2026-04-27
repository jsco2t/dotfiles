# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

Neovim 0.12 personal configuration using **native built-in features** for package management, LSP, and completion. No distribution layer (LazyVim) — all configuration is explicit.

### Key Structure
- `init.lua` — Entry point: sets leader, loads config modules, enables LSP servers
- `lua/config/options.lua` — Vim options (loaded before plugins)
- `lua/config/packages.lua` — `vim.pack.add()` with commit-pinned plugin specs
- `lua/config/plugins.lua` — Plugin `setup()` calls and configuration
- `lua/config/autocommands.lua` — Autocommands including LspAttach for native completion
- `lua/config/keymaps.lua` — Custom keymaps
- `lsp/` — Native LSP server configs (`vim.lsp.config` auto-discovered files)

### Native Features (no plugin needed)
- **Package management**: `vim.pack` with `nvim-pack-lock.json` lockfile
- **LSP configuration**: `vim.lsp.config` + `lsp/*.lua` files + `vim.lsp.enable()`
- **Completion**: `vim.lsp.completion.enable` with autotrigger (via LspAttach)
- **Default keymaps**: `grr` (references), `grn` (rename), `gra` (code action), `K` (hover), etc.
- **Commenting**: Native `gc`/`gcc` (treesitter-aware)

### Language Support

Configured via native `lsp/*.lua` files:
- **Go** (`lsp/gopls.lua`) — gopls with gofumpt, staticcheck, analyses
- **Rust** — rustaceanvim manages rust-analyzer directly (no lsp/ file)
- **Python** (`lsp/pyright.lua`, `lsp/ruff.lua`) — pyright for types, ruff for linting
- **Markdown** (`lsp/marksman.lua`) — marksman
- **JSON** (`lsp/jsonls.lua`) — jsonls + SchemaStore.nvim
- **YAML** (`lsp/yamlls.lua`) — yamlls + SchemaStore.nvim
- **TOML** (`lsp/taplo.lua`) — taplo
- **Docker** (`lsp/dockerls.lua`, `lsp/docker_compose_ls.lua`)
- **Bash/Shell** (`lsp/bashls.lua`) — bashls with shellcheck integration

### Plugins (21 total, managed by vim.pack)
All pinned to exact commit hashes. See `lua/config/packages.lua` for the full list.
Key plugins: snacks.nvim (explorer/picker), lualine, gitsigns, conform.nvim (formatting),
nvim-lint, which-key, trouble.nvim, flash.nvim, mini.ai/icons/pairs, nvim-treesitter.

### Supply Chain Posture
- Every plugin pinned to a commit hash in `packages.lua`
- `nvim-pack-lock.json` records installed revisions (track in git)
- No auto-updates; run `vim.pack.update()` to review changes interactively
- LSP servers/formatters/linters installed via system tools, not Mason
- `install-tools.sh` documents all external tool dependencies

### File Explorer
- Uses **snacks.explorer** — Toggle: `<leader>e` or `\`

### Development Commands
- `:lua vim.pack.update()` — Update plugins (shows diff + confirmation)
- `:lua vim.pack.get()` — List installed plugins
- `:lsp` — Manage LSP clients interactively
- `:checkhealth vim.lsp` — Check LSP status
- `:ConformInfo` — Check formatter status
- `./install-tools.sh` — Install all external tools
- `./reset-nvim.sh` — Reset nvim data, state, and cache

### Configuration Notes
- Leader key: `<space>`
- Nerd Font required for icons (mini.icons)
- Local config file support via `exrc` option
- Spell checking enabled
- SSH-aware: animations disabled over SSH
- No DAP configured (preference for CLI debugging)
- Format-on-save enabled (conform.nvim with LSP fallback)
