return {
  'nvim-treesitter/nvim-treesitter',
  build = ":TSUpdate",
  config = function()
    local config = require('nvim-treesitter.configs')
    config.setup({
      auto_install = true,
      ensure_installed = {
        "bash",
        "go",
        "gomod",
        "gosum",
        "gowork",
        "json",
        "lua",
        "markdown",
        "markdown_inline",
        "proto",
        "python",
        "rust",
        "toml",
        "yaml"
      },
      sync_install = false, -- forces synchronous install
      highlight = { enabled = true },
      indent = { enable = true },
    })
  end
}
