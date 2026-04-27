local autocmd = vim.api.nvim_create_autocmd
local augroup = function(name) return vim.api.nvim_create_augroup(name, { clear = true }) end

-- Enable native LSP completion when a server attaches
autocmd("LspAttach", {
  group = augroup("lsp-attach"),
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if not client then return end

    if client:supports_method("textDocument/completion") then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end

    -- Ruff handles linting/formatting; let pyright own hover and diagnostics
    if client.name == "ruff" then
      client.server_capabilities.hoverProvider = false
    end
  end,
})

-- Highlight yanked text
autocmd("TextYankPost", {
  group = augroup("highlight-yank"),
  callback = function() vim.hl.on_yank() end,
})

-- Equalize splits on terminal resize
autocmd("VimResized", {
  group = augroup("resize-splits"),
  callback = function() vim.cmd("tabdo wincmd =") end,
})

-- Lint on save (nvim-lint)
local ai_config_files = { ["CLAUDE.md"] = true, ["SKILL.md"] = true, ["AGENTS.md"] = true }

autocmd("BufWritePost", {
  group = augroup("nvim-lint"),
  callback = function()
    local filename = vim.fn.fnamemodify(vim.api.nvim_buf_get_name(0), ":t")
    if ai_config_files[filename] then return end
    require("lint").try_lint()
  end,
})

-- Restore cursor position when reopening a file
autocmd("BufReadPost", {
  group = augroup("last-position"),
  callback = function(ev)
    local mark = vim.api.nvim_buf_get_mark(ev.buf, '"')
    local lcount = vim.api.nvim_buf_line_count(ev.buf)
    if mark[1] > 0 and mark[1] <= lcount then
      pcall(vim.api.nvim_win_set_cursor, 0, mark)
    end
  end,
})

-- Close help/man/qf windows with q
autocmd("FileType", {
  group = augroup("close-with-q"),
  pattern = { "help", "man", "qf", "checkhealth", "notify" },
  callback = function(ev)
    vim.bo[ev.buf].buflisted = false
    vim.keymap.set("n", "q", "<cmd>close<cr>", { buffer = ev.buf, silent = true })
  end,
})

-- Auto-create parent directories on save
autocmd("BufWritePre", {
  group = augroup("auto-mkdir"),
  callback = function(ev)
    if ev.match:match("^%w%w+:[\\/][\\/]") then return end
    local file = vim.uv.fs_realpath(ev.match) or ev.match
    vim.fn.mkdir(vim.fn.fnamemodify(file, ":p:h"), "p")
  end,
})
