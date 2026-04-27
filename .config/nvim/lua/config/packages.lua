-- Plugin installation via vim.pack (Neovim 0.12 built-in).
-- Every plugin is pinned to a specific commit hash for supply chain safety.
-- Hashes sourced from the last known-good lazy-lock.json.
--
-- To update: vim.pack.update()   (shows diff + confirmation buffer)
-- To revert: git checkout -- nvim-pack-lock.json, then :restart
-- To freeze:  set version = <commit hash from lockfile>

local gh = function(x) return "https://github.com/" .. x end

vim.pack.add({
  -- Colorscheme
  { src = gh("navarasu/onedark.nvim"), version = "213c23ae45a04797572242568d5d51937181792d" },

  -- Treesitter (parser management)
  { src = gh("nvim-treesitter/nvim-treesitter"), version = "53f6ce29df5841ce26e5a9f06fb371088b8d8031" },

  -- UI
  { src = gh("folke/snacks.nvim"), version = "e6fd58c82f2f3fcddd3fe81703d47d6d48fc7b9f" },
  { src = gh("nvim-lualine/lualine.nvim"), version = "47f91c416daef12db467145e16bed5bbfe00add8" },
  { src = gh("folke/which-key.nvim"), version = "3aab2147e74890957785941f0c1ad87d0a44c15a" },
  { src = gh("folke/trouble.nvim"), version = "bd67efe408d4816e25e8491cc5ad4088e708a69a" },
  { src = gh("echasnovski/mini.icons"), version = "5b9076dae1bfbe47ba4a14bc8b967cde0ab5d77e" },

  -- Editor
  { src = gh("lewis6991/gitsigns.nvim"), version = "7c4faa3540d0781a28588cafbd4dd187a28ac6e3" },
  { src = gh("stevearc/conform.nvim"), version = "086a40dc7ed8242c03be9f47fbcee68699cc2395" },
  { src = gh("mfussenegger/nvim-lint"), version = "606b823a57b027502a9ae00978ebf4f5d5158098" },
  { src = gh("echasnovski/mini.ai"), version = "4b0a6207341d895b6cfe9bcb1e4d3e8607bfe4f4" },
  { src = gh("echasnovski/mini.pairs"), version = "b7fde3719340946feb75017ef9d75edebdeb0566" },
  { src = gh("folke/flash.nvim"), version = "fcea7ff883235d9024dc41e638f164a450c14ca2" },
  { src = gh("folke/todo-comments.nvim"), version = "31e3c38ce9b29781e4422fc0322eb0a21f4e8668" },
  { src = gh("folke/persistence.nvim"), version = "b20b2a7887bd39c1a356980b45e03250f3dce49c" },

  -- Markdown
  { src = gh("MeanderingProgrammer/render-markdown.nvim"), version = "e3c18ddd27a853f85a6f513a864cf4f2982b9f26" },

  -- Language: Rust
  { src = gh("mrcjkb/rustaceanvim"), version = "f2f0c1231a5b019dbc1fd6dafac1751c878925a3" },
  { src = gh("saecki/crates.nvim"), version = "ac9fa498a9edb96dc3056724ff69d5f40b898453" },

  -- Language: Python
  { src = gh("linux-cultist/venv-selector.nvim"), version = "42e8faadf9b819654f29eb1a785797a3a328f301" },

  -- Language: JSON/YAML schema catalog
  { src = gh("b0o/SchemaStore.nvim"), version = "cf2b276dc88696b35d55ea4bd55dfaf7d608c9a2" },

  -- Utility (dependency for todo-comments, etc.)
  { src = gh("nvim-lua/plenary.nvim"), version = "b9fd5226c2f76c951fc8ed5923d85e4de065e509" },
})
