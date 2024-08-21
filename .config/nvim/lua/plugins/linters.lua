-- Most linters are added via the community language recipes. These are additions
-- to those linters.
return {
  "mfussenegger/nvim-lint", -- added by: astrocommunity.lsp.nvim-lint
  opts = {
    linters_by_ft = {
      markdown = { "markdownlint" },
    },
  },
}
