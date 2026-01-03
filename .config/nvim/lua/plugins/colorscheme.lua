return {
  {
    "navarasu/onedark.nvim",
    priority = 1000,
    init = function()
      require("onedark").setup({
        style = "darker",
        colors = {
          -- https://github.com/navarasu/onedark.nvim/blob/master/lua/onedark/palette.lua
          purple = "#726fb5",
          --purple = '#625eac', -- previous theme
          --purple = '#7b78b9', -- lighter
          --purple = '#514d96', -- darker
        },
      })
      vim.cmd.colorscheme("onedark")
    end,
  },

  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "onedark",
    },
  },
}
