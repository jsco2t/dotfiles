-- https://github.com/yazi-rs/plugins/tree/main/git.yazi

-- style info for git markers
th.git = th.git or {}
th.git.modified = ui.Style():fg("blue")
th.git.deleted = ui.Style():fg("red"):bold()
th.git.unknown_sign = " "
th.git.modified_sign = "M"
th.git.deleted_sign = "D"
th.git.clean_sign = "✔"
th.git.added_sign = "+"
th.git.untracked_sign = "U"
th.git.updated_sign = "!"

require("git"):setup {
	-- Order of status signs showing in the linemode
	order = 1500,
}
