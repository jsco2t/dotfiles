local schemas = {}
local ok, schemastore = pcall(require, "schemastore")
if ok then
  schemas = schemastore.json.schemas()
end

return {
  cmd = { "vscode-json-language-server", "--stdio" },
  filetypes = { "json", "jsonc" },
  root_markers = { ".git" },
  settings = {
    json = {
      schemas = schemas,
      validate = { enable = true },
    },
  },
}
