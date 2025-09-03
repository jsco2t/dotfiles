# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a personal Neovim configuration based on kickstart.nvim. The configuration uses Lazy.nvim as the plugin manager and follows a modular structure.

### Key Structure
- `init.lua` - Main entry point, sets leader key and loads all modules in order
- `lua/options.lua` - Core vim options and settings 
- `lua/keymaps.lua` - Basic keybindings and LSP mappings
- `lua/autocommands.lua` - Auto-commands (currently just yank highlighting)
- `lua/lazy-bootstrap.lua` - Lazy.nvim plugin manager bootstrap
- `lua/lazy-plugins.lua` - Main plugin configuration, imports from plugins/ directories
- `lua/plugins/` - Individual plugin configurations organized by functionality
- `lua/plugins/lang/` - Language-specific plugin configurations
- `pack/nvim/start/nvim-lspconfig/` - LSP configurations (pack plugin)

### Plugin Management

Uses Lazy.nvim plugin manager:
- Plugin definitions in `lua/plugins/*.lua` files
- Language-specific plugins in `lua/plugins/lang/*.lua`
- Mason tool installer manages LSP servers and formatters
- Pack plugins used for some LSP servers (see lazy-plugins.lua)

### LSP Configuration

LSP setup handled in multiple places:
- Pack LSP servers enabled directly in `lazy-plugins.lua` (pyright, ruff, pylsp, gopls, etc.)
- Conditional gopls loading based on project-specific configs
- Mason-based LSP server installation in `plugins/lsp.lua`
- Language-specific LSP configs in `plugins/lang/*.lua`

### Development Commands

Plugin management:
- `:Lazy` - Open plugin manager
- `:Lazy update` - Update all plugins
- `:MasonUpdate` - Update Mason registry

Tool management:
- `:Mason` - Open Mason interface for installing tools
- `:ConformInfo` - Check formatter status

Configuration reset:
- `./reset-nvim.sh` - Completely reset nvim data, state, and cache directories

### Key Features

- Telescope fuzzy finder with extensive search capabilities
- LSP with auto-completion via blink.cmp
- Auto-formatting via conform.nvim (stylua, gofumpt, shfmt, etc.)
- Treesitter syntax highlighting
- Git integration via gitsigns
- Terminal integration
- Language support: Lua, Go, Python, Rust, YAML, Protocol Buffers, Shell, Markdown

### Configuration Notes

- Leader key: `<space>`
- Nerd Font required for icons
- Local config file support via `exrc` option
- Spell checking enabled by default
- Clipboard synced with OS
- Auto-format on save (disabled for C/C++)