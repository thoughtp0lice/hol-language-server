# Implementation

How the parser reads HOL Light files, what it reports, and where the code lives. Setup: [README](../README.md).

## Differences from vscode-hol-light

The parser was checked against every file of s2n-bignum and HOL Light. Each change below fixes definitions vscode-hol-light missed or misread.

- `let X = time prove(...)` is a theorem, with its statement.
  - Before: 2536 s2n-bignum theorems were read as plain values.
- `let a = ... and b = ...` gives both `a` and `b`, not only `a`.
- Optional arguments with defaults, `?(x = e)` and `?(x : t = e)`, no longer lose the definition.
  - Examples: `ARM_SIM_TAC`, `X86_SIM_TAC`, `ADD_IBT_RULE`.
- A quote character written as `'"'` no longer starts a string.
  - Before: the rest of HOL Light's `hol_loader.ml` was misread, and parts of 19 other HOL Light files.
- Numbers such as `0x48` are read as numbers, not as the name `x48`.
- A new `let` at the start of a line starts a new definition, even without `;;` before it.
  - It must not be indented deeper than the current definition, and not be the start of a `let ... in`.
  - Inside modules: HOL Light's kernel (`module Hol` in `fusion.ml`) gives 69 definitions instead of 1.
  - At the top level: about 3000 more HOL Light definitions, such as `can` in `lib.ml`.
- `open` and `include` written outside any module, in a loaded file, apply to the files loaded after it.
  - Example: `include Hol` makes `concl`, `mk_comb` and `REFL` visible.
- A file also sees what the files that load it loaded before it.
  - Example: s2n-bignum's `arm/proofs/arm.ml` uses `decode.ml`, because `base.ml` loads both.
  - This needs the loading file read too, which is why the whole workspace is read at startup.
- A request made while the core HOL Light files are still being read waits for them.
- Each definition keeps its whole text, from its `let` to the `;;` or to the next definition.
  - `definition_source` returns that text and the names it uses.
  - Names bound inside the definition itself are left out: its arguments, `let ... in`, `fun`, and `match` patterns.

## Reported failures

Nothing fails silently.

- No HOL Light directory, or one without `hol.ml`: the server stops.
  - The MCP server stops at startup. The language server fails when the editor starts it.
- Files named by `needs`, `loads` or `loadt` that cannot be found.
  - MCP: listed in `unresolved_loads` when a call names a `file`, and as a warning at startup.
  - Language server: a warning underline on each file name that cannot be found, and a pop-up at startup.
- A bad editor setting (unknown name or wrong type), or a search path with an unknown or unset `{...}`: an error.
- A file or directory that cannot be read: an error, not a skip.
- Printed as warnings to stderr:
  - statements the parser could not read;
  - files that are not valid UTF-8. They are still read, with the bad bytes replaced.

## Layout

- `hol_language_server_core/`: the parser, the index of everything read, and the lookups.
  - `service.py` holds the functions both servers call.
- `mcp_server.py`: the MCP server, installed as the `hol-light-code-mcp` command.
- `lsp_server.py`: the language server, installed as the `hol-language-server` command. Built on pygls, over stdin and stdout.
- `vscode/`: the VS Code extension that starts the language server.
- `tests/`: tests and small example files. `tests/examples/hol` stands in for a HOL Light directory.
