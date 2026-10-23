# hol-language-server

Static lookup for [HOL Light](https://github.com/jrh13/hol-light) sources. It parses source files, the files those load, and the core HOL Light sources. It does not run HOL Light, and it never reads the HOL Light `Help/` pages. Evaluating statements, goals, and tactics needs a live HOL Light process, such as the [HOL Light MCP server](https://github.com/jrh13/hol-light/tree/master/mcp).

It has two servers over one shared core: the MCP server `hol-light-code-mcp` with one tool, `definition_source`, and a language server with a subset of the editor features. It is written in Python. Failures are reported, never skipped silently ([docs/implementation.md](docs/implementation.md)).

## Install

Needs [uv](https://docs.astral.sh/uv/). From the checkout:

```sh
uv tool install -e .
```

This puts two commands on PATH (in `~/.local/bin`): `hol-language-server`, the language server, and `hol-light-code-mcp`, the MCP server. With `-e` they run the checkout itself, so edits apply without reinstalling.

For development, `uv sync` creates `.venv` from `uv.lock`; `uv run pytest` runs the tests and `basedpyright --pythonpath .venv/bin/python` the type check.

## Configuration

The server takes the non-REPL settings of vscode-hol-light as flags. Most setups need two:

- `--hol-path`: HOL Light directory (with `hol.ml`).
- `--workspace`: workspace root. For s2n-bignum, whose proofs use paths like `needs "arm/proofs/base.ml"`, point it at the s2n-bignum checkout.

If your project wraps `needs`, `prove` or `new_definition` in commands of its own, name them with `--custom-import`, `--custom-theorem` and `--custom-definition`.

Full flag reference: [docs/configuration.md](docs/configuration.md).

## MCP server

One read-only tool, `definition_source`: the source of a named definition (a tactic, theorem, or any value) and of the definitions it uses. Reference: [docs/mcp.md](docs/mcp.md).

Register it with any stdio MCP client. With Claude Code:

```sh
claude mcp add hol-light-code-mcp -- hol-light-code-mcp --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

Or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "hol-light-code-mcp": {
      "command": "hol-light-code-mcp",
      "args": ["--hol-path", "/path/to/hol-light", "--workspace", "/path/to/s2n-bignum"]
    }
  }
}
```

## Language server

Hover (theorem statements, value types, modules), Go to Definition (including the file named by `needs "..."`), document and workspace symbols, and warnings on loaded files that cannot be found. Reference: [docs/lsp.md](docs/lsp.md).

It speaks LSP over stdio and takes the same flags as the MCP server:

```sh
hol-language-server --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

### VS Code

The client in `vscode/` starts the `hol-language-server` command. It registers `.ml` and `.hl` files as HOL Light, with syntax highlighting. It needs Node.js and npm.

1. Install the server (see Install above).
2. Build the extension:

   ```sh
   cd vscode && npm install && npm run package
   ```

   This writes `vscode/hol-language-server-0.1.0.vsix`.
3. Install it: `code --install-extension vscode/hol-language-server-0.1.0.vsix`. Without the `code` command, open the Extensions view, then the `...` menu, then "Install from VSIX...", and pick the file.
4. Open the user settings as JSON (command palette, "Preferences: Open User Settings (JSON)") and add:

   ```json
   "hol-light.path": "/path/to/hol-light"
   ```

   If the editor does not find `hol-language-server` on PATH, also set `"hol-light.languageServer.command"` to its full path (`which hol-language-server`).
5. Open your project folder (for example the s2n-bignum checkout) and open an `.ml` file. Hover a theorem name to check that it works.
