# Configuration

Every flag of the MCP server `hol-light-code-mcp` (`mcp_server.py`) and of the language server `hol-language-server` (`lsp_server.py`), which take the same flags. Usage: [README](../README.md).

- HOL Light directory
  - Flag: `--hol-path`.
  - Default: `$HOL_LIGHT_DIR`.
  - Holds `hol.ml`. Required: without it, or with a directory that has no `hol.ml`, the server stops with the reason.
- Import search paths
  - Flag: `--root` (repeatable).
  - Default: `[".", "{hol}", "{workspace}"]`.
  - `.` is the directory of the file being resolved.
  - `{hol}` is the HOL Light directory.
  - `{workspace}` is the workspace root.
  - Any other placeholder, a placeholder whose value is unset, or an empty path stops the server.
- Workspace root
  - Flag: `--workspace`.
  - Default: current directory.
- Index every `.ml`/`.hl` file of the workspace at startup
  - Flag: off with `--no-index-workspace`.
  - Default: on.
