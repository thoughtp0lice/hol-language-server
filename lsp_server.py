#!/usr/bin/env python3
"""Language server for HOL Light (hol-language-server).

Static lookup over `.ml` and `.hl` files: hover statements, go to
definition, and document and workspace symbols. It parses files and the
files they load, plus the core HOL Light sources. It evaluates nothing.
"""

import logging
import sys

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from hol_language_server_core.config import Settings, expand_root_paths, parse_settings, settings_from_options
from hol_language_server_core.service import HolLanguageService, SymbolInfo
from hol_language_server_core.text import Position as CorePosition, Range as CoreRange, TextDoc

logger = logging.getLogger(__name__)

MAX_WORKSPACE_SYMBOLS = 1000

_SYMBOL_KINDS = {
    "theorem": lsp.SymbolKind.Constant,
    "definition": lsp.SymbolKind.Function,
    "term": lsp.SymbolKind.Constant,
    "value": lsp.SymbolKind.Variable,
    "module": lsp.SymbolKind.Module,
}


def _fs_path(uri: str) -> str:
    path = to_fs_path(uri)
    if path is None:
        raise ValueError(f"Not a file URI: {uri}")
    return path


def _uri(path: str) -> str:
    uri = from_fs_path(path)
    if uri is None:
        raise ValueError(f"No file URI for {path}")
    return uri


def _warn(ls: LanguageServer, message: str) -> None:
    ls.window_show_message(lsp.ShowMessageParams(type=lsp.MessageType.Warning, message=message))


def _to_lsp_position(pos: CorePosition) -> lsp.Position:
    return lsp.Position(line=pos.line, character=pos.character)


def _to_lsp_range(span: CoreRange) -> lsp.Range:
    return lsp.Range(start=_to_lsp_position(span.start), end=_to_lsp_position(span.end))


def _to_symbol_info(symbol: SymbolInfo) -> lsp.SymbolInformation:
    end = symbol.end_position
    if end is None:
        end = symbol.position.translate(0, len(symbol.name))
    return lsp.SymbolInformation(
        name=symbol.name,
        kind=_SYMBOL_KINDS[symbol.kind],
        location=lsp.Location(
            uri=_uri(symbol.path),
            range=_to_lsp_range(CoreRange(symbol.position, end)),
        ),
        container_name=symbol.container,
    )


def create_server(service: HolLanguageService, settings: Settings,
                  workspace_fixed: bool) -> LanguageServer:
    server = LanguageServer(
        "hol-language-server",
        "0.1.0",
        text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
    )

    # The unresolved loads last shown for each file, so a message repeats only on a change.
    shown_unresolved: dict[str, list[str]] = {}

    def index(ls: LanguageServer, file_path: str, full: bool) -> None:
        # Indexes the file and its dependencies, and warns about loads that could not be found.
        names = sorted({dep.name for dep in service.index(file_path, full)})
        if names and shown_unresolved.get(file_path) != names:
            _warn(ls, f"{file_path}: loads not found: {', '.join(names)}")
        shown_unresolved[file_path] = names

    def prepare(ls: LanguageServer, uri: str) -> TextDoc:
        # Unchanged files are not parsed again.
        file_path = _fs_path(uri)
        index(ls, file_path, True)
        return service.get_document(file_path)

    @server.feature(lsp.INITIALIZE)
    def on_initialize(ls: LanguageServer, params: lsp.InitializeParams) -> None:
        if not workspace_fixed:
            folders = params.workspace_folders or []
            if folders:
                settings.workspace = _fs_path(folders[0].uri)
            elif params.root_uri:
                settings.workspace = _fs_path(params.root_uri)
            elif params.root_path:
                settings.workspace = params.root_path
        # No options is fine; options that are not a valid settings object fail initialize.
        options = params.initialization_options or {}
        if isinstance(options, dict) and "hol-light" in options:
            options = options["hol-light"]
        updated = settings_from_options(options, settings)
        settings.hol_path = updated.hol_path
        settings.root_paths = updated.root_paths
        settings.auto_index = updated.auto_index
        settings.index_workspace = updated.index_workspace
        settings.custom_commands = updated.custom_commands
        # Here rather than in initialized, so a bad directory or root path fails initialize.
        service.database.index_base_hol_light_files(settings.hol_path, settings.custom_commands)
        expand_root_paths(settings)

    @server.feature(lsp.INITIALIZED)
    def on_initialized(ls: LanguageServer, params: lsp.InitializedParams) -> None:
        if settings.index_workspace:
            unresolved = service.index_workspace()
            if unresolved:
                names = sorted({dep.name for dep in unresolved})
                _warn(ls, f"Loads not found in the workspace: {', '.join(names)}")

    @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    def on_open(ls: LanguageServer, params: lsp.DidOpenTextDocumentParams) -> None:
        item = params.text_document
        service.open_document(_fs_path(item.uri), item.text)
        if settings.auto_index:
            index(ls, _fs_path(item.uri), False)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
    def on_change(ls: LanguageServer, params: lsp.DidChangeTextDocumentParams) -> None:
        uri = params.text_document.uri
        service.open_document(_fs_path(uri), params.content_changes[-1].text)
        if settings.auto_index:
            index(ls, _fs_path(uri), False)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
    def on_close(ls: LanguageServer, params: lsp.DidCloseTextDocumentParams) -> None:
        service.close_document(_fs_path(params.text_document.uri))

    @server.feature(lsp.TEXT_DOCUMENT_HOVER)
    def on_hover(ls: LanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
        doc = prepare(ls, params.text_document.uri)
        pos = CorePosition(line=params.position.line, character=params.position.character)
        found = service.hover(doc, pos)
        if found is None:
            return None
        markdown, word_range = found
        return lsp.Hover(
            contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=markdown),
            range=_to_lsp_range(word_range) if word_range is not None else None,
        )

    @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
    def on_definition(ls: LanguageServer, params: lsp.DefinitionParams) -> list[lsp.Location]:
        doc = prepare(ls, params.text_document.uri)
        pos = CorePosition(line=params.position.line, character=params.position.character)
        return [
            lsp.Location(
                uri=_uri(target.path), range=_to_lsp_range(target.range)
            )
            for target in service.definition(doc, pos)
        ]

    @server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def on_document_symbol(ls: LanguageServer,
                           params: lsp.DocumentSymbolParams) -> list[lsp.SymbolInformation]:
        file_path = _fs_path(params.text_document.uri)
        index(ls, file_path, False)
        return [_to_symbol_info(s) for s in service.document_symbols(file_path)]

    @server.feature(lsp.WORKSPACE_SYMBOL)
    def on_workspace_symbol(ls: LanguageServer,
                            params: lsp.WorkspaceSymbolParams) -> list[lsp.SymbolInformation]:
        query = params.query.lower()
        symbols = service.search_symbols(lambda name: query in name.lower())
        return [_to_symbol_info(s) for s in symbols[:MAX_WORKSPACE_SYMBOLS]]

    return server


def main(argv: list[str] | None = None) -> None:
    settings, workspace_fixed = parse_settings(argv, __doc__)
    service = HolLanguageService(settings)
    create_server(service, settings, workspace_fixed).start_io()


def cli() -> None:
    # The console script and `python lsp_server.py`: the entry point, so it configures logging.
    logging.basicConfig(stream=sys.stderr)
    main()


if __name__ == "__main__":
    cli()
