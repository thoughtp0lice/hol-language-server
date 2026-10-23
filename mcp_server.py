#!/usr/bin/env python3
"""Static lookup MCP server for HOL Light (hol-light-static).

Reads the statement and source of a named theorem, definition, or tactic,
and the names it is built from. Parses files and the files they load with
needs/loads/loadt, plus the core HOL Light sources. Evaluates nothing.
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Annotated  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402
from pydantic import Field  # noqa: E402

from core.config import Settings, expand_root_paths, parse_settings  # noqa: E402
from core.service import HolLanguageService, Reference, SymbolInfo, resolve_path  # noqa: E402

logger = logging.getLogger(__name__)

MAX_CONTENT = 2000
# Statements of the theorems a definition uses: enough to recognize them.
MAX_REFERENCE_CONTENT = 300
MAX_NOT_EXPANDED = 50


def _clip(text: str) -> str:
    return text[:MAX_CONTENT] + " ..." if len(text) > MAX_CONTENT else text


def _clip_short(text: str) -> str:
    return text[:MAX_REFERENCE_CONTENT] + " ..." if len(text) > MAX_REFERENCE_CONTENT else text


def create_server(service: HolLanguageService, settings: Settings) -> FastMCP:
    server = FastMCP(
        "hol-light-static",
        instructions=" ".join(
            [
                "Static lookup for HOL Light source files (.ml, .hl): read the statement "
                "and source of a named theorem, definition or tactic, and the names it is built from.",
                "It parses files and the files they load with needs/loads/loadt, plus the core HOL Light sources.",
                "It does not evaluate anything: whether a statement or proof actually runs "
                "must be checked in HOL Light itself.",
                "Results are parsed, not type-checked, so a definition made by an unusual "
                "command may be missing.",
            ]
        ),
    )

    def prepare(file: str) -> tuple[str, list[str]]:
        # Indexes the file and its dependencies. Unchanged files are not parsed again.
        # Returns the path and the names of the loads that could not be found.
        file_path = resolve_path(file, settings.workspace)
        unresolved = service.index(file_path, True)
        return file_path, sorted({dep.name for dep in unresolved})

    @server.tool(
        name="definition_source",
        description=" ".join(
            [
                "The source code of the definition of a tactic, conversion, rule or other OCaml value "
                "(or of a theorem or definition), and the names it is built from.",
                "Every name used in the source (outside comments, strings and HOL terms) is resolved as Go to "
                "Definition resolves it there: `references` lists the theorems and definitions it uses, with their "
                "statements. References that carry nothing beyond a name are left out; read helper names from the "
                "source itself and ask again with depth for their sources. Names with no indexed definition are left "
                "out. No file locations are returned.",
                "When a source is cut at max_chars, only the names in the part returned are listed.",
                "With depth > 0 the sources of the referenced functions are included too, breadth first, each listed "
                "with `via`, the name that uses it, until max_total_chars is reached; names left out are listed in "
                "not_expanded and can be passed back to this tool.",
                "A name defined in several files (e.g., a helper tactic each proof defines for itself) gives one "
                "entry per definition: pass file to get the one a proof uses.",
                "With file, `unresolved_loads` names the files it or its dependencies load that could not be "
                "found; definitions from them are missing from the result.",
                "Theorems and constant definitions are listed with their statements; their proofs are not expanded.",
                "Local variables that share a name with a global definition are reported as references too.",
            ]
        ),
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def definition_source(
        name: Annotated[str, Field(description="The name to look up, e.g. ARM_STEPS_TAC "
                                    "(may be qualified with modules: Module.name)")],
        file: Annotated[str | None, Field(description="Only definitions visible from this file "
                                           "(the file and its dependencies). Without it, every indexed "
                                           "definition with this name")] = None,
        depth: Annotated[int, Field(description="How many levels of referenced functions to include "
                                     "sources for (0: only the definition itself)",
                                     ge=0, le=10)] = 0,
        max_chars: Annotated[int, Field(description="Maximum characters of each source "
                                         "(longer sources are cut and marked truncated)",
                                         ge=1)] = 8000,
        max_total_chars: Annotated[int, Field(description="Leave out definitions which would make the result "
                                               "longer than this many characters (the first definition "
                                               "is always included)", ge=1)] = 20000,
    ) -> str:
        unresolved: list[str] = []
        deps = None
        if file is not None:
            file_path, unresolved = prepare(file)
            deps = service.database.all_dependencies(file_path)
        roots = [s for s in service.find_symbols(name, deps) if s.kind != "module"]
        if not roots:
            raise ValueError(
                f"No definition of {name} is indexed"
                + (f" in {file} or its dependencies" if file else "")
                + ". Try the qualified name (Module.name)."
                + (f" Loads that could not be found: {', '.join(unresolved)}." if unresolved else "")
            )
        def key(s: SymbolInfo) -> str:
            return f"{s.path}:{s.offset}"

        visited = {key(s) for s in roots}
        seen_sources: set[str] = set()
        # Each item: the symbol, its expansion level, and the name that uses it.
        queue: list[tuple[SymbolInfo, int, str | None]] = [(symbol, 0, None) for symbol in roots]
        definitions: list[dict[str, object]] = []
        not_expanded: list[dict[str, str]] = []
        total = 0
        while queue:
            symbol, level, via = queue.pop(0)
            source = service.source(symbol)
            text = source.doc.text[source.start:source.end] if source else ""
            references: list[Reference] = []
            if source:
                doc = source.doc
                # Only the names in the part of the source which is returned.
                if len(text) > max_chars:
                    shown_end = min(source.start + max_chars, len(doc.text))
                else:
                    shown_end = source.end
                references = service.references(doc, source.start, shown_end, symbol)
            shown_source = text[:max_chars] if source else None
            statement = _clip(symbol.content) if symbol.kind != "value" and symbol.content else None
            # The same file can reach the index under two paths; collapse
            # byte-identical definitions so each is reported once.
            identity = json.dumps([symbol.full_name, symbol.kind, shown_source, statement])
            if identity in seen_sources:
                continue
            seen_sources.add(identity)
            entry: dict[str, object] = {"name": symbol.full_name, "kind": symbol.kind}
            if via:
                entry["via"] = via
            if shown_source:
                entry["source"] = shown_source
            if len(text) > max_chars:
                entry["truncated"] = True
                entry["chars"] = len(text)
            if statement:
                entry["statement"] = statement
            # References that carry nothing beyond a name are left out.
            entry["references"] = [
                {"name": ref.name, "kind": s.kind, "statement": _clip_short(s.content)}
                for ref in references
                for s in ref.symbols
                if s.kind != "value" and s.content
            ]
            # The budget is the size of the result (as written below), not of the sources alone.
            size = len(json.dumps(entry, indent=1, ensure_ascii=False))
            if definitions and total + size > max_total_chars:
                skipped = {"name": symbol.full_name}
                if via:
                    skipped["via"] = via
                not_expanded.append(skipped)
                continue
            definitions.append(entry)
            total += size
            if level < depth:
                for ref in references:
                    for s in ref.symbols:
                        if s.kind == "value" and key(s) not in visited:
                            visited.add(key(s))
                            queue.append((s, level + 1, symbol.full_name))
        result: dict[str, object] = {"definitions": definitions}
        if not_expanded:
            result["not_expanded"] = not_expanded[:MAX_NOT_EXPANDED]
        if len(not_expanded) > MAX_NOT_EXPANDED:
            result["not_expanded_total"] = len(not_expanded)
        if unresolved:
            result["unresolved_loads"] = unresolved
        return json.dumps(result, indent=1, ensure_ascii=False)

    return server


def main(argv: list[str] | None = None) -> None:
    settings, _ = parse_settings(argv, __doc__)
    service = HolLanguageService(settings)
    # Index core HOL Light, then (unless disabled) every workspace file.
    # A bad HOL Light directory or root path stops the server here.
    service.database.index_base_hol_light_files(settings.hol_path)
    expand_root_paths(settings)
    if settings.index_workspace:
        unresolved = service.index_workspace()
        if unresolved:
            logger.warning("Loads not found in the workspace: %s",
                           ", ".join(sorted({dep.name for dep in unresolved})))
    server = create_server(service, settings)
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr)
    main()
