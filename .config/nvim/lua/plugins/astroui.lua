---@type LazySpec
return {
  "AstroNvim/astroui",
  ---@type AstroUIOpts
  opts = {
    colorscheme = "nordic", -- 'kanagawa' is also good
    highlights = {
      init = {
        HeirlineNormal = { bg = "#80B3B2" }, -- https://github.com/AstroNvim/AstroNvim/blob/main/lua/astronvim/plugins/_astroui_status.lua
      },
    },
  },
}
