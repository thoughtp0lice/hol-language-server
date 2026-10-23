# MCP tool

The server exposes one tool. Conventions (read-only, name lookup, paths, indexing): [README](../README.md).

- `definition_source`
  - Source of a tactic's (or any value's) definition and the theorems and definitions it uses, resolved as Go to Definition. References that carry nothing beyond a name are left out.
  - With `depth`, helper sources too, recursively, within `max_total_chars`.
  - Byte-identical definitions indexed under two paths are reported once.
  - Names with no indexed definition are left out, never fetched from elsewhere.
  - With `file`, `unresolved_loads` lists the files it or its dependencies load that could not be found, since their definitions are missing. Present only when there are any.
  - Arguments: `name`, `file`, `depth` (default 0), `max_chars` (default 8000), `max_total_chars` (default 20000).
