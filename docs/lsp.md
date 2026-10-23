# Language server

The language server `hol-language-server` gives an editor lookups over HOL Light source files. Setup: [README](../README.md).

## What it does

- Hover: shows what the word under the cursor is.
  - A theorem or definition: its statement.
  - Any other value: its name, and its type when the source writes one.
  - A module: its name.
  - It does not show the HOL Light `Help/` pages.
- Go to Definition: jumps to where a name is defined.
  - Works for definitions and modules.
  - On `needs "..."`, it opens the file named.
- Symbols.
  - The outline of the open file: every definition and module in it.
  - Search across all files read: names containing the search text, ignoring case, at most 1000 results.
- Warnings on missing files.
  - A `needs`, `loads` or `loadt` (or custom import) whose file cannot be found gets a warning underline on the file name.
  - This covers the open file and every file it loads. Those show in the Problems panel.
  - The underline goes away once the file is found, for example after fixing the name.

## Settings

- The server takes the same flags as the MCP server ([configuration.md](configuration.md)).
- An editor can also send settings when it starts the server (the LSP `initializationOptions`). These win over the flags.
  - They may be wrapped as `{"hol-light": {...}}` or sent bare.
  - `path` (text): the HOL Light directory.
  - `rootPaths` (list of text): where `needs` paths are searched.
  - `autoIndex` (true/false): read each file as it is opened or edited. Default true.
  - `indexWorkspace` (true/false): read every `.ml`/`.hl` file of the workspace at startup. Default true.
  - `customImports`, `customTheorems`, `customDefinitions` (lists of text): your project's own command names, the same as the `--custom-*` flags.
  - Any other setting, or a value of the wrong type, stops startup with the reason.
- Defaults when nothing is set.
  - HOL Light directory: `$HOL_LIGHT_DIR`.
  - Workspace: the first folder open in the editor (`--workspace` overrides it).
- Startup reads the core HOL Light files, so a missing or wrong HOL Light directory stops it.

## Messages

- A warning pop-up once at startup, for files the workspace loads that cannot be found.
- The server log (stderr, which the editor keeps).
  - Statements the parser could not read.
  - Files that are not valid UTF-8. They are still read, with the bad bytes replaced.

## Not provided

- Completion.
- Diagnostics other than missing files, such as type errors.
- Editor commands.
- Anything that needs a running HOL Light, such as sending a statement or tactic to it.
