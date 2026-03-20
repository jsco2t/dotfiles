-- Skip markdownlint on AI tool config files (CLAUDE.md, SKILL.md, AGENTS.md).
-- Uses LazyVim's `condition` extension for nvim-lint linters.

local ignore_files = {
  ["CLAUDE.md"] = true,
  ["SKILL.md"] = true,
  ["AGENTS.md"] = true,
}

return {
  {
    "mfussenegger/nvim-lint",
    opts = {
      linters = {
        ["markdownlint-cli2"] = {
          condition = function(ctx)
            return not ignore_files[vim.fn.fnamemodify(ctx.filename, ":t")]
          end,
        },
      },
    },
  },
}
