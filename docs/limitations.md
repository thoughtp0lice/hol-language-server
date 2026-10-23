# Known limitations

Usage: [README](../README.md).

- Two items not separated by `;;` are still read as one when the second is indented deeper than the first or its `let` has a matching `in` before the next `;;`. In HOL Light about 90 column-0 bindings are still missed, mostly `let _ = ...`.
- Types and type constructors are not indexed.
- `definition_source` finds names bound inside an item by offset, not by scope: a name bound anywhere in the item is left out everywhere in it, and a binding the heuristic misses shows up as a reference to a global definition of the same name. Values built from theorem-producing functions other than the theorem commands (`new_axiom`, `WORD_RULE ...`) are values, so their source is expanded like a function's.
