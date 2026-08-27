-- ============================================================================
--  init.lua
-- ----------------------------------------------------------------------------
--  Requires: Neovim >= 0.12  (vim.pack, vim.lsp.enable, lsp/*.lua discovery)
--
--  Philosophy
--    * Everything is pinned. Two lockfiles live next to this file and MUST be
--      committed to git:
--          nvim-pack-lock.json   -- plugin commit SHAs (managed by vim.pack)
--          mason-lock.json       -- language server / tool versions
--      Nothing updates unless you run :PluginUpdate or :MasonLock yourself.
--    * Prefer core, then mini.nvim, then a third-party plugin. In that order.
--    * One file. If it doesn't fit in one file, it's probably too much config.
--
--  Update workflow
--      git checkout -b nvim-update
--      :PluginUpdate          -- review the diff buffer, then confirm
--      :MasonToolsUpdate      -- optional; then :MasonLock to re-pin
--      <use it for a day>
--      git add -A && git commit   (or: git reset --hard && :PluginRestore)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Leader keys. Must be set before any plugin loads.
-- ----------------------------------------------------------------------------
vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

-- Bytecode cache for Lua modules. Meaningful startup win, zero downside.
vim.loader.enable()

-- ----------------------------------------------------------------------------
-- 1. Options
-- ----------------------------------------------------------------------------
local opt = vim.opt

opt.number = true
opt.number = true
opt.relativenumber = false
opt.signcolumn = "yes" -- never shift the text when diagnostics appear
opt.cursorline = true
opt.scrolloff = 8
opt.sidescrolloff = 8
opt.wrap = false
opt.linebreak = true
opt.colorcolumn = "100"

opt.expandtab = true
opt.shiftwidth = 2
opt.tabstop = 2
opt.softtabstop = 2
opt.smartindent = true
opt.shiftround = true

opt.ignorecase = true
opt.smartcase = true
opt.inccommand = "split" -- live preview of :s
opt.hlsearch = true

opt.splitright = true
opt.splitbelow = true
opt.splitkeep = "screen"

opt.undofile = true
opt.swapfile = false
opt.backup = false
opt.updatetime = 250 -- drives CursorHold, document highlight
opt.timeoutlen = 400
opt.confirm = true -- prompt instead of failing on :q with changes

opt.termguicolors = true
opt.pumheight = 12
opt.pumblend = 0
opt.winborder = "rounded" -- 0.11+: default border for all floats
opt.completeopt = "menuone,noselect,fuzzy,nosort"
opt.list = true
opt.listchars = { tab = "» ", trail = "·", nbsp = "␣" }
opt.fillchars = { eob = " ", fold = " ", foldopen = "▾", foldclose = "▸" }

opt.mouse = "a"
opt.clipboard = "unnamedplus"
opt.shortmess:append("cI") -- no completion noise, no intro screen

-- Folds: treesitter-driven, but start fully open. Nothing worse than opening a
-- file and finding it collapsed.
opt.foldmethod = "expr"
opt.foldexpr = "v:lua.vim.treesitter.foldexpr()"
opt.foldtext = ""
opt.foldlevel = 99
opt.foldlevelstart = 99

-- Go and Rust use tabs / 4 spaces respectively; handled per-filetype below.

-- ----------------------------------------------------------------------------
-- 2. Plugins  (vim.pack — built in, no bootstrap needed)
-- ----------------------------------------------------------------------------
-- `version` controls what :PluginUpdate moves *toward*. The lockfile controls
-- what you actually have checked out right now. Semver range = stable tags only.
local range = vim.version.range

vim.pack.add({
  -- --- The mini.nvim suite -------------------------------------------------
  -- Installed as one package; individual modules are enabled in section 4.
  { src = "https://github.com/nvim-mini/mini.nvim", version = range("*") },

  -- --- Syntax / parsing ----------------------------------------------------
  -- nvim-treesitter `main` branch. The old `master` branch is frozen; `main`
  -- has no module system, so highlighting is started manually (section 5).
  { src = "https://github.com/nvim-treesitter/nvim-treesitter", version = "main" },
  { src = "https://github.com/nvim-treesitter/nvim-treesitter-textobjects", version = "main" },

  -- --- LSP -----------------------------------------------------------------
  -- lspconfig is data-only now: it ships lsp/<server>.lua definitions that
  -- vim.lsp.enable() picks up off the runtimepath. We never call its setup().
  { src = "https://github.com/neovim/nvim-lspconfig", version = range("*") },
  { src = "https://github.com/mason-org/mason.nvim", version = range("*") },
  { src = "https://github.com/zapling/mason-lock.nvim" },

  -- --- Language-specific ---------------------------------------------------
  { src = "https://github.com/mrcjkb/rustaceanvim", version = range("*") },

  -- --- Format / lint -------------------------------------------------------
  { src = "https://github.com/stevearc/conform.nvim", version = range("*") },
  { src = "https://github.com/mfussenegger/nvim-lint" },

  -- --- Debugging (minimal: no dap-ui) --------------------------------------
  { src = "https://github.com/mfussenegger/nvim-dap" },
  { src = "https://github.com/leoluz/nvim-dap-go" },

  -- --- Documents -----------------------------------------------------------
  { src = "https://github.com/MeanderingProgrammer/render-markdown.nvim", version = range("*") },

  -- --- Colorscheme ---------------------------------------------------------
  { src = "https://github.com/folke/tokyonight.nvim", version = range("*") },
})

vim.cmd.colorscheme("tokyonight-night")

-- Update commands. Nothing here runs on its own.
local uc = vim.api.nvim_create_user_command
uc("PluginUpdate", function()
  vim.pack.update()
end, { desc = "Fetch plugin updates and show a reviewable diff" })
uc("PluginStatus", function()
  vim.pack.update(nil, { force = false })
end, { desc = "Show pending plugin changes without applying" })
uc("PluginRestore", function()
  vim.pack.update(nil, { target = "lockfile", force = true })
end, { desc = "Hard-reset every plugin to nvim-pack-lock.json" })
uc("PluginClean", function()
  local active = {}
  for _, p in ipairs(vim.pack.get()) do
    active[p.spec.name] = p.active
  end
  local dead = vim.tbl_filter(function(n)
    return not active[n]
  end, vim.tbl_keys(active))
  if #dead == 0 then
    return vim.notify("No unused plugins", vim.log.levels.INFO)
  end
  vim.pack.del(dead)
end, { desc = "Remove plugins no longer listed in init.lua" })

-- ----------------------------------------------------------------------------
-- 3. Diagnostics
-- ----------------------------------------------------------------------------
vim.diagnostic.config({
  severity_sort = true,
  update_in_insert = false,
  underline = { severity = { min = vim.diagnostic.severity.WARN } },
  -- Inline text for warnings and above; the full multi-line view is on <leader>d.
  virtual_text = {
    severity = { min = vim.diagnostic.severity.WARN },
    source = "if_many",
    prefix = "●",
  },
  float = { border = "rounded", source = "if_many", header = "" },
  signs = {
    text = {
      [vim.diagnostic.severity.ERROR] = "󰅚 ",
      [vim.diagnostic.severity.WARN] = "󰀪 ",
      [vim.diagnostic.severity.INFO] = "󰋽 ",
      [vim.diagnostic.severity.HINT] = "󰌶 ",
    },
  },
})

-- ----------------------------------------------------------------------------
-- 4. mini.nvim
-- ----------------------------------------------------------------------------
require("mini.icons").setup()
MiniIcons.mock_nvim_web_devicons() -- so third-party plugins find icons

require("mini.notify").setup({
  lsp_progress = { enable = true },
  window = { config = { border = "rounded" } },
})
vim.notify = MiniNotify.make_notify()

require("mini.statusline").setup({ use_icons = true })
require("mini.tabline").setup()

-- Editing
require("mini.ai").setup({ n_lines = 500 }) -- better a/i textobjects
require("mini.surround").setup() -- gsa / gsd / gsr
require("mini.pairs").setup()
require("mini.splitjoin").setup() -- gS — great on Go structs
require("mini.move").setup() -- Alt-hjkl to move lines/blocks
require("mini.operators").setup() -- g= gx gm gr gs (eval/exchange/multiply/replace/sort)
require("mini.bracketed").setup() -- ]d [d ]q [q ]b [b ...
require("mini.trailspace").setup()

-- Snippets — required for LSP snippet expansion via mini.completion
require("mini.snippets").setup({
  snippets = { require("mini.snippets").gen_loader.from_lang() },
})

-- Completion. Two-stage: LSP first, fallback to buffer words.
require("mini.completion").setup({
  delay = { completion = 100, info = 100, signature = 50 },
  window = {
    info = { height = 25, width = 80, border = "rounded" },
    signature = { height = 25, width = 80, border = "rounded" },
  },
  lsp_completion = {
    source_func = "omnifunc",
    auto_setup = false, -- we set omnifunc per-buffer on LspAttach instead
    snippet_insert = function(snippet)
      MiniSnippets.default_insert(snippet)
    end,
    -- Drop snippet items that duplicate a plain LSP item, and sort by LSP order.
    process_items = function(items, base)
      return MiniCompletion.default_process_items(items, base, { filtersort = "fuzzy" })
    end,
  },
  fallback_action = "<C-x><C-n>",
})

-- Pickers
require("mini.extra").setup()
require("mini.pick").setup({
  mappings = {
    move_down = "<C-j>",
    move_up = "<C-k>",
  },
  options = { use_cache = true },
  window = {
    config = function()
      local h = math.floor(0.618 * vim.o.lines)
      local w = math.floor(0.8 * vim.o.columns)
      return {
        anchor = "NW",
        height = h,
        width = w,
        row = math.floor(0.5 * (vim.o.lines - h)),
        col = math.floor(0.5 * (vim.o.columns - w)),
        border = "rounded",
      }
    end,
  },
})
vim.ui.select = MiniPick.ui_select

-- File explorer
require("mini.files").setup({
  windows = { preview = true, width_preview = 60 },
  options = { permanent_delete = false }, -- deletes go to a trash dir
})

-- Git
require("mini.diff").setup({ view = { style = "sign", signs = { add = "▎", change = "▎", delete = "▁" } } })
require("mini.git").setup()

-- Misc quality-of-life
require("mini.misc").setup()
MiniMisc.setup_auto_root({ ".git", "go.work", "go.mod", "Cargo.toml", "pyproject.toml", "package.json" })
MiniMisc.setup_restore_cursor()

require("mini.hipatterns").setup({
  highlighters = {
    fixme = { pattern = "%f[%w]()FIXME()%f[%W]", group = "MiniHipatternsFixme" },
    hack = { pattern = "%f[%w]()HACK()%f[%W]", group = "MiniHipatternsHack" },
    todo = { pattern = "%f[%w]()TODO()%f[%W]", group = "MiniHipatternsTodo" },
    note = { pattern = "%f[%w]()NOTE()%f[%W]", group = "MiniHipatternsNote" },
    hex_color = require("mini.hipatterns").gen_highlighter.hex_color(),
  },
})

-- Keymap discovery (which-key equivalent)
local clue = require("mini.clue")
clue.setup({
  triggers = {
    { mode = "n", keys = "<Leader>" },
    { mode = "x", keys = "<Leader>" },
    { mode = "n", keys = "g" },
    { mode = "x", keys = "g" },
    { mode = "n", keys = "]" },
    { mode = "n", keys = "[" },
    { mode = "n", keys = "<C-w>" },
    { mode = "n", keys = "z" },
    { mode = "n", keys = '"' },
    { mode = "x", keys = '"' },
    { mode = "i", keys = "<C-r>" },
  },
  clues = {
    clue.gen_clues.builtin_completion(),
    clue.gen_clues.g(),
    clue.gen_clues.marks(),
    clue.gen_clues.registers(),
    clue.gen_clues.windows(),
    clue.gen_clues.z(),
    { mode = "n", keys = "<Leader>f", desc = "+Find" },
    { mode = "n", keys = "<Leader>g", desc = "+Git" },
    { mode = "n", keys = "<Leader>l", desc = "+LSP" },
    { mode = "n", keys = "<Leader>d", desc = "+Debug" },
    { mode = "n", keys = "<Leader>c", desc = "+Code" },
    { mode = "n", keys = "<Leader>t", desc = "+Toggle" },
  },
  window = { delay = 300, config = { border = "rounded", width = "auto" } },
})

-- ----------------------------------------------------------------------------
-- 5. Treesitter
-- ----------------------------------------------------------------------------
local ts_parsers = {
  "bash",
  "c",
  "comment",
  "css",
  "diff",
  "dockerfile",
  "git_config",
  "gitcommit",
  "gitignore",
  "go",
  "gomod",
  "gosum",
  "gotmpl",
  "gowork",
  "html",
  "javascript",
  "json",
  "lua",
  "luadoc",
  "make",
  "markdown",
  "markdown_inline",
  "python",
  "query",
  "regex",
  "rust",
  "sql",
  "ssh_config",
  "toml",
  "tsx",
  "typescript",
  "vim",
  "vimdoc",
  "xml",
  "yaml",
}

require("nvim-treesitter").setup()

-- Install any missing parsers once, quietly, in the background.
do
  local installed = require("nvim-treesitter.config").get_installed("parsers")
  local missing = vim.tbl_filter(function(p)
    return not vim.tbl_contains(installed, p)
  end, ts_parsers)
  if #missing > 0 then
    require("nvim-treesitter").install(missing)
  end
end

-- `main` has no module system: start highlighting/indent ourselves.
vim.api.nvim_create_autocmd("FileType", {
  desc = "Enable treesitter highlighting and indent",
  callback = function(args)
    local ft = vim.bo[args.buf].filetype
    local lang = vim.treesitter.language.get_lang(ft)
    if not lang or not vim.tbl_contains(ts_parsers, lang) then
      return
    end
    pcall(vim.treesitter.start, args.buf, lang)
    -- Treesitter indent is still rough for a few languages; skip those.
    if not vim.tbl_contains({ "python", "yaml", "markdown" }, ft) then
      vim.bo[args.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
    end
  end,
})

require("nvim-treesitter-textobjects").setup({
  select = { lookahead = true },
  move = { set_jumps = true },
})

local ts_select = require("nvim-treesitter-textobjects.select").select_textobject
for lhs, obj in pairs({
  af = "@function.outer",
  ["if"] = "@function.inner",
  ac = "@class.outer",
  ic = "@class.inner",
  aa = "@parameter.outer",
  ia = "@parameter.inner",
  ab = "@block.outer",
  ib = "@block.inner",
}) do
  vim.keymap.set({ "x", "o" }, lhs, function()
    ts_select(obj, "textobjects")
  end, { desc = "Treesitter " .. obj })
end

local ts_move = require("nvim-treesitter-textobjects.move")
vim.keymap.set({ "n", "x", "o" }, "]f", function()
  ts_move.goto_next_start("@function.outer", "textobjects")
end, { desc = "Next function" })
vim.keymap.set({ "n", "x", "o" }, "[f", function()
  ts_move.goto_previous_start("@function.outer", "textobjects")
end, { desc = "Prev function" })

-- ----------------------------------------------------------------------------
-- 6. Mason  (installs the server/tool binaries; mason-lock.json pins versions)
-- ----------------------------------------------------------------------------
require("mason").setup({
  PATH = "prepend",
  ui = {
    border = "rounded",
    icons = { package_installed = "✓", package_pending = "➜", package_uninstalled = "✗" },
  },
})
require("mason-lock").setup({ lockfile_path = vim.fn.stdpath("config") .. "/mason-lock.json" })

-- Everything this config expects on PATH. Install with :MasonInstallAll below,
-- then run :MasonLock to write the pinned versions.
local mason_tools = {
  -- servers
  "gopls",
  "rust-analyzer",
  "basedpyright",
  "ruff",
  "taplo",
  "yaml-language-server",
  "vtsls",
  "marksman",
  "lua-language-server",
  -- formatters
  "gofumpt",
  "goimports",
  "stylua",
  "prettier",
  "shfmt",
  -- linters
  "golangci-lint",
  "shellcheck",
  -- debug adapters
  "delve",
  "codelldb",
}

uc("MasonInstallAll", function()
  local reg = require("mason-registry")
  reg.refresh(function()
    for _, name in ipairs(mason_tools) do
      local ok, pkg = pcall(reg.get_package, name)
      if ok and not pkg:is_installed() then
        pkg:install()
      end
    end
    vim.notify("Mason: install queued. Run :MasonLock when it finishes.", vim.log.levels.INFO)
  end)
end, { desc = "Install every tool this config expects" })

-- ----------------------------------------------------------------------------
-- 7. LSP
-- ----------------------------------------------------------------------------
-- Shared capabilities. mini.completion drives completion via omnifunc, so we
-- advertise snippet support and let the server send full completion items.
vim.lsp.config("*", {
  capabilities = {
    textDocument = {
      completion = {
        completionItem = {
          snippetSupport = true,
          resolveSupport = { properties = { "documentation", "detail", "additionalTextEdits" } },
        },
      },
    },
    workspace = {
      fileOperations = { didRename = true, willRename = true },
    },
  },
})

-- --- Go: the full treatment -------------------------------------------------
vim.lsp.config("gopls", {
  settings = {
    gopls = {
      gofumpt = true,
      staticcheck = true,
      usePlaceholders = true,
      completeUnimported = true,
      semanticTokens = true,
      directoryFilters = { "-.git", "-node_modules", "-vendor" },
      analyses = {
        fieldalignment = false, -- noisy; enable per-project if you care
        nilness = true,
        shadow = true,
        unusedparams = true,
        unusedwrite = true,
        unusedvariable = true,
        useany = true,
      },
      codelenses = {
        generate = true,
        gc_details = true,
        test = true,
        tidy = true,
        upgrade_dependency = true,
        vendor = true,
        regenerate_cgo = true,
        run_govulncheck = true,
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
    },
  },
})

-- --- Rust: rustaceanvim owns rust-analyzer entirely -------------------------
-- Do NOT vim.lsp.enable('rust_analyzer') — rustaceanvim starts it itself.
vim.g.rustaceanvim = {
  tools = { float_win_config = { border = "rounded" } },
  server = {
    default_settings = {
      ["rust-analyzer"] = {
        cargo = {
          allFeatures = true,
          loadOutDirsFromCheck = true,
          buildScripts = { enable = true },
        },
        check = { command = "clippy", extraArgs = { "--no-deps" } },
        procMacro = { enable = true, ignored = { ["async-trait"] = { "async_trait" } } },
        inlayHints = {
          bindingModeHints = { enable = false },
          closureReturnTypeHints = { enable = "with_block" },
          lifetimeElisionHints = { enable = "skip_trivial", useParameterNames = true },
          parameterHints = { enable = true },
          typeHints = { enable = true },
        },
        diagnostics = { enable = true, experimental = { enable = true } },
        files = { excludeDirs = { ".direnv", "target", "node_modules" } },
      },
    },
  },
  dap = {}, -- picks up mason's codelldb automatically
}

-- --- The "safe" tier --------------------------------------------------------
vim.lsp.config("basedpyright", {
  settings = {
    basedpyright = {
      analysis = {
        typeCheckingMode = "standard", -- 'strict' is a lot; opt in per project
        autoImportCompletions = true,
        diagnosticMode = "openFilesOnly",
        inlayHints = { variableTypes = true, functionReturnTypes = true },
      },
    },
  },
})

vim.lsp.config("ruff", {
  -- Let basedpyright own hover; ruff handles lint + fixes + import sorting.
  on_attach = function(client)
    client.server_capabilities.hoverProvider = false
  end,
})

vim.lsp.config("yamlls", {
  settings = {
    yaml = {
      keyOrdering = false,
      validate = true,
      schemaStore = { enable = true, url = "https://www.schemastore.org/api/json/catalog.json" },
    },
  },
})

vim.lsp.config("vtsls", {
  settings = {
    typescript = {
      updateImportsOnFileMove = { enabled = "always" },
      inlayHints = {
        parameterNames = { enabled = "literals" },
        variableTypes = { enabled = false },
        propertyDeclarationTypes = { enabled = true },
        functionLikeReturnTypes = { enabled = true },
      },
    },
    vtsls = { experimental = { completion = { enableServerSideFuzzyMatch = true } } },
  },
})

vim.lsp.config("lua_ls", {
  settings = {
    Lua = {
      runtime = { version = "LuaJIT" },
      workspace = { checkThirdParty = false, library = { vim.env.VIMRUNTIME } },
      diagnostics = {
        globals = {
          "vim",
          "Mini",
          "MiniPick",
          "MiniFiles",
          "MiniIcons",
          "MiniNotify",
          "MiniSnippets",
          "MiniCompletion",
          "MiniMisc",
          "MiniExtra",
        },
      },
      hint = { enable = true },
      telemetry = { enable = false },
      format = { enable = false }, -- stylua does this
    },
  },
})

vim.lsp.enable({
  "gopls",
  "basedpyright",
  "ruff",
  "taplo",
  "yamlls",
  "vtsls",
  "marksman",
  "lua_ls",
})

-- --- Per-buffer LSP setup ---------------------------------------------------
vim.api.nvim_create_autocmd("LspAttach", {
  desc = "LSP keymaps and buffer-local features",
  callback = function(ev)
    local buf = ev.buf
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if not client then
      return
    end

    -- Point mini.completion at the LSP for this buffer.
    vim.bo[buf].omnifunc = "v:lua.MiniCompletion.completefunc_lsp"

    local function map(lhs, rhs, desc, mode)
      vim.keymap.set(mode or "n", lhs, rhs, { buffer = buf, desc = "LSP: " .. desc })
    end

    -- Core already provides: grn rename, gra code action, grr references,
    -- gri implementation, grt type definition, gO document symbols, K hover.
    -- These add picker-backed versions and the things core leaves out.
    map("gd", function()
      MiniExtra.pickers.lsp({ scope = "definition" })
    end, "Definition")
    map("gD", vim.lsp.buf.declaration, "Declaration")
    map("grr", function()
      MiniExtra.pickers.lsp({ scope = "references" })
    end, "References")
    map("gri", function()
      MiniExtra.pickers.lsp({ scope = "implementation" })
    end, "Implementation")
    map("grt", function()
      MiniExtra.pickers.lsp({ scope = "type_definition" })
    end, "Type definition")
    map("gO", function()
      MiniExtra.pickers.lsp({ scope = "document_symbol" })
    end, "Document symbols")
    map("<leader>ls", function()
      MiniExtra.pickers.lsp({ scope = "workspace_symbol" })
    end, "Workspace symbols")
    map("<leader>lr", vim.lsp.buf.rename, "Rename")
    map("<leader>la", vim.lsp.buf.code_action, "Code action", { "n", "x" })
    map("<leader>lc", vim.lsp.codelens.run, "Run code lens")
    map("<C-s>", vim.lsp.buf.signature_help, "Signature help", "i")

    -- Inlay hints on by default; <leader>th toggles.
    if client:supports_method("textDocument/inlayHint") then
      vim.lsp.inlay_hint.enable(true, { bufnr = buf })
    end

    -- Highlight other references to the symbol under the cursor.
    if client:supports_method("textDocument/documentHighlight") then
      local group = vim.api.nvim_create_augroup("lsp_highlight." .. buf, { clear = true })
      vim.api.nvim_create_autocmd({ "CursorHold", "CursorHoldI" }, {
        group = group,
        buffer = buf,
        callback = vim.lsp.buf.document_highlight,
      })
      vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, {
        group = group,
        buffer = buf,
        callback = vim.lsp.buf.clear_references,
      })
    end

    -- Refresh code lenses (Go: generate / test / tidy).
    if client:supports_method("textDocument/codeLens") then
      vim.api.nvim_create_autocmd({ "BufEnter", "InsertLeave", "TextChanged" }, {
        buffer = buf,
        callback = function()
          vim.lsp.codelens.refresh({ bufnr = buf })
        end,
      })
      vim.lsp.codelens.refresh({ bufnr = buf })
    end
  end,
})

-- ----------------------------------------------------------------------------
-- 8. Formatting
-- ----------------------------------------------------------------------------
require("conform").setup({
  notify_on_error = true,
  default_format_opts = { lsp_format = "fallback" },
  formatters_by_ft = {
    go = { "goimports", "gofumpt" },
    rust = { "rustfmt" },
    python = { "ruff_fix", "ruff_format", "ruff_organize_imports" },
    lua = { "stylua" },
    toml = { "taplo" },
    yaml = { "prettier" },
    json = { "prettier" },
    jsonc = { "prettier" },
    markdown = { "prettier" },
    sh = { "shfmt" },
    bash = { "shfmt" },
    javascript = { "prettier" },
    typescript = { "prettier" },
    javascriptreact = { "prettier" },
    typescriptreact = { "prettier" },
  },
  formatters = {
    rustfmt = { options = { default_edition = "2021" } },
    shfmt = { prepend_args = { "-i", "2", "-ci" } },
  },
  format_on_save = function(bufnr)
    if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat then
      return
    end
    return { timeout_ms = 2000, lsp_format = "fallback" }
  end,
})

uc("FormatToggle", function(args)
  if args.bang then
    vim.b.disable_autoformat = not vim.b.disable_autoformat
    vim.notify("Buffer autoformat: " .. (vim.b.disable_autoformat and "off" or "on"))
  else
    vim.g.disable_autoformat = not vim.g.disable_autoformat
    vim.notify("Global autoformat: " .. (vim.g.disable_autoformat and "off" or "on"))
  end
end, { bang = true, desc = "Toggle format-on-save (! = buffer only)" })

-- ----------------------------------------------------------------------------
-- 9. Linting  (things the LSP doesn't already cover)
-- ----------------------------------------------------------------------------
local lint = require("lint")
lint.linters_by_ft = {
  go = { "golangcilint" },
  sh = { "shellcheck" },
  bash = { "shellcheck" },
  -- Python lint comes from the ruff LSP; Rust from clippy via rust-analyzer.
}

vim.api.nvim_create_autocmd({ "BufWritePost", "BufReadPost", "InsertLeave" }, {
  desc = "Run linters",
  callback = function()
    lint.try_lint(nil, { ignore_errors = true })
  end,
})

-- ----------------------------------------------------------------------------
-- 10. Debugging  (nvim-dap, no dap-ui — uses the built-in widgets + REPL)
-- ----------------------------------------------------------------------------
local dap = require("dap")

require("dap-go").setup({
  delve = { detached = vim.fn.has("win32") == 0 },
})

-- Rust: rustaceanvim wires codelldb itself. Use :RustLsp debuggables.

vim.fn.sign_define("DapBreakpoint", { text = "●", texthl = "DiagnosticError" })
vim.fn.sign_define("DapBreakpointCondition", { text = "◆", texthl = "DiagnosticWarn" })
vim.fn.sign_define("DapLogPoint", { text = "◇", texthl = "DiagnosticInfo" })
vim.fn.sign_define("DapStopped", { text = "▶", texthl = "DiagnosticOk", linehl = "Visual" })

local widgets = require("dap.ui.widgets")

-- ----------------------------------------------------------------------------
-- 11. Documents / markdown
-- ----------------------------------------------------------------------------
require("render-markdown").setup({
  completions = { lsp = { enabled = true } },
  heading = { sign = false, width = "block", left_pad = 0, right_pad = 2 },
  code = { sign = false, width = "block", right_pad = 2, language_pad = 1 },
  bullet = { icons = { "●", "○", "◆", "◇" } },
  checkbox = { unchecked = { icon = "󰄱 " }, checked = { icon = "󰱒 " } },
  -- Rendered everywhere except insert mode on the current line, so editing is sane.
  render_modes = { "n", "c", "t" },
  win_options = { conceallevel = { rendered = 3 } },
})

-- A reading mode: no numbers, wrapped text, centred column.
uc("Read", function()
  vim.opt_local.number = false
  vim.opt_local.relativenumber = false
  vim.opt_local.signcolumn = "no"
  vim.opt_local.wrap = true
  vim.opt_local.linebreak = true
  vim.opt_local.list = false
  vim.opt_local.colorcolumn = ""
  vim.opt_local.cursorline = false
  MiniMisc.zoom(0, {})
end, { desc = "Distraction-free reading mode for this buffer" })

-- ----------------------------------------------------------------------------
-- 12. Keymaps
-- ----------------------------------------------------------------------------
local map = vim.keymap.set

map("n", "<Esc>", "<cmd>nohlsearch<CR>", { desc = "Clear search highlight" })
map("n", "<leader>w", "<cmd>write<CR>", { desc = "Write" })
map("n", "<leader>q", "<cmd>quit<CR>", { desc = "Quit" })

-- Keep the cursor centred / selection intact
map("n", "<C-d>", "<C-d>zz")
map("n", "<C-u>", "<C-u>zz")
map("n", "n", "nzzzv")
map("n", "N", "Nzzzv")
map("x", "<", "<gv")
map("x", ">", ">gv")

-- Window navigation
map("n", "<C-h>", "<C-w>h")
map("n", "<C-j>", "<C-w>j")
map("n", "<C-k>", "<C-w>k")
map("n", "<C-l>", "<C-w>l")

-- Terminal
map("t", "<Esc><Esc>", "<C-\\><C-n>", { desc = "Leave terminal mode" })

-- Completion: Tab cycles the popup, plain Tab otherwise
map("i", "<Tab>", function()
  return vim.fn.pumvisible() == 1 and "<C-n>" or "<Tab>"
end, { expr = true })
map("i", "<S-Tab>", function()
  return vim.fn.pumvisible() == 1 and "<C-p>" or "<S-Tab>"
end, { expr = true })
map("i", "<CR>", function()
  return vim.fn.pumvisible() == 1 and "<C-y>" or "<CR>"
end, { expr = true })

-- Find (mini.pick)
map("n", "<leader><leader>", function()
  MiniPick.builtin.buffers()
end, { desc = "Buffers" })
map("n", "<leader>ff", function()
  MiniPick.builtin.files()
end, { desc = "Files" })
map("n", "<leader>fg", function()
  MiniPick.builtin.grep_live()
end, { desc = "Grep live" })
map("n", "<leader>fw", function()
  MiniPick.builtin.grep({ pattern = vim.fn.expand("<cword>") })
end, { desc = "Grep word" })
map("n", "<leader>fh", function()
  MiniPick.builtin.help()
end, { desc = "Help" })
map("n", "<leader>fr", function()
  MiniExtra.pickers.oldfiles()
end, { desc = "Recent files" })
map("n", "<leader>fd", function()
  MiniExtra.pickers.diagnostic()
end, { desc = "Diagnostics" })
map("n", "<leader>fk", function()
  MiniExtra.pickers.keymaps()
end, { desc = "Keymaps" })
map("n", "<leader>fc", function()
  MiniExtra.pickers.commands()
end, { desc = "Commands" })
map("n", "<leader>f/", function()
  MiniExtra.pickers.buf_lines({ scope = "current" })
end, { desc = "Lines in buffer" })
map("n", "<leader>fR", function()
  MiniExtra.pickers.registers()
end, { desc = "Registers" })
map("n", "<leader>fp", function()
  MiniExtra.pickers.explorer()
end, { desc = "Explorer picker" })

-- Files
map("n", "<leader>e", function()
  if not MiniFiles.close() then
    MiniFiles.open(vim.api.nvim_buf_get_name(0), true)
  end
end, { desc = "File explorer" })
map("n", "<leader>E", function()
  MiniFiles.open(vim.uv.cwd(), true)
end, { desc = "File explorer (cwd)" })

-- Git
map("n", "<leader>gg", function()
  vim.cmd("Git status")
end, { desc = "Git status" })
map("n", "<leader>gl", function()
  MiniExtra.pickers.git_commits()
end, { desc = "Git log" })
map("n", "<leader>gb", function()
  MiniExtra.pickers.git_branches()
end, { desc = "Git branches" })
map("n", "<leader>gh", function()
  MiniExtra.pickers.git_hunks()
end, { desc = "Git hunks" })
map("n", "<leader>gd", function()
  MiniDiff.toggle_overlay()
end, { desc = "Diff overlay" })
map({ "n", "x" }, "<leader>gs", function()
  MiniGit.show_at_cursor()
end, { desc = "Show at cursor" })

-- Diagnostics
map("n", "<leader>dd", vim.diagnostic.open_float, { desc = "Line diagnostics" })
map("n", "<leader>dq", vim.diagnostic.setloclist, { desc = "Diagnostics to loclist" })

-- Debug
map("n", "<F5>", function()
  dap.continue()
end, { desc = "Debug: continue" })
map("n", "<F10>", function()
  dap.step_over()
end, { desc = "Debug: step over" })
map("n", "<F11>", function()
  dap.step_into()
end, { desc = "Debug: step into" })
map("n", "<F12>", function()
  dap.step_out()
end, { desc = "Debug: step out" })
map("n", "<leader>db", function()
  dap.toggle_breakpoint()
end, { desc = "Toggle breakpoint" })
map("n", "<leader>dB", function()
  vim.ui.input({ prompt = "Breakpoint condition: " }, function(c)
    if c then
      dap.set_breakpoint(c)
    end
  end)
end, { desc = "Conditional breakpoint" })
map("n", "<leader>dr", function()
  dap.repl.toggle()
end, { desc = "Debug REPL" })
map("n", "<leader>dl", function()
  dap.run_last()
end, { desc = "Run last" })
map("n", "<leader>dt", function()
  dap.terminate()
end, { desc = "Terminate" })
map({ "n", "x" }, "<leader>dh", function()
  widgets.hover()
end, { desc = "Debug: hover value" })
map("n", "<leader>ds", function()
  widgets.centered_float(widgets.scopes)
end, { desc = "Debug: scopes" })
map("n", "<leader>df", function()
  widgets.centered_float(widgets.frames)
end, { desc = "Debug: frames" })

-- Code
map("n", "<leader>cf", function()
  require("conform").format({ async = true })
end, { desc = "Format buffer" })
map("n", "<leader>cl", function()
  lint.try_lint()
end, { desc = "Lint buffer" })

-- Toggles
map("n", "<leader>th", function()
  vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled({ bufnr = 0 }), { bufnr = 0 })
end, { desc = "Inlay hints" })
map("n", "<leader>tw", "<cmd>set wrap!<CR>", { desc = "Wrap" })
map("n", "<leader>tf", "<cmd>FormatToggle<CR>", { desc = "Format on save" })
map("n", "<leader>tz", function()
  MiniMisc.zoom()
end, { desc = "Zoom window" })
map("n", "<leader>tr", "<cmd>RenderMarkdown toggle<CR>", { desc = "Markdown render" })
map("n", "<leader>td", function()
  local on = vim.diagnostic.is_enabled()
  vim.diagnostic.enable(not on)
  vim.notify("Diagnostics " .. (on and "off" or "on"))
end, { desc = "Diagnostics" })

-- ----------------------------------------------------------------------------
-- 13. Language-specific behaviour
-- ----------------------------------------------------------------------------
local ftgroup = vim.api.nvim_create_augroup("ft_settings", { clear = true })

vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = { "go", "gomod", "gowork", "gotmpl" },
  callback = function(a)
    vim.bo[a.buf].expandtab = false
    vim.bo[a.buf].shiftwidth = 4
    vim.bo[a.buf].tabstop = 4
    vim.bo[a.buf].softtabstop = 4
    -- Go-specific: run tests under the cursor / in the file
    vim.keymap.set("n", "<leader>ct", function()
      require("dap-go").debug_test()
    end, { buffer = a.buf, desc = "Debug nearest test" })
  end,
})

vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = { "rust", "python" },
  callback = function(a)
    vim.bo[a.buf].shiftwidth = 4
    vim.bo[a.buf].tabstop = 4
    vim.bo[a.buf].softtabstop = 4
  end,
})

-- Rust: rustaceanvim's extras are worth real keymaps.
vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = "rust",
  callback = function(a)
    local function rmap(lhs, cmd, desc)
      vim.keymap.set("n", lhs, function()
        vim.cmd.RustLsp(cmd)
      end, { buffer = a.buf, desc = "Rust: " .. desc })
    end
    rmap("<leader>cR", "runnables", "Runnables")
    rmap("<leader>cD", "debuggables", "Debuggables")
    rmap("<leader>ce", "expandMacro", "Expand macro")
    rmap("<leader>co", "openCargo", "Open Cargo.toml")
    rmap("<leader>cp", "parentModule", "Parent module")
    rmap("<leader>cE", "explainError", "Explain error")
    rmap("<leader>cj", "joinLines", "Join lines")
    vim.keymap.set("n", "K", function()
      vim.cmd.RustLsp({ "hover", "actions" })
    end, { buffer = a.buf, desc = "Rust: hover actions" })
  end,
})

vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = { "markdown", "text", "gitcommit" },
  callback = function(a)
    vim.opt_local.wrap = true
    vim.opt_local.spell = true
    vim.opt_local.conceallevel = 2
    vim.bo[a.buf].textwidth = 0
  end,
})

vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = { "yaml", "yml" },
  callback = function(a)
    vim.bo[a.buf].shiftwidth = 2
    vim.bo[a.buf].tabstop = 2
    vim.bo[a.buf].indentkeys = vim.bo[a.buf].indentkeys .. ",0-"
  end,
})

-- Close scratch/help style buffers with q
vim.api.nvim_create_autocmd("FileType", {
  group = ftgroup,
  pattern = { "help", "man", "qf", "checkhealth", "lspinfo", "dap-float" },
  callback = function(a)
    vim.bo[a.buf].buflisted = false
    vim.keymap.set("n", "q", "<cmd>close<CR>", { buffer = a.buf, silent = true })
  end,
})

-- ----------------------------------------------------------------------------
-- 14. Misc autocommands
-- ----------------------------------------------------------------------------
local misc = vim.api.nvim_create_augroup("misc", { clear = true })

vim.api.nvim_create_autocmd("TextYankPost", {
  group = misc,
  desc = "Highlight on yank",
  callback = function()
    vim.hl.on_yank({ timeout = 150 })
  end,
})

vim.api.nvim_create_autocmd("BufWritePre", {
  group = misc,
  desc = "Create parent dirs on save",
  callback = function(a)
    if a.match:match("^%w%w+:[\\/][\\/]") then
      return
    end
    vim.fn.mkdir(vim.fn.fnamemodify(vim.uv.fs_realpath(a.match) or a.match, ":p:h"), "p")
  end,
})

vim.api.nvim_create_autocmd("VimResized", {
  group = misc,
  command = "tabdo wincmd =",
})
