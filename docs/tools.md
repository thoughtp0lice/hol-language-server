# MCP tool

The server exposes one tool. Setup: [README](../README.md).

## Conventions

- The tool is read-only and takes names, not cursor positions. Results carry statements and sources, not file locations.
- Files may be absolute or relative to the workspace.
- At startup the server indexes the core HOL Light files and the workspace; calls wait for that.
- It refuses to start without a HOL Light directory (one with `hol.ml`) or with a root path that does not expand.
- It logs a warning for each load in the workspace it cannot find and each statement the parser skips.
- Every call re-indexes the file it touches and its dependencies when they changed on disk.

## Tools


- `definition_source`
  - Source of a tactic's (or any value's) definition and the theorems and definitions it uses, resolved as Go to Definition. References that carry nothing beyond a name are left out.
  - With `depth`, helper sources too, recursively, within `max_total_chars`.
  - Byte-identical definitions indexed under two paths are reported once.
  - Names with no indexed definition are left out, never fetched from elsewhere.
  - With `file`, `unresolved_loads` lists the files it or its dependencies load that could not be found, since their definitions are missing. Present only when there are any.
  - Arguments: `name`, `file`, `depth` (default 0), `max_chars` (default 8000), `max_total_chars` (default 20000).
