# Evaluation on s2n-bignum

Figures from a check over all of s2n-bignum `4d1356a7` with HOL Light `cba9198`.

- Not measured again here. The script that produced them was removed.
- Only the figures about reading files and definitions are kept.

## Results

- Reading files at startup.
  - 798 s2n-bignum files plus the 109 HOL Light files they load, in about 1.8 s, using 180 MB of memory.
  - One file could not be found: `x86/x86-insns.ml`. `make` generates it, so a fresh checkout does not have it.
- Definitions found.
  - Every definition at the start of a line is read.
  - Every `prove`, `time prove`, `new_definition` and `define` is read as a theorem or definition, with its statement.
  - The definitions the check reports as missing are all inside comments or `let _ = ...`.
- Definition sources (`definition_source`).
  - All 30,809 definitions read (s2n-bignum and the HOL Light files it loads) have their source text.
  - Finding the names used by every one of them took 22 s in total, at most 39 ms for one.
  - 429 definitions are longer than 20,000 characters. `max_chars` cuts them.
    - Machine code byte lists (`*_mc`), up to 710,363 characters.
    - Long proofs.
    - HOL Light's `Divstep/hull_light.ml`, whose definitions are 2000-line `let ... in` chains.
