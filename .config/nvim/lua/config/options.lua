-- Options loaded before plugins. Replaces both LazyVim defaults and user overrides.

vim.o.number = true
vim.o.relativenumber = false
vim.o.signcolumn = "yes"
vim.o.mouse = "a"
vim.o.showmode = false
vim.o.clipboard = "unnamedplus"
vim.o.undofile = true
vim.o.undolevels = 10000
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.smartindent = true
vim.o.expandtab = true
vim.o.shiftwidth = 2
vim.o.tabstop = 2
vim.o.shiftround = true
vim.o.inccommand = "split"
vim.o.scrolloff = 10
vim.o.sidescrolloff = 8
vim.o.spell = true
vim.o.exrc = true
vim.o.termguicolors = true
vim.o.cursorline = true
vim.o.splitright = true
vim.o.splitbelow = true
vim.o.splitkeep = "screen"
vim.o.updatetime = 200
vim.o.timeoutlen = 300
vim.o.pumheight = 10
vim.o.laststatus = 3
vim.o.wrap = false
vim.o.linebreak = true
vim.o.virtualedit = "block"
vim.o.completeopt = "menuone,noselect,popup"
vim.o.wildmode = "longest:full,full"
vim.o.grepprg = "rg --vimgrep"
vim.o.grepformat = "%f:%l:%c:%m"
vim.o.foldlevel = 99
vim.o.jumpoptions = "view"
vim.o.winminwidth = 5

vim.opt.shortmess:append({ W = true, I = true, c = true, C = true })
vim.opt.sessionoptions = { "buffers", "curdir", "tabpages", "winsize", "help", "globals", "folds" }
vim.opt.showbreak = "➥"
vim.opt.listchars = { tab = "˗˗", trail = "·", nbsp = "+" }

vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1

if vim.env.SSH_CONNECTION then
  vim.g.snacks_animate = false
end
