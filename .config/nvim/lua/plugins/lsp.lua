return {
  -- mason lsp config helper
  {
    "williamboman/mason-lspconfig.nvim",
    config = function()
      require("mason-lspconfig").setup {
        ensure_installed = {
          "rust_analyzer",
          "gopls",
          "golangci_lint_ls",
        },
      }
    end,
  },
  {
    "jay-babu/mason-null-ls.nvim",
    event = { "BufReadPre", "BufNewFile" },
    dependencies = {
      "williamboman/mason.nvim",
      "nvimtools/none-ls.nvim",
    },
    config = function()
      require("mason-null-ls").setup {
        ensure_installed = { "gopls", "golangci_lint_ls" },
        methods = {
          diagnostics = true,
          formatting = true,
          code_actions = true,
          completion = true,
          hover = true,
        },
        automatic_installation = false,
      }
    end,
  },
  -- tools installer with mason
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    config = function()
      require("mason-tool-installer").setup {
        ensure_installed = {
          "delve",
          "rust_analyzer",
          "gopls",
          "gomodifytags",
          "gotests",
          "gotestsum",
          "golangci-lint",
          "golangci-lint-langserver",
          "gofumpt",
          "iferr",
          "impl",
          "goimports",
          "bash-language-server",
          "shellcheck",
          "editorconfig-checker",
          "shellcheck",
          "shfmt",
          "staticcheck",
          "markdownlint",
        },
      }
    end,
  },
  -- none ls config
  {
    "nvimtools/none-ls.nvim",
    opts = function(_, opts)
      local nls = require "null-ls"
      opts.root_dir = opts.root_dir
        or require("null-ls.utils").root_pattern(".null-ls-root", ".neoconf.json", "Makefile", ".git")
      opts.sources = vim.list_extend(opts.sources or {}, {
        -- see: https://github.com/nvimtools/none-ls.nvim/blob/main/doc/BUILTINS.md
        nls.builtins.diagnostics.buf, -- protobuf
        nls.builtins.formatting.buf,
        nls.builtins.diagnostics.buildifier, -- bazel build files
        nls.builtins.formatting.buildifier,
        nls.builtins.formatting.stylua,
        nls.builtins.formatting.shfmt,
        nls.builtins.diagnostics.checkmake, -- makefile linter
        nls.builtins.diagnostics.editorconfig_checker, -- conform with editor configs
        -- should be pulled in via it's own ls server nls.builtins.diagnostics.golangci_lint, -- golangci-lint support
        nls.builtins.diagnostics.protolint, -- protobuf linter
        nls.builtins.formatting.protolint,
        nls.builtins.formatting.golines, -- shorten long go lines
      })
    end,
  },
}
