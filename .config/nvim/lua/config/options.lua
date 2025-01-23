-- vim global options
--
vim.g.mapleader = " "
vim.g.autoformat = true

-- vim whitespace settings
--
vim.opt.showbreak = "➩"
vim.opt.listchars = { tab = "˗˗", trail = "·", space = "◦" } -- whitespace replacement characters
vim.opt.list = true -- show whitespace characters

vim.o.foldcolumn = "0" -- remove code folding
vim.opt.mouse = "a" -- Enable mouse mode
vim.opt.number = true -- Print line number
vim.opt.signcolumn = "yes" -- Always show the signcolumn, otherwise it would shift the text each time
vim.opt.smartcase = true -- Don't ignore case with capitals
vim.opt.smartindent = true -- Insert indents automatically
vim.opt.spelllang = { "en" }
vim.opt.spell = true -- turn on spell check
vim.opt.splitbelow = true -- Put new windows below current
vim.opt.splitkeep = "screen"
vim.opt.splitright = true -- Put new windows right of current
vim.opt.tabstop = 2 -- Number of spaces tabs count for
vim.opt.termguicolors = true -- True color support
vim.opt.expandtab = true -- Use spaces instead of tabs
vim.opt.clipboard = "unnamedplus" -- Sync with system clipboard
vim.opt.cursorline = true -- Enable highlighting of the current line
vim.opt.shiftwidth = 2 -- Size of an indent
vim.opt.virtualedit = "block" -- Allow cursor to move where there is no text in visual block mode
vim.opt.relativenumber = false
vim.o.exrc = true
