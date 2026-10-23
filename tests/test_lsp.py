"""Tests of the core methods the LSP server uses: positions, hover,
go to definition, and document and workspace symbols."""

import os
from pathlib import Path

import pytest
from hol_server_paths import HOL, PROJECT
from hol_language_server_core.config import default_settings, expand_root_paths, parse_settings, settings_from_options
from hol_language_server_core.parser import CustomCommands
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import Position, TextDoc
from hol_language_server_core.util import get_word_at_position


def example_service() -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = PROJECT
    return HolLanguageService(settings)


def tactics_doc(service: HolLanguageService) -> TextDoc:
    path = os.path.join(PROJECT, "tactics.ml")
    service.index(path, True)
    return service.get_document(path)


def test_positions_round_trip_through_offsets():
    doc = TextDoc("x.ml", "let A = 1;;\nlet BB =\n  2;;\n")
    assert doc.offset_at(Position(1, 4)) == len("let A = 1;;\nlet ")
    assert doc.position_at(doc.offset_at(Position(2, 2))) == Position(2, 2)
    assert doc.offset_at(Position(-1, 0)) == 0
    assert doc.offset_at(Position(99, 0)) == len(doc.text)


def test_word_at_position_falls_back_to_operators():
    doc = TextDoc("x.ml", "let x = f 1;;\n")
    assert get_word_at_position(doc, Position(0, 4))[0] == "x"
    word, span = get_word_at_position(doc, Position(0, 6))
    assert span is not None
    assert (word, (span.start.character, span.end.character)) == ("=", (6, 7))
    assert get_word_at_position(doc, Position(1, 0))[0] is None


def test_hover_shows_the_theorem_statement():
    service = example_service()
    doc = tactics_doc(service)
    # ADD_SYM_ALT in `REWRITE_TAC[th; ADD_SYM_ALT]` on line 6.
    found = service.hover(doc, Position(6, 20))
    assert found is not None
    markdown, _ = found
    assert markdown == "Theorem `ADD_SYM_ALT`\n```\n`|- !m n. n + m = m + n`\n```"


def test_hover_shows_a_value_and_a_module():
    service = example_service()
    doc = tactics_doc(service)
    found = service.hover(doc, Position(5, 5))
    assert found is not None
    markdown, _ = found
    assert markdown == "*HELPER_TAC*"
    assert service.hover(doc, Position(0, 1)) is None


def test_definition_jumps_to_the_name():
    service = example_service()
    doc = tactics_doc(service)
    [target] = service.definition(doc, Position(5, 5))
    assert target.path == doc.path
    assert (target.range.start.line, target.range.start.character) == (5, 4)
    assert service.definition(doc, Position(0, 1)) == []
    assert service.definition(doc, Position(doc.line_count, 0)) == []
    assert service.definition(doc, Position(-1, 0)) == []


def test_definition_jumps_through_needs():
    service = example_service()
    path = os.path.join(PROJECT, "main.ml")
    service.index(path, True)
    doc = service.get_document(path)
    [target] = service.definition(doc, Position(0, 8))
    assert target.path == os.path.join(PROJECT, "lib", "util.ml")


def test_document_symbols_are_position_ordered():
    service = example_service()
    path = os.path.join(PROJECT, "main.ml")
    service.index(path, True)
    symbols = service.document_symbols(path)
    assert [s.name for s in symbols] == ["MY_THM", "x"]
    lines = [(s.position.line, s.position.character) for s in symbols]
    assert lines == sorted(lines)
    assert service.document_symbols(os.path.join(PROJECT, "nope.ml")) == []


def test_search_symbols_matches_by_predicate():
    service = example_service()
    service.index_workspace()
    names = {s.full_name for s in service.search_symbols(lambda n: "TAC" in n)}
    assert {"HELPER_TAC", "MY_TAC", "OTHER_TAC"} <= names


def test_settings_from_options_reads_the_section():
    base = default_settings()
    settings = settings_from_options(
        {"path": "/hol", "rootPaths": ["."], "autoIndex": False, "indexWorkspace": True},
        base,
    )
    assert (settings.hol_path, settings.root_paths) == ("/hol", ["."])
    assert (settings.auto_index, settings.index_workspace) == (False, True)
    assert settings.workspace == base.workspace
    assert settings_from_options({}, base) == base


def test_settings_from_options_rejects_bad_settings():
    base = default_settings()
    for options, message in [
        (None, "must be an object"),
        ("/hol", "must be an object"),
        ({"holPath": "/hol"}, "Unknown hol-light settings: holPath"),
        ({"path": 5}, "path must be a str"),
        ({"autoIndex": "false"}, "autoIndex must be a bool"),
        ({"rootPaths": "."}, "rootPaths must be a list"),
        ({"rootPaths": [1]}, "rootPaths must hold strings"),
        ({"customImports": "my_needs"}, "customImports must be a list"),
        ({"customTheorems": ["my prove"]}, "is not an OCaml identifier"),
        ({"customDefinitions": [3]}, "is not an OCaml identifier"),
    ]:
        with pytest.raises(ValueError, match=message):
            settings_from_options(options, base)


def test_root_paths_reject_unknown_and_unset_placeholders():
    settings = default_settings()
    settings.workspace = PROJECT
    for root_paths, message in [
        (["{wrkspace}/lib"], "unknown placeholder"),
        (["{hol}"], "is not set"),
        ([""], "Empty root path"),
    ]:
        settings.root_paths = root_paths
        with pytest.raises(ValueError, match=message):
            expand_root_paths(settings)


def test_custom_commands_come_from_options_and_flags():
    base = default_settings()
    settings = settings_from_options(
        {"customImports": ["my_needs"], "customTheorems": ["my_prove"], "customDefinitions": []}, base
    )
    assert settings.custom_commands == CustomCommands(imports=["my_needs"], theorems=["my_prove"])
    settings, _ = parse_settings(["--custom-import", "my_needs", "--custom-import", "load_proof",
                                  "--custom-definition", "my_define"], None)
    assert settings.custom_commands == CustomCommands(imports=["my_needs", "load_proof"],
                                                      definitions=["my_define"])
    with pytest.raises(ValueError, match="--custom-theorem: 'a.b' is not an OCaml identifier"):
        parse_settings(["--custom-theorem", "a.b"], None)


def test_definition_jumps_through_a_custom_import(tmp_path: Path):
    (tmp_path / "lib.ml").write_text("let helper = 1;;\n")
    (tmp_path / "main.ml").write_text('my_needs "lib.ml";;\nlet x = helper;;\n')
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    settings.custom_commands = CustomCommands(imports=["my_needs"])
    service = HolLanguageService(settings)
    path = str(tmp_path / "main.ml")
    assert service.index(path, True) == []
    doc = service.get_document(path)
    [target] = service.definition(doc, Position(0, 11))
    assert target.path == str(tmp_path / "lib.ml")
    [target] = service.definition(doc, Position(1, 9))
    assert target.path == str(tmp_path / "lib.ml")


def test_missing_loads_cover_the_files_it_loads(tmp_path: Path):
    (tmp_path / "a.ml").write_text('needs "gone.ml";;\n')
    (tmp_path / "main.ml").write_text('needs "a.ml";;\nneeds "nope.ml";;\n')
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    service = HolLanguageService(settings)
    path = str(tmp_path / "main.ml")
    service.index(path, True)
    missing = {p: [(m.name, m.range.start.line, m.range.start.character) for m in loads]
               for p, loads in service.missing_loads(path).items() if loads}
    assert missing == {path: [("nope.ml", 1, 6)], str(tmp_path / "a.ml"): [("gone.ml", 0, 6)]}
