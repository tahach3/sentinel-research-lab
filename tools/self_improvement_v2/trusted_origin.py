"""Fail-closed trusted-code origin pin for Self-Improvement V2 worker modules.

Classifier, validators, and finalizer must load from the reviewed install root and
match a content-addressed tree digest pin — not merely reside under a path derived
from the imported module's __file__ (self-anchored path checks alone are insufficient).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from tools.self_improvement_v2.git_worker import run_git
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

TRUSTED_MODULE_NAMES = (
    "tools.self_improvement_v2.risk_authority",
    "tools.self_improvement_v2.review_gate",
    "tools.self_improvement_v2.patch_validator",
    "tools.self_improvement_v2.finalizer",
    "tools.self_improvement_v2.workflow_validator",
    "tools.self_improvement_v2.path_policy",
    "tools.self_improvement_v2.pilot_budget",
)

PIN_REL = Path("specs/self_improvement/v2/trusted_origin_pin.json")


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


def _module_relpath(module_name: str) -> str:
    return str(Path(*module_name.split(".")).with_suffix(".py")).replace("\\", "/")


def resolve_reviewed_install_root(explicit: Path | None = None) -> Path:
    """Resolve install root without trusting only an imported module's __file__."""
    if explicit is not None:
        root = explicit.expanduser().resolve()
    else:
        env = os.environ.get("SRL_REPOSITORY_ROOT", "").strip()
        if env:
            root = Path(env).expanduser().resolve()
        else:
            # Walk from process cwd for the reviewed repo marker (not from module __file__).
            cur = Path.cwd().resolve()
            root = None
            for candidate in (cur, *cur.parents):
                if (candidate / PIN_REL).is_file() and (candidate / ".git").exists():
                    root = candidate
                    break
            if root is None:
                # Last resort: package layout adjacent to this file (still verified via pin).
                from tools.self_improvement_v2.schema_loader import worker_package_root

                root = worker_package_root().resolve()
    marker = root / PIN_REL
    if not marker.is_file():
        raise TrustedOriginError(f"trusted origin pin missing at {PIN_REL.as_posix()}")
    if not (root / ".git").exists():
        raise TrustedOriginError("reviewed install root must be a git checkout")
    return root


def trusted_modules_tree_digest(install_root: Path | None = None) -> tuple[str, dict[str, str]]:
    """Return (combined digest, per-module sha256) from on-disk bytes under install_root."""
    root = resolve_reviewed_install_root(install_root)
    per: dict[str, str] = {}
    h = hashlib.sha256()
    for name in TRUSTED_MODULE_NAMES:
        rel = _module_relpath(name)
        path = root / rel
        if not path.is_file():
            raise TrustedOriginError(f"trusted module missing from install: {rel}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        per[name] = digest
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest(), per


def trusted_modules_git_head_digest(install_root: Path | None = None) -> str:
    """Content+HEAD digest anchoring trusted modules to the reviewed commit/tree."""
    digest, _ = trusted_modules_tree_digest(install_root)
    return digest


def load_trusted_origin_pin(install_root: Path | None = None) -> dict[str, Any]:
    root = resolve_reviewed_install_root(install_root)
    return json.loads((root / PIN_REL).read_text(encoding="utf-8"))


def assert_module_from_worker_install(
    module: ModuleType,
    *,
    install_root: Path | None = None,
) -> Path:
    root = resolve_reviewed_install_root(install_root)
    path = _module_file(module)
    if path is None:
        raise TrustedOriginError(f"module {module.__name__} has no __file__ (origin unverifiable)")
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
    """Ensure security-critical modules resolve under the reviewed install and match the pin."""
    root = resolve_reviewed_install_root(install_root)
    assert_no_worktree_on_sys_path(explicit_forbidden=explicit_forbidden_worktrees)
    origins: dict[str, str] = {}
    for name in module_names:
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        path = assert_module_from_worker_install(module, install_root=root)
        # Loaded bytes must match the reviewed tree path (not a different file of the same name).
        rel = _module_relpath(name)
        expected_path = (root / rel).resolve()
        same = path == expected_path
        if not same:
            try:
                same = path.samefile(expected_path)
            except OSError:
                same = False
        if not same:
            raise TrustedOriginError(
                f"module {name} loaded from {path} but reviewed path is {expected_path}"
            )
        origins[name] = str(path)

    combined, per = trusted_modules_tree_digest(root)
    pin = load_trusted_origin_pin(root)
    expected = pin.get("combined")
    if not isinstance(expected, str) or expected != combined:
        raise TrustedOriginError(
            "trusted modules tree digest mismatch vs reviewed pin "
            f"(expected {expected}, got {combined})"
        )
    pin_modules = pin.get("modules") or {}
    for name, digest in per.items():
        if pin_modules.get(name) != digest:
            raise TrustedOriginError(f"trusted module digest mismatch for {name}")

    head = run_git(["rev-parse", "HEAD"], cwd=root, check=True).stdout.decode("utf-8").strip()
    return {
        "install_root": str(root),
        "modules": origins,
        "module_content_sha256": per,
        "trusted_modules_git_head_digest": combined,
        "git_head": head,
        "pin_path": str(PIN_REL).replace("\\", "/"),
    }


def reject_worktree_as_import_root(candidate: Path, *, install_root: Path | None = None) -> None:
    """Explicit guard when a caller attempts to treat a worktree as the code root."""
    root = resolve_reviewed_install_root(install_root)
    cand = candidate.resolve()
    if cand == root:
        return
    if "srl-si2-wt-" in str(cand):
        raise TrustedOriginError("candidate worktree cannot be used as trusted code root")
    nested = cand / "tools" / "self_improvement_v2"
    if nested.is_dir() and not _is_under(nested, root):
        raise TrustedOriginError("non-install self_improvement_v2 tree rejected as origin")
