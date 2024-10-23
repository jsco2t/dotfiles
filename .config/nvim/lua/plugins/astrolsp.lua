---@type LazySpec
return {
  "AstroNvim/astrolsp",
  ---@type AstroLSPOpts
  opts = {
    features = {
      codelens = true, -- enable/disable codelens refresh on start
      inlay_hints = true, -- enable/disable inlay hints on start
      semantic_tokens = true, -- enable/disable semantic token highlighting
      signature_help = true,
    },
    formatting = {
      format_on_save = {
        enabled = true,
      },
    },
    -- based on: https://github.com/AstroNvim/astrocommunity/blob/main/lua/astrocommunity/pack/go/init.lua
    -- included here to disable `ST1003`
    ---@diagnostic disable-next-line: missing-fields
    config = {
      gopls = {
        settings = {
          gopls = {
            analyses = {
              ST1003 = true,
              fieldalignment = false,
              fillreturns = true,
              nilness = true,
              nonewvars = true,
              shadow = true,
              undeclaredname = true,
              unreachable = true,
              unusedparams = true,
              unusedwrite = true,
              useany = true,
            },
            codelenses = {
              gc_details = true, -- Show a code lens toggling the display of gc's choices.
              generate = true, -- show the `go generate` lens.
              regenerate_cgo = true,
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
            buildFlags = { "-tags", "integration" },
            completeUnimported = true,
            diagnosticsDelay = "500ms",
            gofumpt = true,
            matcher = "Fuzzy",
            semanticTokens = true,
            staticcheck = true,
            symbolMatcher = "fuzzy",
            usePlaceholders = true,
          },
        },
      },
    },
  },
}
