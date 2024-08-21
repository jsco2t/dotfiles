-- From the go community plugin we already get `gopls, gomodifytags, gotests, iferr, impl`
-- the following are additions which are helpful for go development.

-- return {
--   {
--     "williamboman/mason-lspconfig.nvim",
--     optional = true,
--     opts = function(_, opts)
--       opts.ensure_installed = require("astrocore").list_insert_unique(opts.ensure_installed, { "golangci_lint_ls" })
--     end,
--   },
--   {
--     "WhoIsSethDaniel/mason-tool-installer.nvim",
--     optional = true,
--     opts = function(_, opts)
--       opts.ensure_installed = require("astrocore").list_insert_unique(
--         opts.ensure_installed,
--         { "staticcheck", "gofumpt", "goimports", "golangci_lint_ls" }
--       )
--     end,
--   },
-- }
--

return {
  -- {
  --   "williamboman/mason-lspconfig.nvim",
  --   optional = true,
  --   opts = {
  --     ensure_installed = {
  --       "golangci_lint_ls",
  --     },
  --   },
  -- },
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    --optional = true,
    lazy = true,
    opts = {
      ensure_installed = {
        "staticcheck",
        "gofumpt",
        "goimports",
        "goimports-reviser",
        "golangci_lint",
        "markdownlint",
      },
    },
  },
}
