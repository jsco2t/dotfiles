-- Plugin configurations. Runs after vim.pack.add() has made all plugins available.

---------------------------------------------------------------------------
-- Colorscheme (loaded first so UI is styled immediately)
---------------------------------------------------------------------------
require("onedark").setup({
  style = "darker",
  colors = {
    purple = "#726fb5",
  },
})
vim.cmd.colorscheme("onedark")

---------------------------------------------------------------------------
-- Icons (before plugins that consume them)
---------------------------------------------------------------------------
require("mini.icons").setup()
MiniIcons.mock_nvim_web_devicons()

---------------------------------------------------------------------------
-- Treesitter (new main-branch API: install parsers, highlighting is native)
---------------------------------------------------------------------------
require("nvim-treesitter").setup()

local ts_parsers = {
  "bash", "c", "diff", "dockerfile", "go", "gomod", "gosum", "gowork",
  "json", "lua", "luadoc", "markdown", "markdown_inline",
  "python", "query", "regex", "rust", "toml", "vim", "vimdoc", "yaml",
}

local installed = require("nvim-treesitter").get_installed()
local missing = vim.tbl_filter(function(p)
  return not vim.list_contains(installed, p)
end, ts_parsers)

if #missing > 0 then
  require("nvim-treesitter").install(missing)
end

---------------------------------------------------------------------------
-- Statusline
---------------------------------------------------------------------------
require("lualine").setup({
  options = {
    theme = "onedark",
    globalstatus = true,
  },
  sections = {
    lualine_a = { "mode" },
    lualine_b = { "branch", "diff", "diagnostics" },
    lualine_c = { { "filename", path = 1 } },
    lualine_x = { "filetype" },
    lualine_y = { "progress" },
    lualine_z = { "location" },
  },
})

---------------------------------------------------------------------------
-- Git signs
---------------------------------------------------------------------------
require("gitsigns").setup({
  on_attach = function(bufnr)
    local gs = require("gitsigns")
    local function map(mode, l, r, desc)
      vim.keymap.set(mode, l, r, { buffer = bufnr, desc = desc })
    end
    map("n", "]h", function() gs.nav_hunk("next") end, "Next hunk")
    map("n", "[h", function() gs.nav_hunk("prev") end, "Prev hunk")
    map("n", "<leader>ghs", gs.stage_hunk, "Stage hunk")
    map("n", "<leader>ghr", gs.reset_hunk, "Reset hunk")
    map("n", "<leader>ghp", gs.preview_hunk, "Preview hunk")
    map("n", "<leader>ghb", function() gs.blame_line({ full = true }) end, "Blame line")
  end,
})

---------------------------------------------------------------------------
-- File explorer & picker (snacks.nvim)
---------------------------------------------------------------------------
require("snacks").setup({
  bigfile = { enabled = true },
  explorer = { enabled = true },
  indent = { enabled = true },
  notifier = { enabled = true },
  picker = {
    sources = {
      explorer = {
        hidden = true,
        layout = { preset = "sidebar", layout = { width = 30 } },
      },
    },
  },
  quickfile = { enabled = true },
  words = { enabled = true },
})

---------------------------------------------------------------------------
-- Formatting (conform.nvim)
---------------------------------------------------------------------------
require("conform").setup({
  formatters_by_ft = {
    go = { "goimports", "gofumpt" },
    python = { "ruff_format" },
    sh = { "shfmt" },
    bash = { "shfmt" },
    lua = { "stylua" },
    -- Rust/TOML/Docker: handled by LSP via lsp_format fallback
  },
  format_on_save = function(bufnr)
    if vim.g.disable_format_on_save or vim.b[bufnr].disable_format_on_save then
      return
    end
    return {
      timeout_ms = 1000,
      lsp_format = "fallback",
    }
  end,
})

---------------------------------------------------------------------------
-- Linting (nvim-lint)
---------------------------------------------------------------------------
require("lint").linters_by_ft = {
  markdown = { "markdownlint-cli2" },
}

---------------------------------------------------------------------------
-- Mini modules
---------------------------------------------------------------------------
require("mini.ai").setup()
require("mini.pairs").setup()

---------------------------------------------------------------------------
-- Flash (enhanced motions)
---------------------------------------------------------------------------
require("flash").setup()

---------------------------------------------------------------------------
-- Which-key (keymap discovery)
---------------------------------------------------------------------------
require("which-key").setup({
  spec = {
    { "<leader>b", group = "Buffer" },
    { "<leader>c", group = "Code" },
    { "<leader>f", group = "Find" },
    { "<leader>g", group = "Git" },
    { "<leader>q", group = "Quit" },
    { "<leader>s", group = "Search" },
    { "<leader>u", group = "UI" },
    { "<leader>x", group = "Diagnostics" },
  },
})

---------------------------------------------------------------------------
-- Diagnostics UI (trouble.nvim)
---------------------------------------------------------------------------
require("trouble").setup()

---------------------------------------------------------------------------
-- TODO comments
---------------------------------------------------------------------------
require("todo-comments").setup()

---------------------------------------------------------------------------
-- Markdown rendering
---------------------------------------------------------------------------
require("render-markdown").setup()

---------------------------------------------------------------------------
-- Rust (rustaceanvim manages rust-analyzer directly — no lsp/*.lua needed)
---------------------------------------------------------------------------
vim.g.rustaceanvim = {
  server = {
    default_settings = {
      ["rust-analyzer"] = {
        checkOnSave = { command = "clippy" },
      },
    },
  },
}

---------------------------------------------------------------------------
-- Crates (Cargo.toml support)
---------------------------------------------------------------------------
require("crates").setup()

---------------------------------------------------------------------------
-- Python venv selector
---------------------------------------------------------------------------
require("venv-selector").setup()

---------------------------------------------------------------------------
-- Session persistence
---------------------------------------------------------------------------
require("persistence").setup()
