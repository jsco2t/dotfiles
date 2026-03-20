-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
--
-- Only options that DIFFER from LazyVim/Neovim defaults are set here.

vim.o.relativenumber = false
vim.o.inccommand = "split"
vim.o.scrolloff = 10
vim.o.spell = true
vim.o.exrc = true

vim.opt.showbreak = "➥"
vim.opt.listchars = { tab = "˗˗", trail = "·", nbsp = "+" }

-- Disable animations over SSH for responsiveness
if vim.env.SSH_CONNECTION then
  vim.g.snacks_animate = false
end
