# Language server

Details of `lsp_server.py`. Usage: [README](../README.md).

## Capabilities

- `textDocument/hover`: theorem and definition statements, value types, and modules. No `Help/` pages.
- `textDocument/definition`: definitions, modules, and the file named by `needs "..."`.
- `textDocument/documentSymbol` and `workspace/symbol` (first 1000 case-insensitive substring matches).

## Settings and messages

- The server takes the same flags as the MCP server ([configuration.md](configuration.md)). Settings in `initializationOptions` override them.
- `initializationOptions` is either `{"hol-light": {...}}` or the settings object itself. Absent options are fine.
- Without `path` or `--hol-path`, the HOL Light directory is `$HOL_LIGHT_DIR`. Without `--workspace`, the workspace is the client's first workspace folder.
- Settings: `path` (string), `rootPaths` (list of strings), `autoIndex` and `indexWorkspace` (booleans). Any other key or type fails `initialize` with the reason.
- `initialize` also indexes the core HOL Light files, so a missing or wrong HOL Light directory fails it.
- `window/showMessage` warnings: once after `initialized` for loads in the workspace that cannot be found, and for an open file whenever the set of its loads that cannot be found changes.
- Parser warnings (a statement it skipped or misread) and files that are not valid UTF-8 go to stderr, which the client keeps as the server log.

## Not provided

Completion, diagnostics, execute commands, and the custom REPL requests (`hol-light/statementAt`, `tacticAt`, and the rest).
