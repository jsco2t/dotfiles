return {
  {
    'nvim-treesitter/nvim-treesitter',
    opts = { ensure_installed = { 'go', 'gomod', 'gowork', 'gosum' } },
  },
  -- Ensure Go tools are installed
  {
    'mason-org/mason.nvim',
    opts = { ensure_installed = { 'goimports', 'gofumpt', 'gopls', 'gomodifytags' } },
  },
  {
    'nvimtools/none-ls.nvim',
    optional = true,
    dependencies = {
      {
        'mason-org/mason.nvim',
      },
    },
    opts = function(_, opts)
      local nls = require 'null-ls'
      opts.sources = vim.list_extend(opts.sources or {}, {
        nls.builtins.code_actions.gomodifytags,
        nls.builtins.code_actions.impl,
        nls.builtins.formatting.goimports,
        nls.builtins.formatting.gofumpt,
      })
    end,
  },
  {
    'stevearc/conform.nvim',
    optional = true,
    opts = {
      formatters_by_ft = {
        go = { 'goimports', 'gofumpt' },
      },
    },
  },
  {
    'mfussenegger/nvim-dap',
    optional = true,
    dependencies = {
      {
        'mason-org/mason.nvim',
        opts = { ensure_installed = { 'delve' } },
      },
      {
        'leoluz/nvim-dap-go',
        opts = {},
      },
    },
  },
  {
    'nvim-neotest/neotest',
    optional = true,
    dependencies = {
      'fredrikaverpil/neotest-golang',
    },
    opts = {
      adapters = {
        ['neotest-golang'] = {
          -- Here we can set options for neotest-golang, e.g.
          -- go_test_args = { "-v", "-race", "-count=1", "-timeout=60s" },
          dap_go_enabled = true, -- requires leoluz/nvim-dap-go
        },
      },
    },
  },
}
