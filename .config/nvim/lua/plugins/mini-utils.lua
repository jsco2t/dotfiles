return {
  -- `*` for version in this case == stable per docs on this plugin
  { 'echasnovski/mini-git', version = '*', main = 'mini.git' },
  { 'echasnovski/mini.diff', version = '*' },
  {
    'echasnovski/mini.statusline',
    version = '*',
    config = function()
      require('mini.statusline').setup {
        use_icons = true, -- Enable icons (requires Nerd Fonts)
        set_vim_settings = true, -- Automatically set Neovim's statusline options
      }
      local statusline = require 'mini.statusline'
      -- You can configure sections in the statusline by overriding their
      -- default behavior. For example, here we set the section for
      -- cursor location to LINE:COLUMN
      ---@diagnostic disable-next-line: duplicate-set-field
      statusline.section_location = function()
        return '%2l:%-2v'
      end
    end,
  },
}
