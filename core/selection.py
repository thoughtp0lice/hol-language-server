"""Skips OCaml comments, which nest."""


def skip_comments(text: str, pos: int) -> int:
    """End offset of the comment starting at pos. Assumes pos is at `(*`."""
    n = len(text)
    level = 1
    i = pos + 1
    while i < n:
        i = text.find("*", i + 1)
        if i < 0:
            return n
        if text[i - 1] == "(":
            level += 1
        elif i + 1 < n and text[i + 1] == ")":
            level -= 1
            if level <= 0:
                return i + 2
            i += 1
    return n
