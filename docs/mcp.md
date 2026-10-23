# MCP server

The MCP server `hol-light-code-mcp` lets an AI assistant read HOL Light source code by name. Setup: [README](../README.md).

## How it behaves

- Read-only.
  - It parses files. It never runs HOL Light, so it cannot say whether a proof works.
- You ask by name, not by cursor position.
  - Example: `ARM_STEPS_TAC`, or a name inside a module, `Hol.REFL`.
  - Answers hold statements and source text, not file locations.
- Startup.
  - It reads the core HOL Light files first, then every `.ml`/`.hl` file of the workspace.
  - Calls made during startup wait until it is done.
  - It stops at once without a HOL Light directory (one with `hol.ml`), or with a search path it cannot fill in ([configuration.md](configuration.md)).
- Warnings, printed to stderr.
  - A file named by `needs`, `loads` or `loadt` that cannot be found.
  - A statement the parser could not read.
- Files on disk that changed.
  - A call with `file` re-reads that file and the files it loads, if they changed since the last read.
- File paths may be absolute or relative to the workspace.

## Tools

- `definition_source`: the source of a definition, and what it is built from.
  - Works for tactics, conversions, rules, any other OCaml value, theorems, and constant definitions.
  - `references` lists the theorems and definitions the source uses, each with its statement.
    - A plain function used in the source has no statement, so it is left out. Read its name from the source and ask again, or use `depth`.
    - A name with no definition in the files read is left out. Nothing is looked up elsewhere.
  - Theorems and constant definitions come with their statements. Their proofs are not followed.
  - A name defined in several files (for example a helper tactic each proof file defines for itself) gives one entry per definition.
    - Pass `file` to get only the one that file sees.
    - The same definition reached under two paths is listed once.
  - Arguments.
    - `name`: the name to look up.
    - `file` (optional): look only in this file and the files it loads. With it, `unresolved_loads` lists the files they load that could not be found, so their definitions are missing. Present only when there are any.
    - `depth` (default 0, at most 10): also include the sources of the functions it uses, this many levels deep. Each extra entry names, in `via`, the definition that uses it.
    - `max_chars` (default 8000): longest source returned per definition. A longer one is cut and marked `truncated`, and only the names in the part returned are listed.
    - `max_total_chars` (default 20000): longest whole answer. Definitions that do not fit are listed by name in `not_expanded`, and can be asked for again. The first definition is always included.
