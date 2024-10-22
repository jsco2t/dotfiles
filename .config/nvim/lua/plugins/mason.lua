return {
  {
    "williamboman/mason-lspconfig.nvim",
    optional = true,
    opts = function(_, opts)
      opts.ensure_installed = require("astrocore").list_insert_unique(opts.ensure_installed, {
        "golangci_lint_ls",
        "gopls",
      })
    end,
  },
  {
    "jay-babu/mason-null-ls.nvim",
    optional = true,
    opts = function(_, opts)
      opts.ensure_installed = require("astrocore").list_insert_unique(opts.ensure_installed, {
        "editorconfig-checker",
        "golangci_lint",
        "goimports",
      })
    end,
  },
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    optional = true,
    opts = function(_, opts)
      opts.ensure_installed = require("astrocore").list_insert_unique(opts.ensure_installed, {
        "delve",
        "gopls",
        "gomodifytags",
        "gotests",
        "iferr",
        "impl",
        "goimports",
        "staticcheck",
        "gofumpt",
        "goimports",
        "goimports-reviser",
        "golangci_lint",
        "markdownlint",
        "editorconfig-checker",
        "gotestsum",
      })
    end,
  },
}

-- BUG: missing from clean install:
--
--  gofumpt
--  gotestsum
--  staticcheck
