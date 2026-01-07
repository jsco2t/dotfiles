#!/usr/bin/env bash

# more info: https://github.com/helix-editor/helix/wiki/Language-Server-Configurations

# go
go install golang.org/x/tools/gopls@latest          # LSP
go install github.com/go-delve/delve/cmd/dlv@latest # Debugger
go install golang.org/x/tools/cmd/goimports@latest  # Formatter
brew install golangci-lint
go install mvdan.cc/gofumpt@latest
go install honnef.co/go/tools/cmd/staticcheck@latest

# toml
cargo install taplo-cli --locked --features lsp

# rust
rustup component add rust-analyzer

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

# markdown linting support
brew install markdownlint-cli
brew install efm-langserver
brew install prettier
brew install marksman

# adding harper (use instead of vale)
cargo install harper-ls --locked
#brew install harper

# markdown/code formatting
brew install dprint
