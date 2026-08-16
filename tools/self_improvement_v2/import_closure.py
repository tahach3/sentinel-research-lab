"""Compute static import closure of the SI2 worker for pin coverage checks.

LIMIT (stated): this is **static AST analysis** of top-level and function-level
`import` / `from … import` statements (absolute and relative) that resolve to
`tools.self_improvement_v2.*`, plus ancestor package `__init__` modules under
that prefix. It does **not** resolve:
  - dynamic imports via `importlib.import_module(...)` — including **literal**
    module-name strings (not only variable forms)
  - `__import__(...)` — including **literal** names (not only non-literals)
  - plugin/entry-point loading
  - string-built module names

TYPE_CHECKING-only imports **are** included (over-inclusive / fail-safe).

A calculator that under-computes would let the pin under-cover while the
equality test still passes — hence the negative test that injects a module
into the closure and requires the equality check to fail.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_PREFIX = "tools.self_improvement_v2"
ENTRYPOINT = "tools.self_improvement_v2.runtime_bridge"


def module_name_to_relpath(module_name: str) -> str:
    """Legacy helper: always returns ``*.py`` (not package ``__init__.py``)."""
    return str(Path(*module_name.split(".")).with_suffix(".py")).replace("\\", "/")


def module_file_relpath(root: Path, module_name: str) -> str | None:
    """Return repo-relative path for a module file or package ``__init__.py``."""
    root = root.resolve()
    file_rel = module_name_to_relpath(module_name)
    if (root / file_rel).is_file():
        return file_rel
    init_rel = str(Path(*module_name.split(".")) / "__init__.py").replace("\\", "/")
    if (root / init_rel).is_file():
        return init_rel
    return None


def _package_ancestors(module_name: str) -> list[str]:
    """Ancestor packages under PACKAGE_PREFIX (inclusive of the prefix package)."""
    if module_name != PACKAGE_PREFIX and not module_name.startswith(PACKAGE_PREFIX + "."):
        return []
    parts = module_name.split(".")
    out: list[str] = []
    while len(parts) > 3:
        parts = parts[:-1]
        out.append(".".join(parts))
    if module_name != PACKAGE_PREFIX:
        out.append(PACKAGE_PREFIX)
    return out


def _absolute_from_relative(
    current_module: str,
    *,
    is_package: bool,
    level: int,
    module: str | None,
) -> str | None:
    """Return the absolute module/package named by a relative ImportFrom."""
    parts = current_module.split(".")
    pkg = parts[:] if is_package else parts[:-1]
    if level > len(pkg):
        return None
    # level=1 → stay at pkg; level=2 → parent of pkg; …
    anchor = pkg[: len(pkg) - (level - 1)]
    if module:
        return ".".join([*anchor, *module.split(".")]) if anchor else module
    return ".".join(anchor)


def _literal_imports(
    tree: ast.AST,
    *,
    current_module: str,
    is_package: bool,
) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE_PREFIX):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = _absolute_from_relative(
                    current_module,
                    is_package=is_package,
                    level=node.level,
                    module=node.module,
                )
                if base is None:
                    continue
                if base == PACKAGE_PREFIX or base.startswith(PACKAGE_PREFIX + "."):
                    found.add(base)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    # `from .pkg import name` → base already includes pkg;
                    # `from . import name` → child is base.name
                    child = f"{base}.{alias.name}" if node.module is None else f"{base}.{alias.name}"
                    if child == PACKAGE_PREFIX or child.startswith(PACKAGE_PREFIX + "."):
                        found.add(child)
                continue
            if node.module and node.module.startswith(PACKAGE_PREFIX):
                found.add(node.module)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    found.add(f"{node.module}.{alias.name}")
    return found


def _resolve_existing(root: Path, name: str) -> str | None:
    """Return the longest existing module name under root for name or its parents."""
    parts = name.split(".")
    while len(parts) >= 3:  # tools.self_improvement_v2.at_least
        candidate = ".".join(parts)
        if module_file_relpath(root, candidate) is not None:
            return candidate
        parts.pop()
    return None


def compute_static_import_closure(
    root: Path,
    *,
    entrypoint: str = ENTRYPOINT,
) -> frozenset[str]:
    """Return frozenset of tools.self_improvement_v2.* modules statically reachable."""
    root = root.resolve()
    pending = [entrypoint]
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        rel = module_file_relpath(root, name)
        if rel is None:
            continue
        seen.add(name)
        is_package = rel.endswith("/__init__.py")
        tree = ast.parse((root / rel).read_text(encoding="utf-8"), filename=str(root / rel))
        # Ancestor package __init__ modules execute on import — must be pinned.
        for ancestor in _package_ancestors(name):
            if ancestor not in seen and module_file_relpath(root, ancestor) is not None:
                pending.append(ancestor)
        for raw in _literal_imports(tree, current_module=name, is_package=is_package):
            resolved = _resolve_existing(root, raw)
            if resolved and resolved not in seen:
                pending.append(resolved)
    return frozenset(seen)


def assert_pin_covers_static_closure(
    root: Path,
    pinned_names: tuple[str, ...] | list[str] | set[str] | frozenset[str],
    *,
    entrypoint: str = ENTRYPOINT,
) -> frozenset[str]:
    """Fail if pinned set != static import closure of the worker entrypoint."""
    closure = compute_static_import_closure(root, entrypoint=entrypoint)
    pinned = frozenset(pinned_names)
    if pinned != closure:
        missing = sorted(closure - pinned)
        extra = sorted(pinned - closure)
        raise AssertionError(
            "trusted pin set must equal static import closure of "
            f"{entrypoint}; missing={missing} extra={extra}"
        )
    return closure
