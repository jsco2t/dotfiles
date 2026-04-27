local map = vim.keymap.set

---------------------------------------------------------------------------
-- Window navigation
---------------------------------------------------------------------------
map("n", "<C-h>", "<C-w>h", { desc = "Go to left window" })
map("n", "<C-j>", "<C-w>j", { desc = "Go to lower window" })
map("n", "<C-k>", "<C-w>k", { desc = "Go to upper window" })
map("n", "<C-l>", "<C-w>l", { desc = "Go to right window" })

map("n", "<C-Up>", "<cmd>resize +2<cr>", { desc = "Increase window height" })
map("n", "<C-Down>", "<cmd>resize -2<cr>", { desc = "Decrease window height" })
map("n", "<C-Left>", "<cmd>vertical resize -2<cr>", { desc = "Decrease window width" })
map("n", "<C-Right>", "<cmd>vertical resize +2<cr>", { desc = "Increase window width" })

---------------------------------------------------------------------------
-- Move lines
---------------------------------------------------------------------------
map("n", "<A-j>", "<cmd>m .+1<cr>==", { desc = "Move down" })
map("n", "<A-k>", "<cmd>m .-2<cr>==", { desc = "Move up" })
map("i", "<A-j>", "<esc><cmd>m .+1<cr>==gi", { desc = "Move down" })
map("i", "<A-k>", "<esc><cmd>m .-2<cr>==gi", { desc = "Move up" })
map("v", "<A-j>", ":m '>+1<cr>gv=gv", { desc = "Move down" })
map("v", "<A-k>", ":m '<-2<cr>gv=gv", { desc = "Move up" })

---------------------------------------------------------------------------
-- Buffers
---------------------------------------------------------------------------
map("n", "[b", "<cmd>bprevious<cr>", { desc = "Prev buffer" })
map("n", "]b", "<cmd>bnext<cr>", { desc = "Next buffer" })
map("n", "<leader>bd", function() Snacks.bufdelete() end, { desc = "Delete buffer" })

---------------------------------------------------------------------------
-- Better indenting (stay in visual mode)
---------------------------------------------------------------------------
map("v", "<", "<gv")
map("v", ">", ">gv")

---------------------------------------------------------------------------
-- Clear search highlight
---------------------------------------------------------------------------
map({ "i", "n" }, "<esc>", "<cmd>noh<cr><esc>", { desc = "Clear hlsearch" })

---------------------------------------------------------------------------
-- File explorer
---------------------------------------------------------------------------
map("n", "<leader>e", function() Snacks.explorer() end, { desc = "File explorer" })
map("n", "\\", function() Snacks.explorer() end, { desc = "File explorer" })

---------------------------------------------------------------------------
-- Find (snacks.picker)
---------------------------------------------------------------------------
map("n", "<leader><space>", function() Snacks.picker.files() end, { desc = "Find files" })
map("n", "<leader>ff", function() Snacks.picker.files() end, { desc = "Find files" })
map("n", "<leader>fg", function() Snacks.picker.grep() end, { desc = "Grep" })
map("n", "<leader>fb", function() Snacks.picker.buffers() end, { desc = "Buffers" })
map("n", "<leader>fh", function() Snacks.picker.help() end, { desc = "Help pages" })
map("n", "<leader>fr", function() Snacks.picker.recent() end, { desc = "Recent files" })
map("n", "<leader>/", function() Snacks.picker.grep() end, { desc = "Grep" })
map("n", "<leader>,", function() Snacks.picker.buffers() end, { desc = "Switch buffer" })
map("n", "<leader>:", function() Snacks.picker.command_history() end, { desc = "Command history" })

---------------------------------------------------------------------------
-- Search
---------------------------------------------------------------------------
map("n", "<leader>sd", function() Snacks.picker.diagnostics() end, { desc = "Diagnostics" })
map("n", "<leader>sw", function() Snacks.picker.grep_word() end, { desc = "Grep word under cursor" })
map("n", "<leader>sk", function() Snacks.picker.keymaps() end, { desc = "Keymaps" })

---------------------------------------------------------------------------
-- Flash (enhanced motions)
---------------------------------------------------------------------------
map({ "n", "x", "o" }, "s", function() require("flash").jump() end, { desc = "Flash" })
map({ "n", "x", "o" }, "S", function() require("flash").treesitter() end, { desc = "Flash treesitter" })

---------------------------------------------------------------------------
-- Git
---------------------------------------------------------------------------
map("n", "<leader>gg", function()
  Snacks.terminal("lazygit", { cwd = vim.fn.getcwd() })
end, { desc = "Lazygit" })

---------------------------------------------------------------------------
-- Diagnostics (trouble.nvim)
---------------------------------------------------------------------------
map("n", "<leader>xx", "<cmd>Trouble diagnostics toggle<cr>", { desc = "Diagnostics" })
map("n", "<leader>xX", "<cmd>Trouble diagnostics toggle filter.buf=0<cr>", { desc = "Buffer diagnostics" })
map("n", "<leader>xl", "<cmd>Trouble loclist toggle<cr>", { desc = "Location list" })
map("n", "<leader>xq", "<cmd>Trouble qflist toggle<cr>", { desc = "Quickfix list" })

---------------------------------------------------------------------------
-- Code
---------------------------------------------------------------------------
map({ "n", "v" }, "<leader>cf", function()
  require("conform").format({ async = true, lsp_format = "fallback" })
end, { desc = "Format" })

---------------------------------------------------------------------------
-- Quit / Session
---------------------------------------------------------------------------
map("n", "<leader>qq", "<cmd>qa<cr>", { desc = "Quit all" })
map("n", "<leader>qs", function() require("persistence").load() end, { desc = "Restore session" })
map("n", "<leader>qS", function() require("persistence").select() end, { desc = "Select session" })

---------------------------------------------------------------------------
-- UI toggles
---------------------------------------------------------------------------
map("n", "<leader>ud", function() vim.diagnostic.enable(not vim.diagnostic.is_enabled()) end, { desc = "Toggle diagnostics" })
map("n", "<leader>uf", function()
  vim.g.disable_format_on_save = not vim.g.disable_format_on_save
  vim.notify("Format on save: " .. (vim.g.disable_format_on_save and "off" or "on"))
end, { desc = "Toggle format on save" })
map("n", "<leader>uw", "<cmd>set wrap!<cr>", { desc = "Toggle word wrap" })
map("n", "<leader>us", "<cmd>set spell!<cr>", { desc = "Toggle spelling" })
map("n", "<leader>ul", "<cmd>set relativenumber!<cr>", { desc = "Toggle relative numbers" })
