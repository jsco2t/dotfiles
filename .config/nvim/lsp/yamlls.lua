local schemas = {}
local ok, schemastore = pcall(require, "schemastore")
if ok then
  schemas = schemastore.yaml.schemas()
end

return {
  cmd = { "yaml-language-server", "--stdio" },
  filetypes = { "yaml", "yaml.docker-compose", "yaml.gitlab" },
  root_markers = { ".git" },
  settings = {
    yaml = {
      schemaStore = { enable = false, url = "" },
      schemas = schemas,
    },
  },
}
