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
vim.lsp.enable 'pylsp'
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
vim.lsp.enable 'rust_analyzer'
vim.lsp.enable 'yamlls'
vim.lsp.enable 'protols'

-- For bazel codebases a custom configuration is required for gopls to work. We only
-- want to load the default tooling if a custom config does not exist.
if vim.fn.filereadable './tools/gopackagesdriver.sh' == 0 and vim.fn.filereadable '.nvim.lua' == 0 then
  vim.lsp.enable 'gopls'

  vim.lsp.config('gopls', {
    settings = {
      gopls = {
        gofumpt = true,
        codelenses = {
          gc_details = false,
          generate = true,
          regenerate_cgo = true,
          run_govulncheck = true,
          test = true,
          tidy = true,
          upgrade_dependency = true,
          vendor = true,
        },
        hints = {
          assignVariableTypes = true,
          compositeLiteralFields = true,
          compositeLiteralTypes = true,
          constantValues = true,
          functionTypeParameters = true,
          parameterNames = true,
          rangeVariableTypes = true,
        },
        analyses = {
          nilness = true,
          unusedparams = true,
          unusedwrite = true,
          useany = true,
        },
        usePlaceholders = true,
        completeUnimported = true,
        staticcheck = true,
        directoryFilters = { '-.git', '-.claude', '-.vscode', '-.idea', '-.vscode-test', '-node_modules' },
        semanticTokens = true,
      },
    },
    -- setup = {
    --   on_attach = function(client, bufnr)
    --     -- workaround for gopls not supporting semanticTokensProvider
    --     -- https://github.com/golang/go/issues/54531#issuecomment-1464982242
    --     if client.name == 'gopls' and not client.server_capabilities.semanticTokensProvider then
    --       local semantic = client.config.capabilities.textDocument.semanticTokens
    --       client.server_capabilities.semanticTokensProvider = {
    --         full = true,
    --         legend = {
    --           tokenTypes = semantic.tokenTypes,
    --           tokenModifiers = semantic.tokenModifiers,
    --         },
    --         range = true,
    --       }
    --     end
    --     -- end workaround
    --   end,
    -- },
    setup = {
      gopls = function(_, opts)
        -- workaround for gopls not supporting semanticTokensProvider
        -- https://github.com/golang/go/issues/54531#issuecomment-1464982242

        opts.lsp.on_attach(function(client, _)
          if not client.server_capabilities.semanticTokensProvider then
            local semantic = client.config.capabilities.textDocument.semanticTokens
            client.server_capabilities.semanticTokensProvider = {
              full = true,
              legend = {
                tokenTypes = semantic.tokenTypes,
                tokenModifiers = semantic.tokenModifiers,
              },
              range = true,
            }
          end
        end, 'gopls')
        -- end workaround
      end,
    },
  })

  vim.lsp.enable 'golangci_lint_ls'
end
