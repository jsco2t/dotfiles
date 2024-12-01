-- more info: https://github.com/nvim-lualine/lualine.nvim
return {
  {
    "nvim-lualine/lualine.nvim",
    lazy = false,
    dependencies = {
      "nvim-tree/nvim-web-devicons",
    },
    config = function()
      -- based on https://github.com/AlexvZyl/nordic.nvim
      local colors = {
        blue   = '#88c0d0',
        cyan   = '#80b3b2',
        green  = '#97b67c',
        black  = '#191d24',
        white  = '#e5e9f0',
        red    = '#bf616a',
        purple = '#7b78b9',
        grey   = '#2e3440',
      }
      local custom_theme = {
        normal = {
          a = { fg = colors.black, bg = colors.green },
          b = { fg = colors.white, bg = colors.grey },
          c = { fg = colors.white },
        },

        insert = { a = { fg = colors.black, bg = colors.blue } },
        visual = { a = { fg = colors.black, bg = colors.purple } },
        replace = { a = { fg = colors.black, bg = colors.red } },

        inactive = {
          a = { fg = colors.white, bg = colors.black },
          b = { fg = colors.white, bg = colors.grey },
          c = { fg = colors.white },
        },
      }
      require("lualine").setup({
        options = {
          globalstatus = true,
          theme = custom_theme,
          --theme = 'nordic',
          -- theme = 'auto', --theme = 'nord',
        },
        sections = {
          lualine_a = { 'mode' },
          lualine_b = { 'branch', 'diff', },
          lualine_c = { 'filename' },
          lualine_x = {
            {
              'diagnostics',
              sources = { 'nvim_diagnostic' }, -- can add others..ex: coc
              update_in_insert = true,         -- Update diagnostics in insert mode.
              always_visible = false,          -- Show diagnostics even if there are none.
            },
            'filetype'
          },
          lualine_y = { 'filesize', 'searchcount' },
          lualine_z = { 'location' }
        },
        inactive_sections = {
          lualine_a = {},
          lualine_b = {},
          lualine_c = { 'filename' },
          lualine_x = { 'location' },
          lualine_y = {},
          lualine_z = {}
        },
      })
    end,
  },
}
