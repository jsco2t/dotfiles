return {
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
    lazy = false,
    -- See Commands section for default commands if you want to lazy load on them
    keys = {
      { "<leader>ac", "<cmd>CopilotChat<cr>", desc = "CopilotChat - Open chat" },
      { "<leader>ar", "<cmd>CopilotChatReview<cr>", desc = "CopilotChat - Review code" },
      { "<leader>ae", "<cmd>CopilotChatExplain<cr>", desc = "CopilotChat - Explain code" },
      { "<leader>af", "<cmd>CopilotChatFixCode<cr>", desc = "CopilotChat - Fix code" },
      { "<leader>at", "<cmd>CopilotChatTests<cr>", desc = "CopilotChat - Generate tests" },
      { "<leader>ad", "<cmd>CopilotChatDocs<cr>", desc = "CopilotChat - Add documentation" },
      {
        "<leader>ap",
        function()
          local actions = require "CopilotChat.actions"
          require("CopilotChat.integrations.fzflua").pick(actions.prompt_actions())
        end,
        desc = "CopilotChat - Prompt actions",
      },
    },
  },
}
