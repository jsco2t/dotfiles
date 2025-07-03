return { -- Useful plugin to show you pending keybinds.
  'folke/which-key.nvim',
  event = 'VimEnter',
  config = function()
    require('which-key').setup()

    -- Document existing key chains
    require('which-key').add {
      { '<leader>a', group = '[A]I' },
      { '<leader>c', group = '[C]ode' },
      { '<leader>d', group = '[D]ocument' },
      { '<leader>e', group = '[E]rrors and Diagnostics' },
      { '<leader>f', group = '[F]iles' },
      { '<leader>r', group = '[R]ename' },
      { '<leader>s', group = '[S]earch' },
      { '<leader>w', group = '[W]orkspace' },
      { '<leader>T', group = '[T]oggle' },
      { '<leader>t', group = '[T]erminal' },
      { '<leader>h', group = 'Git [H]unk', mode = { 'n', 'v' } },
    }
  end,
}
