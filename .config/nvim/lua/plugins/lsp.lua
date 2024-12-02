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
  -- tools installer with mason
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    config = function()
      require("mason-tool-installer").setup {
        ensure_installed = {
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
        },
      }
    end,
  },
}
