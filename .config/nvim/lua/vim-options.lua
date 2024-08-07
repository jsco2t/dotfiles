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

-- perf testing
-- vim.o.cursorline = false
