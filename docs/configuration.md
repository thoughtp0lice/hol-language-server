# Configuration

Both servers take the same flags: the MCP server `hol-light-code-mcp` and the language server `hol-language-server`. Setup: [README](../README.md).

- `--hol-path`: the HOL Light directory.
  - Must hold `hol.ml`. Without it the server stops and says why.
  - Default: `$HOL_LIGHT_DIR`.
- `--workspace`: the root of your project.
  - Default: the current directory. The language server uses the editor's open folder instead.
  - For s2n-bignum, whose proofs write `needs "arm/proofs/base.ml"`, use the s2n-bignum checkout.
- `--root`: a directory where `needs "..."` paths are searched. Repeat it for several.
  - Default: `.`, `{hol}`, `{workspace}`, tried in that order.
    - `.` is the directory of the file that has the `needs`.
    - `{hol}` is replaced by the HOL Light directory.
    - `{workspace}` is replaced by the workspace.
  - The first directory that has the file wins.
  - `loads "..."` paths ignore this list. They are always under the HOL Light directory.
  - Any other `{...}`, one whose value is not set, or an empty path stops the server.
- `--custom-import`, `--custom-theorem`, `--custom-definition`: your project's own command names. Repeat each for several.
  - Use them when a project wraps the built-in commands, for example `let my_prove (t, tac) = prove (t, tac)`.
  - `--custom-import NAME`: `NAME "file.ml"` loads a file, like `needs`. It is searched the same way as `needs`.
  - `--custom-theorem NAME`: `let X = NAME ...` is a theorem with a statement, like `prove`.
  - `--custom-definition NAME`: `let X = NAME ...` is a constant definition, like `new_definition`.
  - Without them, these definitions are read as plain values with no statement, and those loads are not followed.
  - Each name must be a plain OCaml name (letters, digits, `_`, `'`). Anything else stops the server.
- `--no-index-workspace`: do not read every `.ml`/`.hl` file of the workspace at startup.
  - By default they are all read.
  - Reading them matters: a file can use definitions it never loads itself, because the file that loads it loaded them first. Those are found only when the loading file was read.
