-- File explorer customizations (snacks_explorer)
return {
  {
    "folke/snacks.nvim",
    opts = {
      picker = {
        sources = {
          explorer = {
            hidden = true,
            layout = { preset = "sidebar", layout = { width = 30 } },
          },
        },
      },
    },
  },
}
