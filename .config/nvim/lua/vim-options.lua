-- [[ vim config settings ]]
--

-- [[ vim whitespace settings ]]
--
vim.opt.showbreak = "➩"
vim.opt.listchars = { tab = "˗˗", trail = "·", space = "◦" } -- whitespace replacement characters
vim.opt.list = true -- show whitespace characters

-- [[ custom keymaps ]]
--

--- reflow text
vim.keymap.set("n", "<leader>ww", "gwip", { desc = "reflow text" })

-- clear search highlights
vim.keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })

-- buffer navigation (can also use `[b` and `]b`)
vim.keymap.set("n", "<S-Tab>", ":bprev<CR>", { desc = "previous buffer", noremap = true })
vim.keymap.set("n", "<Tab>", ":bnext<CR>", { desc = "next buffer", noremap = true })
vim.keymap.set("n", "<leader>b", ":Telescope buffers<CR>", { desc = "Show buffers", noremap = true })

-- telescope utilities
vim.keymap.set("n", "<leader>k", ":Telescope keymaps<CR>", { desc = "Show keymaps", noremap = true })
vim.keymap.set("n", "<leader>s", ":Telescope lsp_document_symbols<CR>", { desc = "Show doc symbols", noremap = true })
vim.keymap.set("n", "<leader>D", ":Telescope diagnostics<CR>", { desc = "Show diagnostics", noremap = true })

-- [[ vim ui settings ]]
--

-- remove code folding
vim.o.foldcolumn = "0"

-- [[ vim os integration ]]
--

-- configure clipboard support
--vim.opt.clipboard = "unnamedplus"

-- perf testing
-- vim.o.cursorline = false
--vim.opt.clipboard = "unnamedplus,unnamed"

--if os.getenv "SSH_CLIENT" ~= nil or os.getenv "SSH_TTY" ~= nil then
-- local function my_paste(_)
--   return function(_)
--     local content = vim.fn.getreg '"'
--     return vim.split(content, "\n")
--   end
-- end
--
-- vim.g.clipboard = {
--   name = "OSC 52",
--   copy = {
--     ["+"] = require("vim.ui.clipboard.osc52").copy "+",
--     ["*"] = require("vim.ui.clipboard.osc52").copy "*",
--   },
--   paste = {
--     ["+"] = my_paste "+",
--     ["*"] = my_paste "*",
--   },
-- }
--end
--

-- vim.g.clipboard = {
--   name = "OSC 52",
--   copy = {
--     ["+"] = require("vim.ui.clipboard.osc52").copy "+",
--     ["*"] = require("vim.ui.clipboard.osc52").copy "*",
--   },
--   paste = {
--     ["+"] = require("vim.ui.clipboard.osc52").paste "+",
--     ["*"] = require("vim.ui.clipboard.osc52").paste "*",
--   },
-- }
