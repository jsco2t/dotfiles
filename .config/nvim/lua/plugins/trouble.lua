return {
  {
    'folke/trouble.nvim',
    opts = {}, -- for default options, refer to the configuration section for custom setup.
    cmd = 'Trouble',
    keys = {
      {
        '<leader>xX',
        '<cmd>Trouble diagnostics toggle focus=true<cr>',
        desc = 'Workspace Diagnostics (Trouble)',
      },
      {
        '<leader>xx',
        '<cmd>Trouble diagnostics toggle filter.buf=0 focus=true<cr>',
        desc = 'Buffer Diagnostics (Trouble)',
      },
      {
        '<leader>xs',
        '<cmd>Trouble symbols toggle focus=false<cr>',
        desc = 'Symbols (Trouble)',
      },
      {
        '<leader>xl',
        '<cmd>Trouble lsp_document_symbols toggle focus=true<cr>',
        desc = 'LSP symbols',
      },
    },
  },
}
