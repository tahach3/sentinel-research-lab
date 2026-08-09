"""Fail-closed trusted-code origin pin for Self-Improvement V2 worker modules.

Classifier, validators, and finalizer must load from the worker install
(worker_package_root), never from a candidate worktree or worktree-derived sys.path.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.schema_loader import worker_package_root

TRUSTED_MODULE_NAMES = (
    "tools.self_improvement_v2.risk_authority",
    "tools.self_improvement_v2.review_gate",
    "tools.self_improvement_v2.patch_validator",
    "tools.self_improvement_v2.finalizer",
    "tools.self_improvement_v2.workflow_validator",
    "tools.self_improvement_v2.path_policy",
    "tools.self_improvement_v2.pilot_budget",
)


class TrustedOriginError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["TRUSTED_ORIGIN_VIOLATION"], message, state="POLICY_REJECTED")


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _module_file(module: ModuleType) -> Path | None:
    raw = getattr(module, "__file__", None)
    if not raw:
        return None
    return Path(raw).resolve()


def assert_module_from_worker_install(
    module: ModuleType,
    *,
    install_root: Path | None = None,
) -> Path:
    root = (install_root or worker_package_root()).resolve()
    path = _module_file(module)
    if path is None:
        raise TrustedOriginError(f"module {module.__name__} has no __file__ (origin unverifiable)")
    # Worker package lives at <install_root>/tools/self_improvement_v2/...
    if not _is_under(path, root):
        raise TrustedOriginError(
            f"module {module.__name__} loaded from outside worker install: origin rejected"
        )
    return path


def assert_no_worktree_on_sys_path(
    *,
    worktree_markers: Iterable[str] = ("srl-si2-wt-",),
    explicit_forbidden: Iterable[Path] | None = None,
) -> None:
    forbidden = [p.resolve() for p in (explicit_forbidden or [])]
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            path = Path(entry).resolve()
        except OSError:
            continue
        name = path.name
        parent_name = path.parent.name if path.parent else ""
        if any(marker in name or marker in parent_name or marker in str(path) for marker in worktree_markers):
            raise TrustedOriginError(f"worktree-derived sys.path entry rejected: {path.name}")
        for banned in forbidden:
            if path == banned or _is_under(path, banned):
                raise TrustedOriginError("forbidden path present on sys.path")


def assert_trusted_code_origin(
    *,
    install_root: Path | None = None,
    module_names: Iterable[str] = TRUSTED_MODULE_NAMES,
    explicit_forbidden_worktrees: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Ensure security-critical modules resolve under the worker install."""
    root = (install_root or worker_package_root()).resolve()
    assert_no_worktree_on_sys_path(explicit_forbidden=explicit_forbidden_worktrees)
    origins: dict[str, str] = {}
    for name in module_names:
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        path = assert_module_from_worker_install(module, install_root=root)
        origins[name] = str(path)
    return {"install_root": str(root), "modules": origins}


def reject_worktree_as_import_root(candidate: Path, *, install_root: Path | None = None) -> None:
    """Explicit guard when a caller attempts to treat a worktree as the code root."""
    root = (install_root or worker_package_root()).resolve()
    cand = candidate.resolve()
    if cand == root:
        return
    if "srl-si2-wt-" in str(cand):
        raise TrustedOriginError("candidate worktree cannot be used as trusted code root")
    # If candidate contains its own tools/self_improvement_v2, still reject when not install.
    nested = cand / "tools" / "self_improvement_v2"
    if nested.is_dir() and not _is_under(nested, root):
        raise TrustedOriginError("non-install self_improvement_v2 tree rejected as origin")
