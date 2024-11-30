-- No idea if this is the "right" way to override palette colors. This is
-- what I got working after studying the source.
--
-- Original theme was installed with astrocommunity.colorscheme.nordic-nvim.
-- More info about the theme can be found here: https://github.com/AlexvZyl/nordic.nvim/tree/main
--
return {
  {
    "AlexvZyl/nordic.nvim",
    lazy = false,
    priority = 1000,
    config = function()
      require("nordic").setup {
        -- theme matching colors can be found here: https://github.com/AlexvZyl/nordic.nvim/blob/main/lua/nordic/colors/nordic.lua
        on_palette = function(palette)
          palette.magenta.base = "#625eac"
          palette.magenta.bright = "#7b78b9"
          palette.magenta.dim = "#514d96"
          palette.orange.bright = "#CB775D" --made to match dark style as the bright version was too pale (IMHO)
          return palette
        end,
      }
      require("nordic").load()
    end,
  },
}
