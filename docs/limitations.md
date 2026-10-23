# Known limitations

What the parser still gets wrong. Setup: [README](../README.md).

- Two definitions with no `;;` between them are sometimes read as one.
  - This happens when the second is indented deeper than the first, or when its `let` is followed by a matching `in` before the next `;;`.
  - In HOL Light about 90 definitions at the start of a line are still missed, mostly `let _ = ...`.
- Types and type constructors are not read.
- `definition_source` guesses which names are local to a definition by position, not by scope.
  - A name bound anywhere in the definition is treated as local everywhere in it.
  - A local name the guess misses shows up as a use of a global definition with the same name.
- Values made by functions other than the theorem commands (for example `new_axiom`, or `WORD_RULE ...`) are read as plain values, not theorems.
  - So `definition_source` shows their source like a function's, not a statement.
