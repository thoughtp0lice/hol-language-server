"""OCaml-subset parser for HOL Light sources.

Finds `needs`/`loads`/`loadt` dependencies, `prove`-style theorems,
`new_definition`-style constant definitions, other `let` bindings, and
`module`/`open`/`include` structure. Everything else is skipped.
"""

from __future__ import annotations

import logging
import re
from bisect import bisect_right
from dataclasses import dataclass
from enum import IntEnum

from core.text import CHAR_LITERAL, Location, Position, location

logger = logging.getLogger(__name__)


class Dependency:
    def __init__(self, name: str, hol_light_relative: bool) -> None:
        self.name = name
        # Resolve relative to the HOL Light base directory, not the
        # workspace roots, when the loader is `loads`.
        self.hol_light_relative = hol_light_relative


class DefinitionType(IntEnum):
    theorem = 0
    definition = 1
    term = 2
    other = 3


DEFINITION_TYPE_NAMES = {
    DefinitionType.theorem: "theorem",
    DefinitionType.definition: "definition",
    DefinitionType.term: "term",
    DefinitionType.other: "value",
}


def _find_line_number(line_starts: list[int], pos: int) -> int:
    return bisect_right(line_starts, pos) - 1


class Definition:
    def __init__(self, name: str, def_type: DefinitionType, content: str, module: Module | None,
                 offset: int, file_path: str, position: Position) -> None:
        self.name = name
        self.def_type = def_type
        self.content = content
        self.module = module
        # Offset of the name token in the file text.
        self.offset = offset
        self.position = position
        # The whole item which defines this name (`let ... ;;`), shared by
        # the bindings of `let ... and ...`.
        self.source_start: int | None = None
        self.source_end: int | None = None
        self._file_path = file_path

    def get_file_path(self) -> str:
        return self._file_path

    def get_location(self) -> Location:
        return location(self._file_path, self.position)

    @property
    def full_name(self) -> str:
        if self.module is not None:
            return self.module.full_name + "." + self.name
        return self.name

    def to_string(self) -> str:
        if self.def_type == DefinitionType.theorem:
            return f"Theorem `{self.name}`\n```\n`|- {self.content}`\n```"
        if self.def_type == DefinitionType.definition:
            return f"Definition `{self.name}`\n```\n`|- {self.content}`\n```"
        if self.def_type == DefinitionType.term:
            return "```\n`" + self.content + "`\n```"
        text = f"*{self.name}*"
        if self.content:
            # content represents type
            text += f" : {self.content}"
        return text


@dataclass
class OpenDecl:
    name: str
    # Offsets of the `open`/`include` statement and of the end of the name.
    start: int
    end: int


class Module:
    def __init__(self, name: str, parent: Module | None, start: int, file_path: str,
                 position: Position) -> None:
        self.parent = parent
        self.name = name
        self.full_name = (
            parent.full_name + "." + name if parent is not None else name
        )
        # Offset of the module name token in the file text.
        self.start = start
        self.end: int | None = None
        self.position = position
        self.end_position: Position | None = None
        self._file_path = file_path
        self.modules: list[Module] = []
        self.open_decls: list[OpenDecl] = []
        self.include_decls: list[OpenDecl] = []

    def get_file_path(self) -> str:
        return self._file_path

    def get_location(self) -> Location:
        return location(self._file_path, self.position)

    def to_string(self) -> str:
        return f"Module `{self.full_name}`"


@dataclass
class ParseResult:
    definitions: list[Definition]
    # Modules sorted by their start position.
    modules: list[Module]
    dependencies: list[Dependency]
    # Tracks all open and include statements. Holds no definitions or modules.
    global_module: Module


def parse_text(text: str, file_path: str) -> ParseResult:
    return Parser(text).parse(file_path)


class TokenType(IntEnum):
    eof = 0
    comment = 1
    string = 2
    term = 3
    statement_separator = 4
    operator = 5
    identifier = 6
    other = 7


