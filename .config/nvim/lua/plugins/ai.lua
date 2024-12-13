return {
  -- {
  --   "codota/tabnine-nvim",
  --   --lazy = true,
  --   priority = 1000,
  --   build = "./dl_binaries.sh",
  --   config = function()
  --     require("tabnine").setup {
  --       disable_auto_comment = true,
  --       accept_keymap = "<Tab>",
  --       dismiss_keymap = "<C-]>",
  --       debounce_ms = 800,
  --       suggestion_color = { gui = "#808080", cterm = 244 },
  --       exclude_filetypes = { "TelescopePrompt", "NvimTree" },
  --       log_file_path = nil, -- absolute path to Tabnine log file
  --       ignore_certificate_errors = false,
  --     }
  --   end,
  -- },
  -- {
  --   "olimorris/codecompanion.nvim",
  --   dependencies = {
  --     "nvim-lua/plenary.nvim",
  --     "nvim-treesitter/nvim-treesitter",
  --     "MeanderingProgrammer/render-markdown.nvim",
  --   },
  --   config = function()
  --     require("codecompanion").setup {
  --       strategies = {
  --         chat = {
  --           adapter = "ollama_cl",
  --         },
  --         inline = {
  --           adapter = "ollama_cl",
  --         },
  --       },
  --       adapters = {
  --         -- if switching between models - you will need to close out
  --         -- running models to prevent OOM situations
  --         --
  --         ollama_mn = function()
  --           return require("codecompanion.adapters").extend("ollama", {
  --             name = "mn", -- Give this adapter a different name to differentiate it from the default ollama adapter
  --             schema = {
  --               model = {
  --                 default = "mistral-nemo:12b",
  --               },
  --               num_ctx = {
  --                 default = 16384,
  --               },
  --               num_predict = {
  --                 default = -1,
  --               },
  --             },
  --           })
  --         end,
  --         ollama_lama3_2 = function()
  --           return require("codecompanion.adapters").extend("ollama", {
  --             name = "lama3-2", -- Give this adapter a different name to differentiate it from the default ollama adapter
  --             schema = {
  --               model = {
  --                 default = "llama3.2:3b-instruct-q8_0",
  --               },
  --               num_ctx = {
  --                 default = 16384,
  --               },
  --               num_predict = {
  --                 default = -1,
  --               },
  --             },
  --           })
  --         end,
  --         ollama_codestral = function()
  --           return require("codecompanion.adapters").extend("ollama", {
  --             name = "codestral", -- Give this adapter a different name to differentiate it from the default ollama adapter
  --             schema = {
  --               model = {
  --                 default = "codestral:v0.1",
  --               },
  --               num_ctx = {
  --                 default = 16384,
  --               },
  --               num_predict = {
  --                 default = -1,
  --               },
  --             },
  --           })
  --         end,
  --         ollama_cl = function()
  --           return require("codecompanion.adapters").extend("ollama", {
  --             name = "cl", -- Give this adapter a different name to differentiate it from the default ollama adapter
  --             schema = {
  --               model = {
  --                 default = "codellama:13b",
  --               },
  --               num_ctx = {
  --                 default = 16384,
  --               },
  --               num_predict = {
  --                 default = -1,
  --               },
  --             },
  --           })
  --         end,
  --       },
  --     }
  --   end,
  -- },
  {
    "zbirenbaum/copilot.lua",
    config = function() require("copilot").setup {} end,
  },
  {
    "CopilotC-Nvim/CopilotChat.nvim",
    dependencies = {
      { "zbirenbaum/copilot.lua" }, -- or github/copilot.vim
      { "nvim-lua/plenary.nvim" }, -- for curl, log and async functions
    },
    build = "make tiktoken", -- Only on MacOS or Linux
    opts = {
      -- See Configuration section for options
    },
    -- See Commands section for default commands if you want to lazy load on them
  },
}
