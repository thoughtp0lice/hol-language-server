"""In-memory index of parsed HOL Light sources and their dependencies."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable

from hol_language_server_core import util
from hol_language_server_core.config import DEBUG
from hol_language_server_core.parser import CustomCommands, Definition, Module, OpenDecl, ParseResult, parse_text
from hol_language_server_core.parser import Dependency as ParsedDependency
from hol_language_server_core.text import Location, Position, TextDoc, location

logger = logging.getLogger(__name__)

HOL_LIGHT_BASE_SKIP = re.compile(r"^(?:bignum_num|database|make|pa_j|update_database)")


class Dependency:
    def __init__(self, dep: ParsedDependency, path: str | None = None) -> None:
        self._dep = dep
        self.path = path

    @property
    def is_resolved(self) -> bool:
        return self.path is not None

    @property
    def name(self) -> str:
        return self._dep.name

    def get_location(self) -> Location | None:
        if self.path is None:
            return None
        return location(self.path, Position(0, 0))


def _resolve_dependency_path(dep: ParsedDependency, hol_path: str, base_path: str,
                             root_paths: list[str]) -> str | None:
    if os.path.isabs(dep.name):
        return dep.name if util.file_exists(dep.name, False) else None
    if dep.hol_light_relative:
        # hol_path is only used for `loads` dependencies.
        candidate = os.path.join(hol_path, dep.name)
        return candidate if util.file_exists(candidate, False) else None
    for root in root_paths:
        candidate = os.path.join(base_path if root == "." else root, dep.name)
        if util.file_exists(candidate, False):
            return candidate
    return None


def _resolve_dependencies(parser_deps: list[ParsedDependency], hol_path: str, base_path: str,
                          root_paths: list[str]) -> list[Dependency]:
    return [
        Dependency(
            parser_dep,
            _resolve_dependency_path(parser_dep, hol_path, base_path, root_paths),
        )
        for parser_dep in parser_deps
    ]


class FileIndex:
    """Everything indexed for one file: its dependencies, definitions,
    modules, and the module tracking its open/include statements."""

    def __init__(self, mtime: float | None, dependencies: list[Dependency], result: ParseResult) -> None:
        self.mtime = mtime
        # Resolved and unresolved dependencies. May be cyclic (`needs`
        # allows cyclic dependencies, but the result could be unpredictable).
        self.dependencies = dependencies
        self.definitions = result.definitions
        self.modules = result.modules
        self.global_module = result.global_module


class Database:
    def __init__(self) -> None:
        # Base HOL Light files: every other file is assumed to depend on them.
        self._base_hol_light_files: set[str] = set()
        # Information about all indexed files.
        self._file_index: dict[str, FileIndex] = {}
        # Definitions sharing a name (key) live in different files.
        self._definition_index: dict[str, list[Definition]] = {}
        # Modules sharing a name may live in different files or nest.
        self._module_index: dict[str, list[Module]] = {}
        # Results of all_dependencies and loaders_of; cleared on any change.
        self._dependency_cache: dict[str, set[str]] = {}
        self._open_modules_cache: dict[str, set[Module]] = {}
        self._loaders: dict[str, list[tuple[str, int]]] | None = None
        self._base_hol_light_indexed = False

    def is_base_hol_light_file(self, file_path: str) -> bool:
        return file_path in self._base_hol_light_files

    def get_file_index(self, file_path: str) -> FileIndex | None:
        return self._file_index.get(file_path)

    def filter_by_name(self, predicate: Callable[[str], bool],
                       deps: set[str] | None = None) -> tuple[list[Definition], list[Module]]:
        """Definitions and modules whose names satisfy the predicate,
        in deps when given."""
        defs: list[Definition] = []
        mods: list[Module] = []
        for name, items in self._definition_index.items():
            if predicate(name):
                defs.extend(d for d in items if deps is None or d.get_file_path() in deps)
        for name, items in self._module_index.items():
            if predicate(name):
                mods.extend(m for m in items if deps is None or m.get_file_path() in deps)
        return defs, mods

    def find_dependency(self, file_path: str, name: str) -> Dependency | None:
        file = self._file_index.get(file_path)
        if file is None:
            return None
        for dep in file.dependencies:
            if dep.name == name:
                return dep
        return None

    def _add_to_index(self, file_path: str, result: ParseResult, deps: list[Dependency],
                      mtime: float | None) -> None:
        self._remove_from_index(file_path)
        self._invalidate_caches()
        self._file_index[file_path] = FileIndex(mtime, deps, result)

        def add[T: (Definition, Module)](index: dict[str, list[T]], items: list[T]) -> None:
            for item in items:
                index.setdefault(item.name, []).append(item)

        add(self._definition_index, result.definitions)
        add(self._module_index, result.modules)

    def _remove_from_index(self, file_path: str) -> None:
        file = self._file_index.get(file_path)
        if file is None:
            return
        self._invalidate_caches()

        def remove[T: (Definition, Module)](index: dict[str, list[T]], items: list[T]) -> None:
            for item in items:
                entries = index[item.name]
                entries.remove(item)
                if not entries:
                    del index[item.name]

        remove(self._definition_index, file.definitions)
        remove(self._module_index, file.modules)
        del self._file_index[file_path]

    def index_file(self, file_path: str, hol_path: str, root_paths: list[str] | None,
                   custom: CustomCommands) -> tuple[bool, list[Dependency]]:
        """Index the file when new or modified. Returns whether it was
        indexed and its dependencies (existing ones when untouched)."""
        file = self._file_index.get(file_path)
        mtime = os.stat(file_path).st_mtime
        known = file.mtime if file is not None and file.mtime is not None else -1
        if mtime > known:
            result = parse_text(util.read_text(file_path), file_path, custom)
            if root_paths is None:
                deps = []
            else:
                deps = _resolve_dependencies(
                    result.dependencies,
                    hol_path,
                    os.path.dirname(file_path),
                    root_paths,
                )
            self._add_to_index(file_path, result, deps, mtime)
            return True, deps
        return False, file.dependencies if file is not None else []

    def _add_closure(self, file_path: str, visited: set[str]) -> None:
        if file_path in visited and file_path not in self._base_hol_light_files:
            return
        visited.add(file_path)
        queue = [file_path]
        while queue:
            name = queue.pop()
            file = self._file_index.get(name)
            for dep in file.dependencies if file is not None else []:
                if dep.path is not None and dep.path not in visited:
                    visited.add(dep.path)
                    queue.append(dep.path)

    def _loaders_of(self, file_path: str) -> list[tuple[str, int]]:
        """Files loading the file: [loading file, position in its list]."""
        if self._loaders is None:
            self._loaders = {}
            for loader, file in self._file_index.items():
                for i, dep in enumerate(file.dependencies):
                    if dep.path is not None:
                        self._loaders.setdefault(dep.path, []).append((loader, i))
        return self._loaders.get(file_path, [])

    def load_context(self, file_path: str) -> list[str]:
        """Files loaded before the file by the files loading it.

        For example, s2n-bignum's arm/proofs/base.ml loads
        arm/proofs/decode.ml and then arm/proofs/arm.ml, which uses
        definitions from decode.ml without loading it. The loading files
        themselves are included.
        """
        result: list[str] = []
        seen = {file_path}
        queue = [file_path]
        while queue:
            file = queue.pop()
            for loader, index in self._loaders_of(file):
                if loader in seen:
                    continue
                seen.add(loader)
                result.append(loader)
                deps = self._file_index.get(loader)
                siblings = deps.dependencies if deps is not None else []
                result.extend(
                    util.filter_map(siblings[:index], lambda dep: dep.path)
                )
                queue.append(loader)
        return result

    def all_dependencies(self, file_path: str) -> set[str]:
        """The file's dependencies, plus files loaded before it by its loaders."""
        if file_path in self._dependency_cache:
            return self._dependency_cache[file_path]
        visited = set(self._base_hol_light_files)
        self._add_closure(file_path, visited)
        for file in self.load_context(file_path):
            self._add_closure(file, visited)
        self._dependency_cache[file_path] = visited
        return visited

    def _invalidate_caches(self) -> None:
        self._dependency_cache.clear()
        self._open_modules_cache.clear()
        self._loaders = None

    def resolve_module_name(self, module_name: str, open_modules: set[Module],
                            deps: set[str]) -> set[Module]:
        """Modules for the name. Shadowing modules are all returned."""
        if not module_name:
            return set(open_modules)
        if module_name.endswith("."):
            module_name = module_name[:-1]
        names = module_name.split(".")
        modules: list[Module] = []
        for mod in self._module_index.get(names[0], []):
            if mod.parent is not None:
                if mod.parent in open_modules:
                    modules.append(mod)
            elif mod.get_file_path() in deps:
                modules.append(mod)
        for name in names[1:]:
            if not modules:
                break
            modules = [
                submod
                for mod in modules
                for submod in mod.modules
                if submod.name == name
            ]
        return set(modules)

    def _dependency_open_modules(self, file_path: str, deps: set[str]) -> set[Module]:
        """Top-level opened/included modules of the file's dependencies.

        In the OCaml toplevel they stay open for files loaded later: e.g.,
        HOL Light's fusion.ml defines the kernel in `module Hol` and then
        calls `include Hol`.
        """
        result = self._open_modules_cache.get(file_path)
        if result is None:
            result = set()
            for dep in deps:
                file = None if dep == file_path else self._file_index.get(dep)
                decls: list[OpenDecl] = []
                if file is not None:
                    decls = file.global_module.open_decls + file.global_module.include_decls
                for decl in decls:
                    result.update(self.resolve_module_name(decl.name, result, deps))
            self._open_modules_cache[file_path] = result
        return result

    def all_open_modules(self, file_path: str, offset: int, deps: set[str]) -> set[Module]:
        """All modules open at the offset in the file."""
        result = set(self._dependency_open_modules(file_path, deps))
        file = self._file_index.get(file_path)
        if file is None:
            return result
        # Globally open (and included) modules from the current file.
        for decl in file.global_module.open_decls + file.global_module.include_decls:
            if decl.start < offset:
                result.update(self.resolve_module_name(decl.name, result, deps))
        # Modules defined in the file, sorted by start: previously open
        # modules may affect the visibility of submodules.
        for module in file.modules:
            if module.start <= offset and (module.end is None or module.end > offset):
                result.add(module)
                for decl in module.open_decls:
                    if decl.end < offset:
                        result.update(self.resolve_module_name(decl.name, result, deps))
        return result

    def find_definitions(self, name: str, deps: set[str], allow_global: bool,
                         modules: set[Module]) -> list[Definition]:
        """Definitions of the name in the file's dependencies, visible from
        the global module or one of the given modules."""
        return [
            definition
            for definition in self._definition_index.get(name, [])
            if definition.get_file_path() in deps
            and (definition.module in modules if definition.module is not None else allow_global)
        ]

    def find_all_by_name(self, name: str,
                         deps: set[str] | None = None) -> tuple[list[Definition], list[Module]]:
        """Definitions and modules of the unqualified name, in deps when given."""
        def in_deps(item: Definition | Module) -> bool:
            return deps is None or item.get_file_path() in deps

        return (
            [d for d in self._definition_index.get(name, []) if in_deps(d)],
            [m for m in self._module_index.get(name, []) if in_deps(m)],
        )

    def find_definitions_and_modules(self, word: str, file_path: str,
                                     offset: int) -> tuple[list[Definition], set[Module]]:
        """Definitions and modules the word names at the offset in the file:
        only those the file or its dependencies define, in the global module
        or an open one."""
        deps = self.all_dependencies(file_path)
        open_modules = self.all_open_modules(file_path, offset, deps)
        names = word.split(".")
        name = names[-1] if len(names) > 1 else word
        if len(names) > 1:
            name_modules = self.resolve_module_name(
                ".".join(names[:-1]), open_modules, deps
            )
        else:
            name_modules = open_modules
        return (
            self.find_definitions(name, deps, len(names) == 1, name_modules),
            self.resolve_module_name(word, open_modules, deps),
        )

    def index_base_hol_light_files(self, hol_path: str, custom: CustomCommands) -> None:
        """Index the core HOL Light files once. The HOL Light path is fixed
        for the process, so a later call reuses the first. Raises ValueError
        when hol_path is not a HOL Light directory."""
        if not self._base_hol_light_indexed:
            self._do_index_base_hol_light_files(hol_path, custom)
            self._base_hol_light_indexed = True

    def _do_index_base_hol_light_files(self, hol_path: str, custom: CustomCommands) -> None:
        if DEBUG:
            logger.error("Indexing Base HOL Light files: %s", hol_path)
        if not hol_path:
            raise ValueError("No HOL Light directory: pass --hol-path, set $HOL_LIGHT_DIR, "
                             "or set the hol-light path setting")
        if not util.file_exists(os.path.join(hol_path, "hol.ml"), False):
            raise ValueError(f"Not a HOL Light directory (no hol.ml): {hol_path}")
        for entry in util.read_dir(hol_path):
            name = entry.name
            if entry.is_file() and name.endswith(".ml") and not HOL_LIGHT_BASE_SKIP.match(name):
                file_path = os.path.join(hol_path, entry.name)
                # Add before indexing the file.
                self._base_hol_light_files.add(file_path)
                indexed, _ = self.index_file(file_path, hol_path, None, custom)
                if indexed and DEBUG:
                    logger.error("Indexed: %s", file_path)
        if DEBUG:
            logger.error("Done indexing HOL Light base files")

    def index_document_with_dependencies(self, document: TextDoc, hol_path: str, root_paths: list[str],
                                         full_index: bool, custom: CustomCommands) -> list[Dependency]:
        """Index the document and its dependencies. Returns the unresolved
        dependencies of the document and of its indexed dependencies."""
        # Index HOL Light files first (no-op when already indexed).
        self.index_base_hol_light_files(hol_path, custom)
        doc_path = document.path
        if DEBUG:
            logger.error("Indexing: %s", doc_path)
        result = parse_text(document.text, doc_path, custom)
        doc_dep_names = {dep.name: dep for dep in result.dependencies}
        old_file = self._file_index.get(doc_path)
        old_names = [dep.name for dep in old_file.dependencies] if old_file is not None else []
        if not full_index and not util.difference(doc_dep_names.keys(), old_names):
            # No full indexing and no new dependency names: update the index
            # without resolving dependencies.
            file = self._file_index.get(doc_path)
            deps = (
                [
                    Dependency(doc_dep_names[dep.name], dep.path)
                    for dep in file.dependencies
                    if dep.name in doc_dep_names
                ]
                if file is not None
                else []
            )
            self._add_to_index(doc_path, result, deps, None)
            return [dep for dep in deps if not dep.is_resolved]
        if DEBUG:
            logger.error(
                "Indexing %s dependencies of %s", "all" if full_index else "new", doc_path
            )
        doc_file = self._file_index.get(doc_path)
        old_paths = util.filter_map(
            doc_file.dependencies if doc_file is not None else [], lambda dep: dep.path
        )
        doc_deps = _resolve_dependencies(
            result.dependencies,
            hol_path,
            os.path.dirname(doc_path),
            root_paths,
        )
        unresolved = [dep for dep in doc_deps if not dep.is_resolved]
        # A cyclic dependency on this document indexes it twice; cyclic
        # dependencies should be removed instead.
        self._add_to_index(doc_path, result, doc_deps, None)
        visited = {doc_path}
        new_paths = util.filter_map(doc_deps, lambda dep: dep.path)
        queue = list(new_paths) if full_index else util.difference(new_paths, old_paths)
        while queue:
            dep_path = queue.pop()
            if dep_path in visited:
                continue
            visited.add(dep_path)
            # old_paths is computed before index_file is called.
            known_file = self._file_index.get(dep_path)
            known_deps = known_file.dependencies if known_file is not None else []
            old_paths = util.filter_map(known_deps, lambda dep: dep.path)
            indexed, deps = self.index_file(dep_path, hol_path, root_paths, custom)
            if indexed and DEBUG:
                logger.error("Indexed: %s", dep_path)
            unresolved.extend(dep for dep in deps if not dep.is_resolved)
            new_paths = util.filter_map(deps, lambda dep: dep.path)
            queue.extend(new_paths if full_index else util.difference(new_paths, old_paths))
        return unresolved
