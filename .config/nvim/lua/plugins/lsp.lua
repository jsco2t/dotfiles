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
}
