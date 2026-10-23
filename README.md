# hol-language-server

Static lookup for [HOL Light](https://github.com/jrh13/hol-light) sources, extracted from the [vscode-hol-light](https://github.com/hol-light-family/vscode-hol-light) extension (commit `c5f0189`). It parses source files, the files those load, and the core HOL Light sources. It does not run HOL Light, and it never reads the HOL Light `Help/` pages. Evaluating statements, goals, and tactics needs a live HOL Light process, such as the [HOL Light MCP server](https://github.com/jrh13/hol-light/tree/master/mcp).

This variant has two servers over one shared core: the MCP server `hol-light-static` with one tool, `definition_source`, and a language server with a subset of the editor features. It is Python, ported from the TypeScript server one module at a time; the parser, index, and tool behave the same, except that failures the TypeScript server skipped silently are reported ([docs/implementation.md](docs/implementation.md)).

## Build

There is no build step. The environment is managed by [uv](https://docs.astral.sh/uv/): Python 3.12 (pinned in `.python-version`) and the dependencies in `pyproject.toml`, locked in `uv.lock`.

```sh
uv sync                  # creates .venv
uv run python server.py --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
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

Register it with any stdio MCP client. With Claude Code:

```sh
claude mcp add hol-light-static -- /path/to/hol-language-server/.venv/bin/python /path/to/hol-language-server/server.py \
    --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

Or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "hol-light-static": {
      "command": "/path/to/hol-language-server/.venv/bin/python",
      "args": ["/path/to/hol-language-server/server.py",
               "--hol-path", "/path/to/hol-light",
               "--workspace", "/path/to/s2n-bignum"]
    }
  }
}
```

The s2n-bignum-hol-light-llm description pipeline registers it as `hol-light-static`.

All tools are read-only and take names, not cursor positions. Results carry statements and sources, not file locations. Files may be absolute or relative to the workspace. At startup the server indexes the core HOL Light files and the workspace; tools wait for that. It refuses to start without a HOL Light directory (one with `hol.ml`) or with a root path that does not expand, and logs a warning for each load in the workspace it cannot find and each statement the parser skips. Every call re-indexes the file it touches and its dependencies when they changed on disk.

Tool: `definition_source`, the source of a named definition and the names it is built from. Full reference: [docs/tools.md](docs/tools.md).

## Language server

```sh
uv run python lsp_server.py --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

It speaks LSP over stdio and takes the same flags as the MCP server. Settings in `initializationOptions` (either `{"hol-light": {...}}` or the options themselves) override the flags: `path`, `rootPaths`, `autoIndex`, `indexWorkspace`. Without either, the path is `$HOL_LIGHT_DIR`; without a workspace flag, the workspace is the client's first workspace folder. An unknown setting, a value of the wrong type, or no HOL Light directory fails `initialize` with the reason. Loads that cannot be found are shown as warning messages. Full reference: [docs/lsp.md](docs/lsp.md).

Provided features: hover (theorem statements, value types, modules), Go to Definition (including the file named by `needs "..."`), document and workspace symbols.

With Emacs eglot, for `.ml` buffers:

```elisp
(add-to-list 'eglot-server-programs
             '(tuareg-mode . ("/path/to/hol-language-server/.venv/bin/python" "/path/to/hol-language-server/lsp_server.py"
                              "--hol-path" "/path/to/hol-light"
                              "--workspace" "/path/to/s2n-bignum")))
```

With VSCode, point any generic LSP client extension at the same command. Syntax highlighting is not part of LSP here.

## Not included

- Everything that needs a running HOL Light: the REPL and server terminals, sending statements and tactics, goal view, notebook execution, search results, execution highlighting, and hover information taken from a live session.
- Editor features beyond the language server's subset: completion, diagnostics, and execute commands ([docs/lsp.md](docs/lsp.md)).
- Statement, term, and tactic selection, dependency listing, and the `search` command builder.

## Known limitations

Full list: [docs/limitations.md](docs/limitations.md). Parser and index behavior versus vscode-hol-light: [docs/implementation.md](docs/implementation.md). Measured results on s2n-bignum: [docs/evaluation.md](docs/evaluation.md).

## License

MIT, as vscode-hol-light (Copyright (c) 2018 Alexey Solovyev).
