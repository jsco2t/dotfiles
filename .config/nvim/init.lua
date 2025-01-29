-- initial version of this config loosely based on:
-- https://github.com/nvim-lua/kickstart.nvim

-- Set <space> as the leader key
-- See `:help mapleader`
--  NOTE: Must happen before plugins are loaded (otherwise wrong leader will be used)
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

-- Setup configuration
--
require 'config.options'
require 'config.keymaps'
require 'config.autocommands'
require 'config.lazy' -- should be last so that all other config is set before lazy loads
