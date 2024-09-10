#!/usr/bin/env bash

# more info: https://github.com/helix-editor/helix/wiki/Language-Server-Configurations

# go
go install golang.org/x/tools/gopls@latest                             # LSP
go install github.com/go-delve/delve/cmd/dlv@latest                    # Debugger
go install golang.org/x/tools/cmd/goimports@latest                     # Formatter
go install github.com/nametake/golangci-lint-langserver@latest         # Linter
go install github.com/golangci/golangci-lint/cmd/golangci-lint@v1.60.1 # Linter (required by previous)
go install mvdan.cc/gofumpt@latest
go install honnef.co/go/tools/cmd/staticcheck@latest

# toml
cargo install taplo-cli --locked --features lsp

# rust
rustup component add rust-analyzer

# markdown
cargo install --git https://github.com/Feel-ix-343/markdown-oxide.git markdown-oxide
brew install ltex-ls

# ansible
npm i -g @ansible/ansible-language-server

#hx --grammar fetch
#hx --grammar build

# helm
brew install helm-ls

# json
npm i -g vscode-langservers-extracted

# python
npm install --location=global pyright

# terraform
brew install hashicorp/tap/terraform-ls

# yaml
npm i -g yaml-language-server@next

# vale (spelling, grammar, style linting for written content)
# brew install vale

# The `vale-ls` tool will also need to be installed. The easy way to do this is:
#  - Clone: https://github.com/errata-ai/vale-ls
#  - Navigate into the `vale-ls` directory
#  - Run:
#    cargo install --path .
#

# markdown linting support
brew install markdownlint-cli
brew install efm-langserver

# adding harper (use instead of vale)
cargo install harper-ls --locked
