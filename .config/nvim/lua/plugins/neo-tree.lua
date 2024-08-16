---@type LazySpec
return {
  "nvim-neo-tree/neo-tree.nvim",
  opts = {
    sources = { "filesystem" },
    filesystem = {
      window = {
        mappings = {
          ["\\"] = "close_window",
          ["<leader>e"] = "close_window",
        },
      },
      filtered_items = {
        hide_hidden = false,
        hide_dotfiles = false,
        hide_gitignored = false,
        never_show = {
          ".DS_Store",
          "thumbs.db",
        },
      },
    },
  },
  config = function(_, opts)
    opts.sources = { "filesystem" }
    opts.source_selector = {
      --winbar = true,
      content_layout = "left",
    }
    require("neo-tree").setup(opts)
  end,
}
