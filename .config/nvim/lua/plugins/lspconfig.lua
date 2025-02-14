-- LSP Support requires a few external dependencies
--
--  The `nvim` command: `:checkhealth` can be use to diagnose issues.
--  It's recommended that at least the following be installed:
--    - Node/Node Version Manager: https://github.com/nvm-sh/nvm?tab=readme-ov-file#installing-and-updating
--    - `tree-sitter cli`: cargo install tree-sitter-cli
--    - Python dependencies: sudo apt install python3-pip python3-pynvim
--    - ripgrep: sudo apt install ripgrep

return {
  -- mason lsp config helper
  {
    'williamboman/mason-lspconfig.nvim',
    config = function()
      require('mason-lspconfig').setup {
        ensure_installed = {
          'rust_analyzer',
          'gopls',
          'golangci_lint_ls',
        },
      }
    end,
  },
  { -- LSP Configuration & Plugins
    'neovim/nvim-lspconfig',
    dependencies = {
      -- Automatically install LSPs and related tools to stdpath for Neovim
      { 'williamboman/mason.nvim', config = true }, -- NOTE: Must be loaded before dependents
      'williamboman/mason-lspconfig.nvim',
      'WhoIsSethDaniel/mason-tool-installer.nvim',

      -- Useful status updates for LSP.
      -- NOTE: `opts = {}` is the same as calling `require('fidget').setup({})`
      { 'j-hui/fidget.nvim', opts = {} },

      {
        'folke/lazydev.nvim',
        ft = 'lua', -- only load on lua files
        opts = {
          library = {
            'LazyVim',
          },
        },
      },
      { -- optional completion source for require statements and module annotations
        'hrsh7th/nvim-cmp',
        opts = function(_, opts)
          opts.sources = opts.sources or {}
          table.insert(opts.sources, {
            name = 'lazydev',
            group_index = 0, -- set group index to 0 to skip loading LuaLS completions
          })
        end,
      },
    },
    config = function()
      vim.api.nvim_create_autocmd('LspAttach', {
        group = vim.api.nvim_create_augroup('kickstart-lsp-attach', { clear = true }),
        callback = function(event)
          -- NOTE: Remember that Lua is a real programming language, and as such it is possible
          -- to define small helper and utility functions so you don't have to repeat yourself.
          --
          -- In this case, we create a function that lets us more easily define mappings specific
          -- for LSP related items. It sets the mode, buffer and description for us each time.
          local map = function(keys, func, desc)
            vim.keymap.set('n', keys, func, { buffer = event.buf, desc = 'LSP: ' .. desc })
          end

          -- Jump to the definition of the word under your cursor.
          --  This is where a variable was first declared, or where a function is defined, etc.
          --  To jump back, press <C-t>.
          --map('gd', require('telescope.builtin').lsp_definitions, '[G]oto [D]efinition')

          -- Find references for the word under your cursor.
          --map('gr', require('telescope.builtin').lsp_references, '[G]oto [R]eferences')

          -- Jump to the implementation of the word under your cursor.
          --  Useful when your language has ways of declaring types without an actual implementation.
          --map('gI', require('telescope.builtin').lsp_implementations, '[G]oto [I]mplementation')

          -- Jump to the type of the word under your cursor.
          --  Useful when you're not sure what type a variable is and you want to see
          --  the definition of its *type*, not where it was *defined*.
          --map('<leader>D', require('telescope.builtin').lsp_type_definitions, 'Type [D]efinition')

          -- Fuzzy find all the symbols in your current document.
          --  Symbols are things like variables, functions, types, etc.
          --map('<leader>ds', require('telescope.builtin').lsp_document_symbols, '[D]ocument [S]ymbols')

          -- Fuzzy find all the symbols in your current workspace.
          --  Similar to document symbols, except searches over your entire project.
          --map('<leader>ws', require('telescope.builtin').lsp_dynamic_workspace_symbols, '[W]orkspace [S]ymbols')

          -- Rename the variable under your cursor.
          --  Most Language Servers support renaming across files, etc.
          map('<leader>rn', vim.lsp.buf.rename, '[R]e[n]ame')

          -- Execute a code action, usually your cursor needs to be on top of an error
          -- or a suggestion from your LSP for this to activate.
          map('<leader>ca', vim.lsp.buf.code_action, '[C]ode [A]ction')

          -- Opens a popup that displays documentation about the word under your cursor
          --  See `:help K` for why this keymap.
          map('K', vim.lsp.buf.hover, 'Hover Documentation')

          -- WARN: This is not Goto Definition, this is Goto Declaration.
          --  For example, in C this would take you to the header.
          -- The following two autocommands are used to highlight references of the
          -- word under your cursor when your cursor rests there for a little while.
          --    See `:help CursorHold` for information about when this is executed
          --
          -- When you move your cursor, the highlights will be cleared (the second autocommand).
          local client = vim.lsp.get_client_by_id(event.data.client_id)
          if client and client.supports_method(vim.lsp.protocol.Methods.textDocument_documentHighlight) then
            local highlight_augroup = vim.api.nvim_create_augroup('kickstart-lsp-highlight', { clear = false })
            vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
              buffer = event.buf,
              group = highlight_augroup,
              callback = vim.lsp.buf.document_highlight,
            })

            vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
              buffer = event.buf,
              group = highlight_augroup,
              callback = vim.lsp.buf.clear_references,
            })

            vim.api.nvim_create_autocmd('LspDetach', {
              group = vim.api.nvim_create_augroup('kickstart-lsp-detach', { clear = true }),
              callback = function(event2)
                vim.lsp.buf.clear_references()
                vim.api.nvim_clear_autocmds { group = 'kickstart-lsp-highlight', buffer = event2.buf }
              end,
            })
          end

          -- This may be unwanted, since they displace some of your code
          vim.lsp.inlay_hint.enable(true, { bufnr = event.buf })
          if client and client.supports_method(vim.lsp.protocol.Methods.textDocument_inlayHint) then
            map('<leader>th', function()
              vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = event.buf })
            end, '[T]oggle Inlay [H]ints')
          end

          if client and client.name == 'gopls' then
            local semantic = client.config.capabilities.textDocument.semanticTokens
            if semantic then
              client.server_capabilities.semanticTokensProvider = {
                full = true,
                legend = { tokenModifiers = semantic.tokenModifiers, tokenTypes = semantic.tokenTypes },
                range = true,
              }
            end
          end
        end,
      })

      local capabilities = vim.lsp.protocol.make_client_capabilities()
      capabilities = vim.tbl_deep_extend('force', capabilities, require('cmp_nvim_lsp').default_capabilities())

      local servers = {
        --clangd = {}, -- not available on arm/raspi
        --gopls = {},
        gopls = {
          settings = {
            gopls = {
              env = {
                GOPACKAGESDRIVER = './tools/gopackagesdriver.sh',
              },
              codelenses = {
                gc_details = false,
                generate = false,
                regenerate_cgo = false,
                run_govulncheck = false,
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
              -- defaults from gopls for analyzer's looks fine
              -- analyses = {
              --   --fieldalignment = true,
              --   nilness = true,
              --   unusedparams = true,
              --   unusedwrite = true,
              --   useany = true,
              --   assign = true,
              --   bools = true,
              -- },
              usePlaceholders = true,
              completeUnimported = true,
              directoryFilters = {
                '-.git',
                '-.vscode',
                '-.idea',
                '-.vscode-test',
                '-node_modules',
                '-bazel-bin',
                '-bazel-out',
                '-bazel-testlogs',
                '-baze-mypkg',
              },
              semanticTokens = true,
            },
          },
        },
        pyright = {},
        rust_analyzer = {},
        lua_ls = {
          -- cmd = {...},
          -- filetypes = { ...},
          -- capabilities = {},
          settings = {
            Lua = {
              completion = {
                callSnippet = 'Replace',
              },
              -- You can toggle below to ignore Lua_LS's noisy `missing-fields` warnings
              diagnostics = { disable = { 'missing-fields' } },
            },
          },
        },
      }

      -- Ensure the servers and tools above are installed
      --  To check the current status of installed tools and/or manually install
      --  other tools, you can run
      --    :Mason
      --
      --  You can press `g?` for help in this menu.
      require('mason').setup()

      -- You can add other tools here that you want Mason to install
      -- for you, so that they are available from within Neovim.
      local ensure_installed = vim.tbl_keys(servers or {})
      vim.list_extend(ensure_installed, {
        'stylua', -- Used to format Lua code
        'shellcheck', -- used for bash script checking
        'shellharden', -- another bash script checker
        'staticcheck', -- checks golang code
        'gopls',
        'gofumpt', -- go formatting
        'goimports', -- organizes golang imports
        'golines', -- fix long lines in go
        'bash-language-server',
        --'golangci-lint',
        'pylint', -- formats/lints python
        'markdownlint', -- linter for markdown - requires node to be installed
        'isort', -- python
        'black', -- python
        'rustfmt', -- for rust
      })
      require('mason-tool-installer').setup { ensure_installed = ensure_installed }

      require('mason-lspconfig').setup {
        ensure_installed = {
          'rust_analyzer',
          'gopls',
          --'golangci_lint_ls',
        },
        automatic_installation = true,
        handlers = {
          function(server_name)
            local server = servers[server_name] or {}
            -- This handles overriding only values explicitly passed
            -- by the server configuration above. Useful when disabling
            -- certain features of an LSP (for example, turning off formatting for tsserver)
            server.capabilities = vim.tbl_deep_extend('force', {}, capabilities, server.capabilities or {})
            require('lspconfig')[server_name].setup(server)
          end,
        },
      }
    end,
  },

  {
    'jay-babu/mason-null-ls.nvim',
    event = { 'BufReadPre', 'BufNewFile' },
    dependencies = {
      'williamboman/mason.nvim',
      'nvimtools/none-ls.nvim',
    },
    config = function()
      local null_ls = require 'null-ls'
      null_ls.setup()

      require('mason-null-ls').setup {
        ensure_installed = {},
        methods = {
          diagnostics = true,
          formatting = true,
          code_actions = true,
          completion = true,
          hover = true,
        },
        automatic_installation = false,
        handlers = {
          function() end, -- disables automatic setup of all null-ls sources !! IMPORTANT !!
          golangci_lint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.golangci_lint.with {
              condition = function(utils)
                return utils.root_has_file { 'BUILD.bazel' } == false
              end,
            })
          end,

          staticcheck = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.staticcheck.with {
              condition = function(utils)
                return utils.root_has_file { 'BUILD.bazel' } == false
              end,
            })
          end,

          ansiblelint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.ansiblelint)
          end,
          buf = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.buf)
          end,
          buildifier = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.buildifier)
          end,
          markdownlint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.markdownlint)
          end,
          protolint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.protolint)
          end,
          pylint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.pylint)
          end,
          yamllint = function(source_name, methods)
            null_ls.register(null_ls.builtins.diagnostics.yamllint)
          end,

          black = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.black)
          end,
          buf_fmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.buf)
          end,
          buildifier_fmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.buildifier)
          end,
          gofmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.gofmt)
          end,
          goimports = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.goimports)
          end,
          goimports_reviser = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.goimports_reviser)
          end,
          golines = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.golines)
          end,
          markdownlint_fmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.markdownlint)
          end,
          opentofu_fmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.opentofu_fmt)
          end,
          prettier = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.prettier)
          end,
          protolint_fmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.protolint)
          end,
          shellharden = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.shellharden)
          end,
          shfmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.shfmt)
          end,
          yamlfmt = function(source_name, methods)
            null_ls.register(null_ls.builtins.formatting.yamlfmt)
          end,
        },
      }
    end,
  },
}
