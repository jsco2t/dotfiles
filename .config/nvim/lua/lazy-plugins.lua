-- [[ Configure and install plugins ]]
--
--  To check the current status of your plugins, run
--    :Lazy
--
--  You can press `?` in this menu for help. Use `:q` to close the window
--
--  To update plugins you can run
--    :Lazy update
--
require('lazy').setup({

  --'NMAC427/guess-indent.nvim', -- Detect tabstop and shiftwidth automatically

  { import = 'plugins' },
  { import = 'plugins/lang' },
}, {
  ui = {
    -- If you are using a Nerd Font: set icons to an empty table which will use the
    -- default lazy.nvim defined Nerd Font icons, otherwise define a unicode icons table
    icons = vim.g.have_nerd_font and {} or {
      cmd = '⌘',
      config = '🛠',
      event = '📅',
      ft = '📂',
      init = '⚙',
      keys = '🗝',
      plugin = '🔌',
      runtime = '💻',
      require = '🌙',
      source = '📄',
      start = '🚀',
      task = '📌',
      lazy = '💤 ',
    },
  },
})

-- pack plugins
-- https://github.com/neovim/nvim-lspconfig/blob/master/doc/configs.md
vim.lsp.enable 'pyright'
vim.lsp.enable 'ruff'
--vim.lsp.enable 'pylsp'
vim.lsp.config('pylsp', {
  settings = {
    pylsp = {
      plugins = {
        pycodestyle = {
          ignore = { 'W391' },
          maxLineLength = 100,
        },
      },
    },
  },
})
vim.lsp.enable 'gopls'
vim.lsp.enable 'golangci_lint_ls'
vim.lsp.enable 'rust_analyzer'
vim.lsp.enable 'yamlls'
vim.lsp.enable 'protols'
vim.lsp.enable 'bzl'
