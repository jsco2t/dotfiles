-- AstroCommunity: import any community modules here
-- We import this file in `lazy_setup.lua` before the `plugins/` folder.
-- This guarantees that the specs are processed before any user plugins.

---@type LazySpec
return {
  "AstroNvim/astrocommunity",
  { import = "astrocommunity.pack.lua" },

  -- statusline config
  --{ import = "astrocommunity.recipes.heirline-mode-text-statusline" }, -- see statusline.lua - done manually

  -- tabline config
  { import = "astrocommunity.recipes.disable-tabline" },

  -- themes
  -- { import = "astrocommunity.colorscheme.nordic-nvim" }, -- see /lua/plugins/theme.lua
  -- { import = "astrocommunity.colorscheme.sonokai" },
  -- { import = "astrocommunity.colorscheme.tokyonight-nvim" },
  -- { import = "astrocommunity.colorscheme.catppuccin" },

  -- dev tools
  { import = "astrocommunity.pack.rust" },
  { import = "astrocommunity.pack.python" },
  { import = "astrocommunity.pack.go" },
  { import = "astrocommunity.pack.bash" },
  { import = "astrocommunity.pack.markdown" },
  { import = "astrocommunity.recipes.telescope-lsp-mappings" },

  -- linting support
  { import = "astrocommunity.lsp.nvim-lint" },

  -- issues and diagnostics
  { import = "astrocommunity.diagnostics.trouble-nvim" },
}
