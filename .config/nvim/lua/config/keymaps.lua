-- [[ custom keymaps ]]
--

--- reflow text
vim.keymap.set("n", "<leader>ww", "gwip", { desc = "reflow text" })

-- clear search highlights
vim.keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })

-- buffer navigation (can also use `[b` and `]b`)
vim.keymap.set("n", "<S-Tab>", ":bprev<CR>", { desc = "previous buffer", noremap = true })
vim.keymap.set("n", "<Tab>", ":bnext<CR>", { desc = "next buffer", noremap = true })
vim.keymap.set("n", "<leader>b", ":FzfLua buffers<CR>", { desc = "Show buffers", noremap = true })
vim.keymap.set("n", "<leader>bs", ":FzfLua buffers<CR>", { desc = "Show buffers", noremap = true })

-- telescope utilities
vim.keymap.set("n", "<leader>k", ":FzfLua keymaps<CR>", { desc = "Show keymaps", noremap = true })
vim.keymap.set("n", "<leader>s", ":FzfLua lsp_document_symbols<CR>", { desc = "Show doc symbols", noremap = true })
vim.keymap.set("n", "<leader>D", ":FzfLua diagnostics_document<CR>", { desc = "Show diagnostics", noremap = true })
