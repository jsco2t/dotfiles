return {
  -- `*` for version in this case == stable per docs on this plugin
  { 'echasnovski/mini-git', version = '*', main = 'mini.git' },
  { 'echasnovski/mini.diff', version = '*' },
  {
    'echasnovski/mini.statusline',
    version = '*',
    config = function()
      require('mini.statusline').setup {}
      local statusline = require 'mini.statusline'

      ---@diagnostic disable-next-line: duplicate-set-field
      statusline.section_location = function()
        return '%2l:%-2v'
      end
    end,
  },
}
