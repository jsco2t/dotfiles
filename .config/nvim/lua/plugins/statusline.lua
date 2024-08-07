return {
  "rebelot/heirline.nvim",
  opts = function(_, opts)
    local status = require "astroui.status"
    opts.statusline = { -- statusline
      hl = { fg = "fg", bg = "bg" },
      status.component.mode {
        mode_text = { padding = { left = 1, right = 1 } },
      }, -- add the mode text
      status.component.git_branch(),
      status.component.file_info {
        filename = { padding = { left = 0, right = 1 } },
        filetype = false,
      },
      status.component.git_diff(),
      status.component.diagnostics(),
      status.component.fill(),
      status.component.cmd_info(),
      status.component.fill(),
      status.component.lsp(),
      status.component.virtual_env(),
      status.component.treesitter(),
      --status.component.treesitter { padding = { right = 1 } },
      status.component.nav {
        -- add some padding for the percentage provider
        percentage = { padding = { right = 1 } },
        -- disable all other providers
        ruler = false,
        scrollbar = false,
        -- use no separator and define the background color
        surround = { separator = "none", color = "file_info_bg" },
      },
    }
  end,
}
