"""Tests of the parser, database, util, and the service lookup methods."""

import logging
import os
from pathlib import Path

import pytest
from hol_server_paths import EXAMPLES, HOL, PROJECT
from hol_language_server_core.config import default_settings
from hol_language_server_core.database import Database
from hol_language_server_core.parser import (
    DefinitionType,
    OpenDecl,
    Parser,
    TokenType,
    parse_text,
)
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import TextDoc
from hol_language_server_core.util import difference, filter_map, read_text


def read_doc(*parts: str) -> TextDoc:
    path = os.path.join(EXAMPLES, *parts)
    with open(path, encoding="utf-8") as handle:
        return TextDoc(path, handle.read())


def test_parser_definitions_hl():
    doc = read_doc("definitions.hl")
    result = parse_text(doc.text, doc.path)
    assert len(result.definitions) == 36
    assert len(result.dependencies) == 1
    assert len(result.modules) == 0
    assert result.global_module.open_decls == []
    assert (
        len([d for d in result.definitions if d.def_type == DefinitionType.theorem])
        == 1
    )


def test_parser_modules_hl():
    doc = read_doc("modules.hl")
    result = parse_text(doc.text, doc.path)
    # vscode-hol-light finds 5: newMap1 and exists1 follow a `type`
    # item which is not ended by `;;`.
    assert len(result.definitions) == 7
    assert len(result.dependencies) == 0
    assert len(result.modules) == 6
    assert result.global_module.open_decls == [OpenDecl("Utils", 523, 533)]
    mods = result.modules
    assert [m.full_name for m in mods] == [
        "Utils", "Utils.Pair", "Utils.List", "Utils.Substlist", "Mmap", "Mmap.Make",
    ]
    assert mods[0].modules == [mods[1], mods[2], mods[3]]
    assert all(mods[i + 1].start > mods[i].start for i in range(len(mods) - 1))


def parse_names(text: str) -> list[str]:
    return [
        f"{d.name}:{DefinitionType(d.def_type).name}:{d.content}"
        for d in parse_text(text, "x.ml").definitions
    ]


def test_character_literals_do_not_start_strings():
    text = (
        "let sep = if b then ';' else ':';;\n"
        "let q = Some '\"' and r = Some '\\'';;\n"
        "let s' = \"a\\\"b\" ^ s';;\n"
        "let f (x:'a) = x;;\n"
        "let needs s = s;;"
    )
    assert parse_names(text) == [
        "sep:other:", "q:other:", "r:other:", "s':other:", "f:other:", "needs:other:",
    ]


def test_time_prove_and_bindings_optional_parameters():
    assert parse_names("let TH = time prove\n (`x = x`, REFL_TAC);;") == ["TH:theorem:x = x"]
    assert parse_names(
        "let X1 = define `X1 = 1`\nand X2 = define `X2 = 2`\n"
        "and x3 = let a = 1 and b = 2 in a;;"
    ) == ["X1:definition:X1 = 1", "X2:definition:X2 = 2", "x3:other:"]
    assert parse_names(
        "let SIM_TAC ?(pre:tactic option) ?(canon=true) "
        "?(bridge:thm option = None) th = ALL_TAC;;"
    ) == ["SIM_TAC:other:"]


def test_operator_bindings_are_indexed():
    assert parse_names("let (=/) x y = x;;") == ["=/:other:"]
    assert parse_names("let ( >>= ) m f = m;;") == [">>=:other:"]


def test_numeric_literals_are_not_identifiers():
    tokens = []
    parser = Parser("[0x48; 0x8b; 1_000; 2.5e3]")
    token = parser.next_token()
    while token.type != TokenType.eof:
        if token.type == TokenType.identifier:
            tokens.append(token.value)
        token = parser.next_token()
    assert tokens == []


