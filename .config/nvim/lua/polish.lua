-- [[ vim config settings ]]
--

--vim.opt.number = true
--vim.opt.relativenumber = false

-- [[ custom keymaps ]]
--

-- reflow text
vim.keymap.set("n", "<leader>ww", "gwip", { desc = "reflow text" })

-- clear search highlights
vim.keymap.set("n", "<leader>nh", ":nohl<CR>", { desc = "Clear search highlights" })

-- perf testing
-- vim.o.cursorline = false

-- original file content:
--
-- This will run last in the setup process and is a good place to configure
-- things like custom filetypes. This just pure lua so anything that doesn't
-- fit in the normal config locations above can go here

-- Set up custom filetypes
-- vim.filetype.add {
--   extension = {
--     foo = "fooscript",
--   },
--   filename = {
--     ["Foofile"] = "fooscript",
--   },
--   pattern = {
--     ["~/%.config/foo/.*"] = "fooscript",
--   },
-- }
