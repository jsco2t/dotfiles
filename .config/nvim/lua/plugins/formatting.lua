return {
  {
    "stevearc/conform.nvim",
    opts = function()
      local opts = {
        formatters_by_ft = {
          go = { "gofmt", "golines", "goimports" },
          markdown = { "markdownlint" },
        },
      }
    end,
  },
}
