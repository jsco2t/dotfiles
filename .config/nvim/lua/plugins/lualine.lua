return {
  {
    "nvim-lualine/lualine.nvim",
    lazy = false,
    dependencies = {
      "nvim-tree/nvim-web-devicons",
    },
    config = function()
      require("lualine").setup({
        options = {
          globalstatus = true,
          theme = 'auto',
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
          lualine_y = { 'searchcount' },
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
