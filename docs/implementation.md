# Implementation

How the parser and index differ from vscode-hol-light, and the source layout. Usage: [README](../README.md).

## Differences from vscode-hol-light

The parser and index were checked against s2n-bignum and HOL Light by a corpus check (removed in the lookup-only trim), and these changes came out of that check. Each fixes a case where vscode-hol-light misses or misreads definitions.

- `let X = time prove(...)` is a theorem with its statement (2536 s2n-bignum theorems were plain values).
- Every binding of `let a = ... and b = ...` is indexed, not only the first.
- Optional parameters with default values, `?(x = e)` and `?(x : t = e)`, no longer drop the definition (`ARM_SIM_TAC`, `X86_SIM_TAC`, `ADD_IBT_RULE`).
- Character literals such as `'"'` no longer start a string. In vscode-hol-light the rest of HOL Light's `hol_loader.ml` (`needs`, `loads`, `loadt`) was misread, and so were parts of 19 other files of the HOL Light tree.
- Numeric literals are tokens: `0x48` no longer yields the identifier `x48` in identifier analysis.
- A `let` at the start of a line, not indented deeper than the current item and not part of a `let ... in` expression, starts a new item even without `;;`. Inside modules this recovers HOL Light's kernel (`module Hol` in `fusion.ml`: 69 definitions instead of 1); at the top level it recovers about 3000 HOL Light definitions such as `can` in `lib.ml`.
- Top-level `open` and `include` in a dependency apply to the files loaded after it (`include Hol` makes `concl`, `mk_comb`, `REFL`, ... visible).
- A file also sees what the files that load it loaded before it (s2n-bignum's `arm/proofs/arm.ml` uses `decode.ml` because `base.ml` loads both). This needs the loading file in the index, hence workspace indexing.
- A request that arrives while the core HOL Light files are being indexed waits for indexing to finish.
- Each definition records the whole item that defines it, from its `let` to the `;;` or the start of the next item. `definition_source` returns that text and the names it uses, leaving out names bound inside the item itself (parameters, `let ... in`, `fun`, match patterns).

## Reported failures

No failure is skipped without a word:

- No HOL Light directory, or one without `hol.ml`: the server stops (the MCP server at startup, the language server in `initialize`).
- Loads that cannot be found: `unresolved_loads` in the MCP result when `file` is given, a startup warning for the workspace, and editor warnings.
- Editor settings of the wrong type or with an unknown key, and root paths with an unknown or unset placeholder: an error.
- A file or directory that cannot be read while indexing: an error instead of a skip.
- Statements the parser skips or misreads, and files that are not valid UTF-8 (still decoded with replacement characters): a warning on stderr.

## Layout

- `core/`: the parser, index, and name-reference search. `service.py` is the API both servers use. Positions sit beside the MCP server's offsets; the parser computes both in one pass.
- `mcp_server.py`: the MCP server entry point.
- `lsp_server.py`: the LSP server entry point (pygls, stdio).
- `tests/`: tests and example files. `examples/hol` is a minimal stand-in for a HOL Light directory.
