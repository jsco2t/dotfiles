return {
  {
    "nvim-neotest/neotest",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "nvim-neotest/nvim-nio",
      "nvim-treesitter/nvim-treesitter",
      "fredrikaverpil/neotest-golang",
    },
    opts = {
      adapters = {
        ["neotest-golang"] = {
          -- default args include `-race` (race detection) which doesn't appear to be well
          -- supported on arm64
          go_test_args = {
            "-v",
            "-count=1",
            "-timeout=60s",
          },
          dap_go_enabled = true,
        },
      },
    },
  },
}
