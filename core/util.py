"""Small collection helpers and file checks."""

import logging
import os
import re
import stat
from collections.abc import Callable, Iterable

from core.text import Position, Range, TextDoc

logger = logging.getLogger(__name__)


def difference[T](xs: Iterable[T], ys: Iterable[T]) -> list[T]:
    s = ys if isinstance(ys, set) else set(ys)
    return [x for x in xs if x not in s]


def filter_map[T, U](xs: Iterable[T], f: Callable[[T], U | None]) -> list[U]:
    res: list[U] = []
    for x in xs:
        r = f(x)
        if r is not None:
            res.append(r)
    return res


def file_exists(path: str, check_dir: bool) -> bool:
    try:
        mode = os.stat(path).st_mode
        return stat.S_ISDIR(mode) if check_dir else stat.S_ISREG(mode)
    except OSError:
        return False


def read_dir(path: str) -> list[os.DirEntry[str]]:
    with os.scandir(path) as entries:
        return list(entries)


def read_text(path: str) -> str:
    """The file's text with its line endings. Bytes that are not UTF-8 are
    replaced, with a warning."""
    with open(path, "rb") as handle:
        data = handle.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as err:
        logger.warning("%s is not valid UTF-8 (%s at byte %d): invalid bytes replaced",
                       path, err.reason, err.start)
        return data.decode("utf-8", errors="replace")


# Operator characters are not in the word pattern (the `/` completes
# imported file names and must not join the word).
_OPERATOR_FALLBACK_RE = re.compile(r"[-+$&*/=>@^\\|~!?%<:.]")


def get_word_at_position(doc: TextDoc, position: Position) -> tuple[str, Range] | tuple[None, None]:
    """The word at the position and its range, else (None, None)."""
    word_range = doc.get_word_range_at_position(position)
    if word_range is not None:
        return doc.get_text(word_range), word_range
    if position.line < 0 or position.line >= doc.line_count:
        return None, None
    line = doc.line_at(position.line)
    i = j = position.character
    while j < len(line) and _OPERATOR_FALLBACK_RE.match(line[j]):
        j += 1
    while i > 0 and _OPERATOR_FALLBACK_RE.match(line[i - 1]):
        i -= 1
    if i < j:
        return line[i:j], Range(position.with_(character=i), position.with_(character=j))
    return None, None
