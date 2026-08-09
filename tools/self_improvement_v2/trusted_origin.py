"""Fail-closed trusted-code origin pin for Self-Improvement V2 worker modules.

Trust is anchored to the reviewed worker install identity (env / cwd discovery) and
a pin that binds module content digests to an exact reviewed git HEAD — not to a
self-consistent pin inside an arbitrary alternate checkout.
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
ENV_REPOSITORY_ROOT = "SRL_REPOSITORY_ROOT"
ENV_REVIEWED_HEAD = "SRL_REVIEWED_HEAD"


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


def _canonical_bytes(data: bytes) -> bytes:
    """Normalize text to LF so Windows working-tree CRLF matches git blob digests."""
    return data.replace(b"\r\n", b"\n")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(_canonical_bytes(data)).hexdigest()


def _git_head(root: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=root, check=True).stdout.decode("utf-8").strip()


def _git_blob_digest(root: Path, reviewed_head: str, rel: str) -> str:
    """Digest of immutable git object bytes at reviewed_head:rel (not working tree)."""
    proc = run_git(["show", f"{reviewed_head}:{rel}"], cwd=root, check=False)
    if proc.returncode != 0:
        raise TrustedOriginError(f"reviewed git blob missing: {reviewed_head}:{rel}")
    return _sha256_bytes(proc.stdout)


def resolve_reviewed_install_root(explicit: Path | None = None) -> Path:
    """Resolve install root from env/cwd — explicit roots cannot override env identity."""
    env = os.environ.get(ENV_REPOSITORY_ROOT, "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if explicit is not None and Path(explicit).expanduser().resolve() != root:
            raise TrustedOriginError(
                "install_root is not the reviewed worker install (SRL_REPOSITORY_ROOT)"
            )
    elif explicit is not None:
        root = explicit.expanduser().resolve()
    else:
        cur = Path.cwd().resolve()
        root = None
        for candidate in (cur, *cur.parents):
            if (candidate / PIN_REL).is_file() and (candidate / ".git").exists():
                root = candidate
                break
        if root is None:
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
        digest = _sha256_bytes(path.read_bytes())
        per[name] = digest
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest(), per


def head_content_binding_digest(reviewed_head: str, content_combined: str) -> str:
    """Cryptographically bind reviewed HEAD to the trusted module content digest."""
    h = hashlib.sha256()
    h.update(reviewed_head.encode("ascii"))
    h.update(b"\0")
    h.update(content_combined.encode("ascii"))
    h.update(b"\0")
    return h.hexdigest()


def trusted_modules_git_head_digest(install_root: Path | None = None) -> str:
    """HEAD-bound digest anchoring trusted modules to the reviewed commit."""
    root = resolve_reviewed_install_root(install_root)
    content, _ = trusted_modules_tree_digest(root)
    pin = load_trusted_origin_pin(root)
    reviewed_head = pin.get("reviewed_git_head")
    if not isinstance(reviewed_head, str) or len(reviewed_head) < 40:
        raise TrustedOriginError("trusted origin pin missing reviewed_git_head")
    return head_content_binding_digest(reviewed_head, content)


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


def reject_worktree_as_import_root(candidate: Path, *, install_root: Path | None = None) -> None:
    """Reject alternate checkout/worktree roots by verified identity (not only name markers)."""
    root = resolve_reviewed_install_root(install_root)
    cand = candidate.resolve()
    if cand == root:
        return
    if "srl-si2-wt-" in str(cand):
        raise TrustedOriginError("candidate worktree cannot be used as trusted code root")
    nested = cand / "tools" / "self_improvement_v2"
    if nested.is_dir() and not _is_under(nested, root):
        raise TrustedOriginError("non-install self_improvement_v2 tree rejected as origin")
    if (cand / PIN_REL).is_file() and cand != root:
        raise TrustedOriginError("alternate checkout with origin pin rejected as import root")
    if cand != root:
        raise TrustedOriginError("import root is not the reviewed worker install")


def assert_trusted_code_origin(
    *,
    install_root: Path | None = None,
    module_names: Iterable[str] = TRUSTED_MODULE_NAMES,
    explicit_forbidden_worktrees: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Ensure security-critical modules resolve under the reviewed install and match the pin."""
    # Canonical identity from env/cwd — never trust a self-pinned alternate checkout.
    canonical = resolve_reviewed_install_root(None)
    if install_root is not None:
        reject_worktree_as_import_root(Path(install_root), install_root=canonical)
        if Path(install_root).expanduser().resolve() != canonical:
            raise TrustedOriginError(
                "alternate checkout/import root rejected; not the reviewed worker install"
            )
    root = canonical
    # Primary assertion always invokes worktree/alternate-root rejection.
    reject_worktree_as_import_root(root, install_root=root)
    assert_no_worktree_on_sys_path(explicit_forbidden=explicit_forbidden_worktrees)

    pin = load_trusted_origin_pin(root)
    reviewed_head = pin.get("reviewed_git_head")
    if not isinstance(reviewed_head, str) or len(reviewed_head) < 40:
        raise TrustedOriginError("trusted origin pin missing reviewed_git_head")

    live_head = _git_head(root)
    env_head = os.environ.get(ENV_REVIEWED_HEAD, "").strip()
    if env_head and env_head != reviewed_head:
        raise TrustedOriginError(
            "reviewed HEAD identity mismatch (SRL_REVIEWED_HEAD vs pin.reviewed_git_head)"
        )
    if live_head != reviewed_head:
        # Allow pin-only / unrelated commits after the reviewed HEAD, but never trusted-module drift.
        rels = [_module_relpath(name) for name in TRUSTED_MODULE_NAMES]
        drifted = run_git(
            ["diff", "--quiet", reviewed_head, live_head, "--", *rels],
            cwd=root,
            check=False,
        )
        if drifted.returncode != 0:
            raise TrustedOriginError(
                f"git HEAD {live_head} drifted trusted modules vs reviewed_git_head {reviewed_head}"
            )
        if env_head and env_head != live_head and env_head != reviewed_head:
            raise TrustedOriginError(
                "reviewed HEAD identity mismatch (SRL_REVIEWED_HEAD / pin / git)"
            )

    origins: dict[str, str] = {}
    for name in module_names:
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        path = assert_module_from_worker_install(module, install_root=root)
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
    expected_combined = pin.get("combined")
    if not isinstance(expected_combined, str) or expected_combined != combined:
        raise TrustedOriginError(
            "trusted modules tree digest mismatch vs reviewed pin "
            f"(expected {expected_combined}, got {combined})"
        )
    pin_modules = pin.get("modules") or {}
    for name, digest in per.items():
        if pin_modules.get(name) != digest:
            raise TrustedOriginError(f"trusted module digest mismatch for {name}")
        # Loaded file bytes must match pin.
        file_digest = _sha256_bytes(Path(origins[name]).read_bytes())
        if file_digest != digest:
            raise TrustedOriginError(f"loaded module bytes mismatch pin for {name}")

    # Bind content digests to immutable git blobs at reviewed_git_head. Dirty working-tree
    # mutations with a regenerated pin fail: blobs at the reviewed commit diverge, and
    # uncommitted trusted-module edits are rejected outright.
    for name, digest in per.items():
        rel = _module_relpath(name)
        dirty = run_git(["diff", "--quiet", "HEAD", "--", rel], cwd=root, check=False)
        if dirty.returncode != 0:
            raise TrustedOriginError(f"trusted module dirty vs HEAD: {rel}")
        blob_digest = _git_blob_digest(root, reviewed_head, rel)
        if blob_digest != digest:
            raise TrustedOriginError(
                f"trusted module git blob at reviewed HEAD mismatches pin/file for {name}"
            )

    binding = head_content_binding_digest(reviewed_head, combined)
    expected_binding = pin.get("head_content_binding")
    if not isinstance(expected_binding, str) or expected_binding != binding:
        raise TrustedOriginError("head_content_binding mismatch vs reviewed pin")

    return {
        "install_root": str(root),
        "modules": origins,
        "module_content_sha256": per,
        "trusted_modules_git_head_digest": binding,
        "git_head": live_head,
        "reviewed_git_head": reviewed_head,
        "pin_path": str(PIN_REL).replace("\\", "/"),
    }
