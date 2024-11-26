-- [[ vim whitespace settings ]]
--
vim.opt.showbreak = "➩"
vim.opt.listchars = { tab = "˗˗", trail = "·", space = "◦" } -- whitespace replacement characters
vim.opt.list = true -- show whitespace characters

-- remove code folding
vim.o.foldcolumn = "0"
