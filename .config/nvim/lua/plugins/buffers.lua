return {
  -- auto close buffers
  {
    'chrisgrieser/nvim-early-retirement',
    config = true,
    event = 'VeryLazy',
    opts = function(_, opts)
      opts.minimumBufferNum = 3
      opts.retirementAgeMins = 10
    end,
  },
}
