vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

require("config.options")
require("config.packages")
require("config.plugins")
require("config.autocommands")
require("config.keymaps")

vim.lsp.enable({
  "gopls",
  "pyright",
  "ruff",
  "bashls",
  "jsonls",
  "yamlls",
  "taplo",
  "dockerls",
  "docker_compose_ls",
  "marksman",
})