def test_database_definitions_hl_and_dependencies():
    doc = read_doc("definitions.hl")
    database = Database()
    database.index_document_with_dependencies(doc, HOL, ["."], True)
    dep_path = os.path.join(EXAMPLES, "modules.hl")
    examples = {doc.path, dep_path}
    # 38 in vscode-hol-light (see modules.hl above).
    assert len({d.name for ds in database._definition_index.values() for d in ds
                if d.get_file_path() in examples}) == 40
    assert len({m.name for ms in database._module_index.values() for m in ms
                if m.get_file_path() in examples}) == 6
    assert {p for p in database.all_dependencies(doc.path)
            if not database.is_base_hol_light_file(p)} == examples
    _, mods = database.find_definitions_and_modules("Utils", doc.path, 0)
    [utils_mod] = mods
    all_deps = database.all_dependencies(doc.path)
    assert len(database.find_definitions("x", all_deps, True, set())) == 2
    assert database.find_definitions("const", all_deps, True, set()) == []
    assert (
        len(database.find_definitions("const", all_deps, True, {utils_mod})) == 1
    )
    assert database.find_definitions_and_modules("Pair", dep_path, 509) == ([], set())
    assert database.find_definitions_and_modules("Pair", dep_path, 536) == (
        [],
        {utils_mod.modules[0]},
    )


def test_filter_map_and_difference():
    assert filter_map([1, 2, 3, 4, 5], lambda x: x * 2 if x % 2 == 0 else None) == [4, 8]
    assert filter_map([1, 2, 3, 4, 5], lambda x: None if x == 3 else x * 2) == [2, 4, 8, 10]
    assert difference({1, 2, 3, 4}, [3, 4, 5]) == [1, 2]
    assert difference([1, 2, 3], {1, 2, 3}) == []


def example_service() -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = PROJECT
    return HolLanguageService(settings)


def test_indexing_resolves_dependencies_and_reports_unresolved():
    service = example_service()
    main_path = os.path.join(PROJECT, "main.ml")
    unresolved = service.index(main_path, True)
    assert [dep.name for dep in unresolved] == ["missing.ml"]
    assert service.database.is_base_hol_light_file(os.path.join(HOL, "hol.ml"))


def test_symbols():
    service = example_service()
    service.index(os.path.join(PROJECT, "main.ml"), True)
    assert [s.path for s in service.find_symbols("ADD_SYM")] == [
        os.path.join(HOL, "hol.ml")
    ]
    # kernel.ml is indexed as a base file and ctx.ml uses it through `include Kernel`.
    assert [os.path.basename(s.path) for s in service.find_symbols("kfun2")] == ["kernel.ml"]


def test_find_symbols_ranks_exact_full_name_first(tmp_path: Path):
    first = tmp_path / "first.ml"
    first.write_text(
        "module A = struct\nmodule Mod = struct\nlet foo = 1;;\nend\nend\n",
        encoding="utf-8",
    )
    second = tmp_path / "second.ml"
    second.write_text("module Mod = struct\nlet foo = 2;;\nend\n", encoding="utf-8")
    service = example_service()
    service.index(str(first), True)
    service.index(str(second), True)
    assert [s.full_name for s in service.find_symbols("Mod.foo")] == [
        "Mod.foo",
        "A.Mod.foo",
    ]


def test_indexing_a_workspace():
    service = example_service()
    assert [dep.name for dep in service.index_workspace()] == ["missing.ml"]
    assert [os.path.basename(s.path) for s in service.find_symbols("USES_CONTEXT")] == ["ctx.ml"]


def test_base_indexing_refuses_a_missing_or_wrong_hol_light_directory(tmp_path: Path):
    with pytest.raises(ValueError, match="No HOL Light directory"):
        Database().index_base_hol_light_files("")
    with pytest.raises(ValueError, match="no hol.ml"):
        Database().index_base_hol_light_files(str(tmp_path))


def test_parser_warns_about_what_it_skips(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="hol_language_server_core.parser"):
        parse_text("open 5;;\n", "x.ml")
    assert [r.getMessage() for r in caplog.records] == ["Error: identifier expected x.ml:1:6"]


def test_non_utf8_text_is_replaced_with_a_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    path = tmp_path / "latin1.ml"
    path.write_bytes(b"let x = 1;; (* caf\xe9 *)\r\n")
    with caplog.at_level(logging.WARNING, logger="hol_language_server_core.util"):
        assert read_text(str(path)) == "let x = 1;; (* caf\ufffd *)\r\n"
    assert "is not valid UTF-8" in caplog.text
