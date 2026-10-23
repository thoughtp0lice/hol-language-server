# Known limitations

What the parser still gets wrong. Setup: [README](../README.md).

- Two definitions with no `;;` between them are sometimes read as one.
  - This happens when the second is indented deeper than the first, or when its `let` is followed by a matching `in` before the next `;;`.
  - In HOL Light about 90 definitions at the start of a line are still missed, mostly `let _ = ...`.
- Types and type constructors are not read.
- `definition_source` guesses which names are local to a definition by position, not by scope.
  - A name bound anywhere in the definition is treated as local everywhere in it.
  - A local name the guess misses shows up as a use of a global definition with the same name.
- Theorems made by commands outside the built-in list are read as plain values, with no statement.
  - Built in: `prove`, `ARITH_RULE`, `REAL_ARITH` and `VECTOR_ARITH` for theorems, and `new_definition`, `new_basic_definition` and `define` for definitions.
  - Not built in: other HOL Light rules that take the statement as their argument, and `new_axiom`.
  - In s2n-bignum this is about 79 theorems: 51 made with `BITBLAST_RULE`, 20 with `WORD_BLAST`, 8 with `WORD_RULE`.
  - For these, hover shows no statement, and `definition_source` shows the source like a function's.
  - Workaround: name the command with `--custom-theorem` ([configuration.md](configuration.md)), for example `--custom-theorem BITBLAST_RULE`.