_TOKEN_RE = re.compile(
    CHAR_LITERAL
    + r"|\(\*"
    + r"|[" + '"' + r"`'()\],{}]"
    + r"|\[\|?|\|\]"
    + r"|[-+*/#><=!?~%&$^@:.|]+"
    + r"|;+"
    + r"|[_a-zA-Z][\w'.]*"
    + r"|\d[\w'.]*"
)

_OPERATOR_CHARS = set("-+*/#><=!?~%&$^@:.|")


def _skip_re(search_module_end: bool) -> re.Pattern[str]:
    words = "module|begin|end|let" if search_module_end else "module|let"
    return re.compile(
        CHAR_LITERAL + r"|\(\*|" + r'["`]|;;+|\b(?:' + words + r")\b"
    )


_SKIP_RE = {True: _skip_re(True), False: _skip_re(False)}

OCAML_KEYWORDS = set(
    "and as assert asr begin class constraint do done downto else end "
    "exception external false for fun function functor if in include inherit "
    "initializer land lazy let lor lsl lsr lxor match method mod module mutable "
    "new nonrec object of open or private rec sig struct then to true try type "
    "val virtual when while with".split()
)


class Token:
    def __init__(self, token_type: TokenType, start: int, end: int, value: str | None = None) -> None:
        self.type = token_type
        self.value = value
        self.start_pos = start
        self.end_pos = end
        self._start_position: Position | None = None
        self._end_position: Position | None = None

    def get_value(self, text: str) -> str:
        return self.value if self.value is not None else text[self.start_pos:self.end_pos]

    def get_start_position(self, line_starts: list[int]) -> Position:
        if self._start_position is None:
            line = _find_line_number(line_starts, self.start_pos)
            self._start_position = Position(line, self.start_pos - line_starts[line])
        return self._start_position

    def get_end_position(self, line_starts: list[int]) -> Position:
        if self._end_position is None:
            line = _find_line_number(line_starts, self.end_pos - 1)
            self._end_position = Position(line, self.end_pos - line_starts[line])
        return self._end_position


class ParserError(Exception):
    def __init__(self, message: str, token: Token | None = None) -> None:
        super().__init__(message)
        self.token = token


@dataclass
class Binding:
    name_token: Token
    type: str = ""


@dataclass
class _ParserState:
    pos: int
    cur_token: Token | None = None


class Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.eof_token = Token(TokenType.eof, len(text), len(text), "")
        self._line_starts: list[int] = []
        i = 0
        while True:
            self._line_starts.append(i)
            i = text.find("\n", i) + 1
            if i <= 0:
                break

        def mk(words: list[str]) -> re.Pattern[str]:
            return re.compile("^(?:" + "|".join(words) + ")$")

        self._import_re = mk(["needs", "loads", "loadt"])
        self._theorem_re = mk(["prove", "VECTOR_ARITH", "ARITH_RULE", "REAL_ARITH"])
        self._definition_re = mk(["new_definition", "new_basic_definition", "define"])
        self._def_other_re = mk(["new_recursive_definition"])

        self.pos = 0
        self._cur: Token | None = None

    def reset_state(self, state: _ParserState) -> None:
        self.pos = state.pos
        self._cur = state.cur_token

    def save_state(self) -> _ParserState:
        return _ParserState(self.pos, self._cur)

    def peek(self) -> Token:
        if self._cur is None:
            self._cur = self.next_token()
        return self._cur

    def next_token(self) -> Token:
        if self._cur is not None:
            res = self._cur
            self._cur = None
            return res
        m = _TOKEN_RE.search(self.text, self.pos)
        if m is None:
            self.pos = len(self.text)
            return self.eof_token
        tok = m.group(0)
        if tok == "(*":
            return self._parse_comment(m.start())
        if tok == '"':
            return self._parse_string(m.start())
        if tok == "`":
            return self._parse_term(m.start())
        self.pos = m.end()
        if tok.startswith(";;"):
            kind = TokenType.statement_separator
        elif tok[0] == "_" or "a" <= tok[0] <= "z" or "A" <= tok[0] <= "Z":
            kind = TokenType.identifier
        elif tok != "|]" and tok[0] in _OPERATOR_CHARS:
            kind = TokenType.operator
        else:
            kind = TokenType.other
        return Token(kind, m.start(), self.pos, tok)

    def _parse_comment(self, pos: int) -> Token:
        pattern = re.compile(r"\(\*|\*\)")
        p = pos + 2
        level = 1
        while True:
            m = pattern.search(self.text, p)
            if m is None:
                break
            if m.group(0) == "(*":
                level += 1
            elif level - 1 <= 0:
                level = 0
                self.pos = m.end()
                return Token(TokenType.comment, pos, self.pos)
            else:
                level -= 1
            p = m.end()
        self.pos = len(self.text)
        return Token(TokenType.comment, pos, self.pos)

    def _parse_string(self, pos: int) -> Token:
        pattern = re.compile(r'"|\\.')
        p = pos + 1
        while True:
            m = pattern.search(self.text, p)
            if m is None:
                break
            if m.group(0) == '"':
                self.pos = m.end()
                return Token(TokenType.string, pos, self.pos)
            p = m.end()
        self.pos = len(self.text)
        return Token(TokenType.string, pos, self.pos)

    def _parse_term(self, pos: int) -> Token:
        end = self.text.find("`", pos + 1)
        self.pos = len(self.text) if end < 0 else end + 1
        return Token(TokenType.term, pos, self.pos)

    def skip_to_next_statement(self, search_module_end: bool, item_indent: int) -> None:
        # The next call skips the current token. Do not check for `module`
        # and `end` here: a current `module` or `end` is handled by parse().
        # Skip comments first: the current token starts the statement.
        if self.next_skip_comments().type == TokenType.statement_separator:
            return
        # Not strictly necessary since next_token resets _cur.
        self._cur = None

        # With search_module_end, `end` tokens closing a module expression
        # are honored. Some modules hold no `;;`, and `end` is not always
        # followed by `;;`. Only `begin`/`end` pairs count: other `end`
        # closers (`sig`, `struct`, `object`) may hold `;;` and are skipped.
        # A `let` starting a line, indented no deeper than the current item,
        # and not opening a `let ... in` expression starts the next item.
        # Items are often not separated by `;;` inside modules (the kernel
        # in HOL Light's fusion.ml) and sometimes at the top level.
        pattern = _SKIP_RE[search_module_end]
        pos = self.pos
        begin_level = 0
        while True:
            m = pattern.search(self.text, pos)
            if m is None:
                break
            tok = m.group(0)
            pos = m.end()
            if tok.startswith("'"):
                # A character literal.
                continue
            if tok == "(*":
                self._parse_comment(m.start())
                pos = self.pos
            elif tok == '"':
                self._parse_string(m.start())
                pos = self.pos
            elif tok == "`":
                self._parse_term(m.start())
                pos = self.pos
            elif tok == "begin":
                begin_level += 1
            elif tok == "let":
                # lastIndexOf('\n', m.index - 1): the newline at or before the token.
                line_start = self.text.rfind("\n", 0, m.start()) + 1
                if (
                    not begin_level
                    and m.start() - line_start <= item_indent
                    and not self.text[line_start:m.start()].strip()
                    and not self._is_let_in_expression(m.start())
                ):
                    self.pos = m.start()
                    return
            elif tok == "end":
                if begin_level:
                    begin_level -= 1
                else:
                    self.pos = m.start()
                    return
            elif tok == "module":
                self.pos = m.start()
                return
            else:
                # Past the matched `;;`.
                self.pos = pos
                return
        self.pos = len(self.text)

    def _is_let_in_expression(self, pos: int) -> bool:
        """Whether the `let` at pos closes with an `in` before `;;`."""
        saved = self.save_state()
        self.pos = pos
        self._cur = None
        try:
            self.next_token()
            depth = 1
            while True:
                token = self.next_skip_comments()
                if (
                    token.type == TokenType.eof
                    or token.type == TokenType.statement_separator
                ):
                    return False
                if token.value == "let":
                    depth += 1
                elif token.value == "in" and depth - 1 == 0:
                    return True
                elif token.value == "in":
                    depth -= 1
        finally:
            self.reset_state(saved)

    def skip_comments(self) -> None:
        while self.peek().type == TokenType.comment:
            self.next_token()

    def peek_skip_comments(self) -> Token:
        self.skip_comments()
        return self.peek()

    def next_skip_comments(self) -> Token:
        self.skip_comments()
        return self.next_token()

    def expect(self, value: str | TokenType) -> Token:
        token = self.next_skip_comments()
        if isinstance(value, str):
            ok = token.value == value
        else:
            ok = token.type == value
        if not ok:
            raise ParserError(f"{value if isinstance(value, str) else value.name} expected", token)
        return token

    def match1(self, value: str | TokenType) -> Token | None:
        """Consume the next non-comment token when it matches; else None."""
        token = self.peek_skip_comments()
        if isinstance(value, str):
            ok = token.value == value
        else:
            ok = token.type == value
        if ok:
            return self.next_token()
        return None

    def _parse_type(self, allow_comma: bool = False) -> str:
        def atom() -> str:
            result = ""
            token = self.next_skip_comments()
            if token.value == "(":
                inner = self._parse_type(True)
                self.expect(")")
                result = f"({inner})"
            elif token.type == TokenType.identifier:
                result = token.get_value(self.text)
            elif token.value == "'":
                token = self.expect(TokenType.identifier)
                result = "'" + token.get_value(self.text)
            while True:
                token = self.match1(TokenType.identifier)
                if token is None:
                    break
                result = result + " " + token.get_value(self.text)
            return result

        def compound_type() -> str:
            result: list[str] = []
            while True:
                result.append(atom())
                token = self.peek_skip_comments()
                if token.value in ("->", "*") or (allow_comma and token.value == ","):
                    self.next_token()
                    result.append(", " if token.value == "," else " " + token.value + " ")
                else:
                    break
            return "".join(result)

        return compound_type()

    def _parse_pattern(self, allow_constructor: bool) -> list[Binding]:
        def atom() -> list[Binding]:
            result: list[Binding]
            token = self.next_skip_comments()
            if token.value == "(":
                # ( pattern [: type] )
                token = self.peek_skip_comments()
                if token.value == ")":
                    # unit pattern
                    self.next_token()
                    result = []
                elif token.type == TokenType.operator:
                    # ( operator )
                    self.next_token()
                    result = [Binding(token)]
                    self.expect(")")
                else:
                    result = self._parse_pattern(True)
                    if self.match1(":"):
                        type_text = self._parse_type()
                        if len(result) == 1 and not result[0].type:
                            # A pattern with a single name is just a simple pattern.
                            result[0].type = type_text
                    self.expect(")")
            elif token.value == "[" or token.value == "[|":
                # list or array of patterns
                end_value = "|]" if token.value == "[|" else "]"
                result = self._parse_pattern(True)
                while self.match1(";"):
                    if self.peek_skip_comments().value == end_value:
                        break
                    result.extend(self._parse_pattern(True))
                self.expect(end_value)
            elif token.value == "{":
                # record pattern
                result = record_field()
                while self.match1(";"):
                    token = self.peek_skip_comments()
                    if token.value == "_":
                        self.next_token()
                        self.match1(";")
                        break
                    if token.value == "}":
                        break
                    result.extend(record_field())
                self.expect("}")
            elif token.type == TokenType.identifier:
                # identifier
                result = [] if token.value == "_" else [Binding(token)]
                first = token.get_value(self.text)[:1]
                if allow_constructor and first.isupper() and first.isascii():
                    # constructor?
                    token = self.peek_skip_comments()
                    if token.type == TokenType.identifier:
                        # constructor with one argument
                        self.next_token()
                        result = [] if token.value == "_" else [Binding(token)]
                    elif (token.value or "") in ("(", "[", "{"):
                        # constructor with a pattern
                        result = self._parse_pattern(False)
            else:
                raise ParserError("identifier, (, or [ expected", token)
            return result

        def record_field() -> list[Binding]:
            field = self.next_skip_comments()
            if field.type != TokenType.identifier:
                raise ParserError("field name: identifier expected", field)
            result = [Binding(field)]
            if self.match1(":"):
                result[0].type = self._parse_type()
            if self.match1("="):
                return self._parse_pattern(True)
            return result

        def cons() -> list[Binding]:
            result: list[Binding] = []
            while True:
                result.extend(atom())
                if self.peek_skip_comments().value != "::":
                    break
                self.next_token()
            return result

        def tup() -> list[Binding]:
            result: list[Binding] = []
            while True:
                result.extend(cons())
                if self.match1("as"):
                    self.expect(TokenType.identifier)
                if self.peek_skip_comments().value != ",":
                    break
                self.next_token()
            return result

        return tup()

    def _skip_to_closing_bracket(self) -> None:
        """Skip tokens until an unmatched `)` (not consumed)."""
        depth = 0
        while True:
            token = self.peek_skip_comments()
            if token.type == TokenType.eof or token.type == TokenType.statement_separator:
                return
            if token.value == ")" and depth == 0:
                return
            if token.value in ("(", "[", "[|", "{"):
                depth += 1
            elif token.value in (")", "]", "|]", "}"):
                depth -= 1
            self.next_token()

    def _parse_parameter(self) -> list[Binding]:
        token = self.peek_skip_comments()
        if token.value == "~":
            # Labeled parameters.
            self.next_token()
            if self.match1("("):
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    type_text = self._parse_type()
                self.expect(")")
            else:
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    return self._parse_pattern(False)
            return [Binding(name_token, type_text)]
        if token.value == "?":
            # Optional parameters.
            self.next_token()
            if self.match1("("):
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    type_text = self._parse_type()
                if self.match1("="):
                    # A default value: skip the expression.
                    self._skip_to_closing_bracket()
                self.expect(")")
            else:
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    if self.match1("("):
                        # [:typexpr][= expr] is not supported.
                        result = self._parse_pattern(True)
                        self.expect(")")
                        return result
                    return self._parse_pattern(False)
            return [Binding(name_token, type_text)]
        return self._parse_pattern(False)

    def _parse_let_binding_lhs(self) -> list[Binding]:
        """Left hand side of a let binding (`=` not included, may be missing)."""
        result = self._parse_pattern(False)
        types: list[str] = []
        while True:
            token = self.peek_skip_comments()
            if token.value == ":" or token.value == "=":
                break
            par = self._parse_parameter()
            if len(par) == 1 and par[0].type:
                types.append(par[0].type)
            else:
                types.append("?")
        if token.value == ":":
            self.next_token()
            type_text = self._parse_type()
            if len(result) == 1 and not result[0].type:
                types.append(type_text)
                result[0].type = " -> ".join(
                    f"({t})" if "->" in t else t for t in types
                )
        return result

    def _parse_type_params(self) -> None:
        def type_param() -> None:
            token = self.next_skip_comments()
            if (token.value or "") in ("+", "-", "+!", "-!", "!-", "!+"):
                token = self.next_token()
            if token.value != "'":
                raise ParserError("' expected", token)
            self.expect(TokenType.identifier)

        if self.match1("("):
            while True:
                type_param()
                if not self.match1(","):
                    break
        else:
            type_param()

    def _parse_extended_module_path(self) -> str:
        result = ""
        while True:
            token = self.expect(TokenType.identifier)
            result += token.get_value(self.text)
            token = self.peek_skip_comments()
            if token.value == "(":
                self.next_token()
                inner = self._parse_extended_module_path()
                self.expect(")")
                result += f"({inner})"
            elif token.value == ".":
                result += "."
            else:
                break
        return result

    def _parse_mod_constraint(self) -> None:
        token = self.next_skip_comments()
        if token.value == "type":
            token = self.peek_skip_comments()
            if (token.value or "") in ("+", "-", "+!", "-!", "!-", "!+", "'", "("):
                self._parse_type_params()
            # should be [extended-module-path.]typeconst-name
            self._parse_extended_module_path()
            self.expect("=")
            self._parse_type()
            if self.match1("constraint"):
                self._parse_type()
                self.expect("=")
                self._parse_type()
        elif token.value == "module":
            self.expect(TokenType.identifier)
            self.expect("=")
            self._parse_extended_module_path()
        else:
            raise ParserError("type or module expected", token)

    def _parse_module_type(self) -> None:
        """Parses module types. Currently, does not return anything."""
        token = self.peek_skip_comments()
        if token.value == "(":
            self.next_token()
            self._parse_module_type()
            self.expect(")")
        elif token.value == "sig":
            self.next_token()
            # Skip until `end`.
            while True:
                token = self.next_skip_comments()
                if token.type == TokenType.eof or token.value == "end":
                    break
        elif token.value == "functor":
            raise ParserError("Functors are not supported", token)
        elif token.type == TokenType.identifier:
            self._parse_extended_module_path()
        else:
            raise ParserError("Module type expected", token)
        if self.match1("with"):
            while True:
                self._parse_mod_constraint()
                if not self.match1("and"):
                    break

    def _parse_module_expr(self) -> bool:
        """Parses a module expr. Only the start of `struct` is consumed."""
        token = self.next_skip_comments()
        if token.value == "struct":
            return True
        if token.value == "(":
            inner = self._parse_module_expr()
            if inner:
                # Closing ')' is not consumed (silently ignored after the end).
                return inner
            if self.match1(":"):
                self._parse_module_type()
            self.expect(")")
        elif token.value == "functor":
            self.expect("(")
            self.expect(TokenType.identifier)
            self.expect(":")
            self._parse_module_type()
            self.expect(")")
            self.expect("->")
            return self._parse_module_expr()
        elif token.type != TokenType.identifier:
            raise ParserError("Unsupported module expression", token)
        if self.match1("("):
            inner = self._parse_module_expr()
            if inner:
                return inner
            self.expect(")")
        return False

    def _parse_module_definition(self) -> Token | None:
        """`module` is already consumed. Returns the name token for `struct`."""
        if self.match1("type"):
            self.expect(TokenType.identifier)
            self.expect("=")
            self._parse_module_type()
            return None
        name_token = self.expect(TokenType.identifier)
        token = self.next_skip_comments()
        if token.value == "(":
            self.expect(TokenType.identifier)
            self.expect(":")
            self._parse_module_type()
            self.expect(")")
            token = self.next_skip_comments()
        if token.value == ":":
            self._parse_module_type()
            token = self.next_skip_comments()
        if token.value != "=":
            raise ParserError("= expected after a module declaration", token)
        return name_token if self._parse_module_expr() else None

    def _find_top_level_ands(self) -> list[_ParserState]:
        """States after each `and` starting a new binding of this `let`.

        Finds `and` tokens not nested in brackets, `begin ... end`, or inner
        `let ... in` expressions. The parser state is not changed.
        """
        saved = self.save_state()
        result: list[_ParserState] = []
        depth = 0
        let_depth = 0
        while True:
            token = self.next_skip_comments()
            if token.type == TokenType.eof or token.type == TokenType.statement_separator:
                break
            value = token.value or ""
            if value in ("(", "[", "[|", "{", "begin", "struct", "sig", "object"):
                depth += 1
            elif value in (")", "]", "|]", "}", "end"):
                depth -= 1
                if depth < 0:
                    break
            elif value == "let":
                let_depth += 1
            elif value == "in":
                let_depth = max(0, let_depth - 1)
            elif value == "and":
                if depth == 0 and let_depth == 0:
                    result.append(self.save_state())
        self.reset_state(saved)
        return result

    def parse(self, uri: str) -> ParseResult:
        self.pos = 0
        self._cur = None

        global_module = Module("", None, 0, uri, Position(0, 0))
        definitions: list[Definition] = []
        dependencies: list[Dependency] = []
        modules: list[Module] = []
        module_stack: list[Module] = []

        def add_definition(name: str, def_type: DefinitionType, content: str, offset: int,
                           position: Position) -> None:
            module = module_stack[-1] if module_stack else None
            definitions.append(
                Definition(name, def_type, content, module, offset, uri, position)
            )

        def skip_while_eq(value: str) -> None:
            while self.peek_skip_comments().value == value:
                self.next_token()

        while self.peek().type != TokenType.eof:
            # Save and restore the state at the end of the loop: parsing may
            # consume a statement separator, which must not be skipped.
            # (For example, `let x;;` consumes its own `;;`.)
            state = self.save_state()

            # Safe to consume: the position is restored from `state`.
            statement_token = self.next_skip_comments()
            statement_value = statement_token.value or ""
            first_definition = len(definitions)

            try:
                if statement_value == "let":
                    if self.peek_skip_comments().value == "rec":
                        self.next_token()
                    # `let a = ... and b = ...`: states after each top-level `and`.
                    and_states = self._find_top_level_ands()

                    def parse_binding() -> None:
                        lhs = self._parse_let_binding_lhs()
                        if len(lhs) == 1 and self.next_skip_comments().value == "=":
                            name = lhs[0].name_token.get_value(self.text)
                            pos = lhs[0].name_token.start_pos
                            position = lhs[0].name_token.get_start_position(self._line_starts)
                            skip_while_eq("(")
                            token = self.next_skip_comments()
                            # `time f x` evaluates `f x` (e.g., `let TH = time prove(...)`).
                            if token.value == "time":
                                skip_while_eq("(")
                                token = self.next_skip_comments()
                            if token.type == TokenType.term:
                                add_definition(
                                    name, DefinitionType.term,
                                    token.get_value(self.text)[1:-1], pos, position,
                                )
                                return
                            value = token.value or ""
                            if self._theorem_re.match(value):
                                skip_while_eq("(")
                                # Accept terms, strings, and identifiers.
                                token = self.next_skip_comments()
                                if token.type in (TokenType.term, TokenType.string):
                                    text = token.get_value(self.text)[1:-1]
                                    add_definition(name, DefinitionType.theorem, text, pos, position)
                                    return
                                if token.type == TokenType.identifier:
                                    add_definition(
                                        name, DefinitionType.theorem,
                                        token.get_value(self.text), pos, position,
                                    )
                                    return
                                if token.type != TokenType.statement_separator:
                                    # `;;` here is an alias for a theorem-producing function.
                                    self._report(f"Unparsed theorem: {name}", pos, uri)
                            elif self._definition_re.match(value):
                                skip_while_eq("(")
                                token = self.next_skip_comments()
                                if token.type in (TokenType.term, TokenType.string):
                                    text = token.get_value(self.text)[1:-1]
                                    add_definition(name, DefinitionType.definition, text, pos, position)
                                    return
                                if token.type == TokenType.identifier:
                                    add_definition(
                                        name, DefinitionType.definition,
                                        token.get_value(self.text), pos, position,
                                    )
                                    return
                                if token.type != TokenType.statement_separator:
                                    self._report(f"Unparsed definition: {name}", pos, uri)
                            elif self._def_other_re.match(value):
                                # Skip the next token.
                                self.next_token()
                                skip_while_eq("(")
                                token = self.next_skip_comments()
                                if token.type in (TokenType.term, TokenType.string):
                                    text = token.get_value(self.text)[1:-1]
                                    add_definition(name, DefinitionType.definition, text, pos, position)
                                    return
                                if token.type == TokenType.identifier:
                                    add_definition(
                                        name, DefinitionType.definition,
                                        token.get_value(self.text), pos, position,
                                    )
                                    return
                                self._report(f"Unparsed definition(2): {name}", pos, uri)
                        # Default case.
                        for binding in lhs:
                            name = binding.name_token.get_value(self.text)
                            pos = binding.name_token.start_pos
                            position = binding.name_token.get_start_position(self._line_starts)
                            add_definition(name, DefinitionType.other, binding.type, pos, position)

                    parse_binding()
                    for and_state in and_states:
                        self.reset_state(and_state)
                        try:
                            parse_binding()
                        except ParserError as err:
                            self._report(f"Error: {err}", err.token, uri)
                elif statement_value == "module":
                    module_name_token = self._parse_module_definition()
                    if module_name_token is not None:
                        pos = module_name_token.start_pos
                        name = module_name_token.get_value(self.text)
                        parent = module_stack[-1] if module_stack else None
                        module = Module(
                            name, parent, pos, uri,
                            module_name_token.get_start_position(self._line_starts),
                        )
                        if parent is not None:
                            parent.modules.append(module)
                        module_stack.append(module)
                        modules.append(module)
                    # `module Module = struct` is not followed by `;;`.
                    continue
                elif statement_value == "end":
                    if module_stack:
                        module = module_stack.pop()
                        module.end = statement_token.end_pos
                        module.end_position = statement_token.get_end_position(self._line_starts)
                    else:
                        self._report("Unexpected end", statement_token, uri)
                    # Some `end` tokens are not followed by `;;`.
                    continue
                elif statement_value in ("open", "include"):
                    name_token = self.expect(TokenType.identifier)
                    module = module_stack[-1] if module_stack else global_module
                    decl = OpenDecl(
                        name_token.get_value(self.text),
                        statement_token.start_pos,
                        name_token.end_pos,
                    )
                    if statement_value == "include":
                        module.include_decls.append(decl)
                    else:
                        module.open_decls.append(decl)
                elif self._import_re.match(statement_value):
                    name_token = self.next_token()
                    # Skip very long strings: most definitely invalid
                    # (probably not properly closed yet).
                    if (
                        name_token.type == TokenType.string
                        and name_token.end_pos - name_token.start_pos <= 2000
                    ):
                        text = name_token.get_value(self.text)[1:-1]
                        # Ignore multiline strings.
                        if "\n" not in text:
                            dependencies.append(
                                Dependency(
                                    text,
                                    statement_token.get_value(self.text) == "loads",
                                )
                            )
            except ParserError as err:
                self._report(f"Error: {err}", err.token, uri)

            self.reset_state(state)
            # lastIndexOf('\n', startPos - 1): the newline at or before the token.
            line_start = self.text.rfind("\n", 0, statement_token.start_pos) + 1
            column = statement_token.start_pos - line_start
            self.skip_to_next_statement(len(module_stack) > 0, column)
            if len(definitions) > first_definition:
                end = self.pos
                while end > statement_token.start_pos and self.text[end - 1].isspace():
                    end -= 1
                for found in definitions[first_definition:]:
                    found.source_start = statement_token.start_pos
                    found.source_end = end

        if module_stack:
            for mod in module_stack:
                self._report(f"Unclosed module: {mod.name}", mod.start, uri)

        return ParseResult(definitions, modules, dependencies, global_module)

    def _report(self, message: str, token_or_offset: Token | int | None, uri: str) -> None:
        """Warn about something the parser skipped or misread."""
        if isinstance(token_or_offset, Token):
            offset = token_or_offset.start_pos
        else:
            offset = token_or_offset
        if offset is None:
            line, col = 0, 0
        else:
            upto = self.text[:offset]
            line = len(upto.split("\n"))
            col = offset - (upto.rfind("\n") + 1) + 1
        logger.warning("%s %s:%d:%d", message, uri, line, col)
