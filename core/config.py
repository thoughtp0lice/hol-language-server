"""Settings: the non-REPL options of vscode-hol-light, as server flags."""

import argparse
import os
import re
from dataclasses import dataclass, field

DEBUG = bool(os.environ.get("HOL_LS_DEBUG"))

DEFAULT_ROOT_PATHS = [".", "{hol}", "{workspace}"]


@dataclass
class Settings:
    # A HOL Light directory (with hol.ml)
    hol_path: str = ""
    # Where `needs` paths are searched: may contain `.`, `{hol}`, `{workspace}`
    root_paths: list[str] = field(default_factory=lambda: list(DEFAULT_ROOT_PATHS))
    # The workspace root which replaces `{workspace}` in root_paths
    workspace: str = ""
    # Automatically index open documents.
    auto_index: bool = True
    # Index all HOL Light files of the workspace. Needed for definitions
    # which a file sees only because the file which loads it loaded them first.
    index_workspace: bool = False


# The editor settings and the type each must have.
_OPTION_TYPES = {"path": str, "rootPaths": list, "autoIndex": bool, "indexWorkspace": bool}


def default_settings() -> Settings:
    return Settings()


def parse_settings(argv: list[str] | None, description: str | None) -> tuple[Settings, bool]:
    """Settings from the server flags, and whether `--workspace` was given."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--hol-path", default=None)
    parser.add_argument("--root", action="append", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--no-index-workspace", action="store_true")
    args = parser.parse_args(argv)
    settings = default_settings()
    settings.hol_path = args.hol_path or os.environ.get("HOL_LIGHT_DIR", "")
    settings.workspace = args.workspace or os.getcwd()
    if args.root:
        settings.root_paths = args.root
    settings.index_workspace = not args.no_index_workspace
    return settings, args.workspace is not None


def settings_from_options(options: object, base: Settings) -> Settings:
    """The `hol-light` section of the editor settings over the base settings.
    Raises ValueError on an unknown setting or a value of the wrong type."""
    if not isinstance(options, dict):
        raise ValueError(f"hol-light settings must be an object, not {options!r}")
    unknown = sorted(str(key) for key in options if key not in _OPTION_TYPES)
    if unknown:
        raise ValueError(f"Unknown hol-light settings: {', '.join(unknown)}")
    for key, value in options.items():
        if not isinstance(value, _OPTION_TYPES[key]):
            raise ValueError(
                f"hol-light setting {key} must be a {_OPTION_TYPES[key].__name__}, not {value!r}"
            )
    root_paths = options.get("rootPaths", base.root_paths)
    if not all(isinstance(path, str) for path in root_paths):
        raise ValueError(f"hol-light setting rootPaths must hold strings, not {root_paths!r}")
    return Settings(
        hol_path=options.get("path", base.hol_path),
        root_paths=list(root_paths),
        workspace=base.workspace,
        auto_index=options.get("autoIndex", base.auto_index),
        index_workspace=options.get("indexWorkspace", base.index_workspace),
    )


def expand_root_paths(settings: Settings) -> list[str]:
    """Replace the `{hol}` and `{workspace}` parts of the root paths. Raises
    ValueError on another placeholder, an unset value, or an empty path."""
    values = {"hol": settings.hol_path, "workspace": settings.workspace}

    def expand(path: str) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                raise ValueError(f"Root path {path!r}: unknown placeholder {{{key}}}")
            if not values[key]:
                raise ValueError(f"Root path {path!r}: {{{key}}} is not set")
            return values[key]

        expanded = re.sub(r"\{(.*?)\}", replace, path)
        if not expanded:
            raise ValueError("Empty root path")
        return expanded

    return [expand(path) for path in settings.root_paths]
