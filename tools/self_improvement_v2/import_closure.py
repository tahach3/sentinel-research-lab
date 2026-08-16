"""Compute static import closure of the SI2 worker for pin coverage checks.

LIMIT (stated): this is **static AST analysis** of top-level and function-level
`import` / `from … import` statements that resolve to
`tools.self_improvement_v2.*`. It does **not** resolve:
  - dynamic imports (`importlib.import_module(variable)`)
  - `__import__` with non-literal names
  - plugin/entry-point loading
  - string-built module names

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
    return str(Path(*module_name.split(".")).with_suffix(".py")).replace("\\", "/")


def _literal_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE_PREFIX):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(PACKAGE_PREFIX):
                # from tools.self_improvement_v2.foo import bar  → module foo
                # from tools.self_improvement_v2 import foo → package submodule
                if node.level and node.level > 0:
                    continue
                found.add(node.module)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    child = f"{node.module}.{alias.name}"
                    # Prefer submodule if it exists as a file; callers resolve.
                    found.add(child)
    return found


def _resolve_existing(root: Path, name: str) -> str | None:
    """Return the longest existing module name under root for name or its parents."""
    parts = name.split(".")
    while len(parts) >= 3:  # tools.self_improvement_v2.at_least
        candidate = ".".join(parts)
        path = root / module_name_to_relpath(candidate)
        if path.is_file():
            return candidate
        # package __init__
        init = root / Path(*parts) / "__init__.py"
        if init.is_file():
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
        rel = module_name_to_relpath(name)
        path = root / rel
        if not path.is_file():
            continue
        seen.add(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for raw in _literal_imports(tree):
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
