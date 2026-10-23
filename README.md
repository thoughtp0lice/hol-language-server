# hol-language-server

Static lookup for [HOL Light](https://github.com/jrh13/hol-light) sources. It parses source files, the files those load, and the core HOL Light sources. It does not run HOL Light, and it never reads the HOL Light `Help/` pages. Evaluating statements, goals, and tactics needs a live HOL Light process, such as the [HOL Light MCP server](https://github.com/jrh13/hol-light/tree/master/mcp).

It has two servers over one shared core: the MCP server `hol-light-static` with one tool, `definition_source`, and a language server with a subset of the editor features. It is written in Python. Failures are reported, never skipped silently ([docs/implementation.md](docs/implementation.md)).

## Build

There is no build step. The environment is managed by [uv](https://docs.astral.sh/uv/): Python 3.12 (pinned in `.python-version`) and the dependencies in `pyproject.toml`, locked in `uv.lock`.

```sh
uv sync                  # creates .venv
uv run python mcp_server.py --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
uv run pytest            # unit tests plus MCP and LSP tests over stdio
basedpyright --pythonpath .venv/bin/python   # type check, configured in pyproject.toml
```

The registrations below run `.venv/bin/python` directly, so they need `uv sync` once and no uv afterwards.

## Configuration

The server takes the non-REPL settings of vscode-hol-light as flags. Most setups need two:

- `--hol-path`: HOL Light directory (with `hol.ml`).
- `--workspace`: workspace root. For s2n-bignum, whose proofs use paths like `needs "arm/proofs/base.ml"`, point it at the s2n-bignum checkout.

Full flag reference: [docs/configuration.md](docs/configuration.md).

## MCP server

One read-only tool, `definition_source`: the source of a named definition (a tactic, theorem, or any value) and of the definitions it uses. Reference: [docs/tools.md](docs/tools.md).

Run `uv sync` once, then register it with any stdio MCP client. With Claude Code:

```sh
claude mcp add hol-light-static -- /path/to/hol-language-server/.venv/bin/python /path/to/hol-language-server/mcp_server.py \
    --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

Or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "hol-light-static": {
      "command": "/path/to/hol-language-server/.venv/bin/python",
      "args": ["/path/to/hol-language-server/mcp_server.py",
               "--hol-path", "/path/to/hol-light",
               "--workspace", "/path/to/s2n-bignum"]
    }
  }
}
```

## Language server

Hover (theorem statements, value types, modules), Go to Definition (including the file named by `needs "..."`), and document and workspace symbols. Reference: [docs/lsp.md](docs/lsp.md).

It speaks LSP over stdio and takes the same flags as the MCP server:

```sh
uv run python lsp_server.py --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

### VS Code

The client in `vscode/` starts `.venv/bin/python lsp_server.py` from this checkout. It registers `.ml` and `.hl` files as HOL Light, with syntax highlighting. It needs Node.js and npm.

1. Set up the server once, from the repository root: `uv sync`.
2. Build the extension:

   ```sh
   cd vscode && npm install && npm run package
   ```

   This writes `vscode/hol-language-server-0.1.0.vsix`.
3. Install it: `code --install-extension vscode/hol-language-server-0.1.0.vsix`. Without the `code` command, open the Extensions view, then the `...` menu, then "Install from VSIX...", and pick the file.
4. Open the user settings as JSON (command palette, "Preferences: Open User Settings (JSON)") and add:

   ```json
   "hol-light.languageServer.repository": "/path/to/hol-language-server",
   "hol-light.path": "/path/to/hol-light"
   ```

5. Open your project folder (for example the s2n-bignum checkout) and open an `.ml` file. Hover a theorem name to check that it works.
