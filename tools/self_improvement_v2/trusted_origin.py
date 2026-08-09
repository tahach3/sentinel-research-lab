"""Fail-closed trusted-code origin pin for Self-Improvement V2 worker modules.

Trust requires separately authenticated launcher anchors:
  SRL_REPOSITORY_ROOT + SRL_REVIEWED_HEAD

Authority is never derived from CWD, package root, or a self-consistent pin inside
an arbitrary alternate checkout alone. The pin binds module content digests
(including this verifier) to pin.reviewed_git_head, which must match SRL_REVIEWED_HEAD.
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

# Verifier is authenticated with the other pinned modules (env anchors first).
TRUSTED_MODULE_NAMES = (
    "tools.self_improvement_v2.trusted_origin",
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


def _require_launcher_anchors() -> tuple[Path, str]:
    """Fail closed unless immutable externally supplied root + reviewed HEAD are present."""
    env_root = os.environ.get(ENV_REPOSITORY_ROOT, "").strip()
    if not env_root:
        raise TrustedOriginError(
            "SRL_REPOSITORY_ROOT required (fail-closed; CWD/package root are not authority)"
        )
    env_head = os.environ.get(ENV_REVIEWED_HEAD, "").strip()
    if not env_head or len(env_head) < 40:
        raise TrustedOriginError(
            "SRL_REVIEWED_HEAD required (fail-closed; pin self-identity is not authority)"
        )
    root = Path(env_root).expanduser().resolve()
    if not root.is_dir():
        raise TrustedOriginError("SRL_REPOSITORY_ROOT must be an existing directory")
    marker = root / PIN_REL
    if not marker.is_file():
        raise TrustedOriginError(f"trusted origin pin missing at {PIN_REL.as_posix()}")
    if not (root / ".git").exists():
        raise TrustedOriginError("reviewed install root must be a git checkout")
    return root, env_head


def resolve_reviewed_install_root(explicit: Path | None = None) -> Path:
    """Resolve install root solely from SRL_REPOSITORY_ROOT (never CWD / package root)."""
    root, _env_head = _require_launcher_anchors()
    if explicit is not None and Path(explicit).expanduser().resolve() != root:
        raise TrustedOriginError(
            "install_root is not the reviewed worker install (SRL_REPOSITORY_ROOT)"
        )
    return root


def module_tree_digest_at(root: Path, module_names: Iterable[str] = TRUSTED_MODULE_NAMES) -> tuple[str, dict[str, str]]:
    """Digest trusted modules under root from on-disk bytes (no identity policy)."""
    per: dict[str, str] = {}
    h = hashlib.sha256()
    for name in module_names:
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


def trusted_modules_tree_digest(install_root: Path | None = None) -> tuple[str, dict[str, str]]:
    """Return (combined digest, per-module sha256) under the reviewed install root."""
    root = resolve_reviewed_install_root(install_root)
    return module_tree_digest_at(root)


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
    """Ensure security-critical modules resolve under the reviewed install and match the pin.

    Bootstrap order (fail-closed):
      1) require SRL_REPOSITORY_ROOT + SRL_REVIEWED_HEAD
      2) bind pin.reviewed_git_head to SRL_REVIEWED_HEAD
      3) verify all pinned modules (including trusted_origin) against pin + git blobs
    """
    # 1) Externally supplied anchors — never CWD / self-pinned shadow.
    root, env_head = _require_launcher_anchors()
    if install_root is not None:
        reject_worktree_as_import_root(Path(install_root), install_root=root)
        if Path(install_root).expanduser().resolve() != root:
            raise TrustedOriginError(
                "alternate checkout/import root rejected; not the reviewed worker install"
            )
    reject_worktree_as_import_root(root, install_root=root)
    assert_no_worktree_on_sys_path(explicit_forbidden=explicit_forbidden_worktrees)

    # 2) Pin vs launcher reviewed HEAD (pin alone is not authority).
    pin = load_trusted_origin_pin(root)
    reviewed_head = pin.get("reviewed_git_head")
    if not isinstance(reviewed_head, str) or len(reviewed_head) < 40:
        raise TrustedOriginError("trusted origin pin missing reviewed_git_head")

    live_head = _git_head(root)
    rels = [_module_relpath(name) for name in TRUSTED_MODULE_NAMES]

    def _no_trusted_module_drift(left: str, right: str) -> bool:
        drifted = run_git(
            ["diff", "--quiet", left, right, "--", *rels],
            cwd=root,
            check=False,
        )
        return drifted.returncode == 0

    if env_head == reviewed_head:
        # Primary bind: launcher names the pin's reviewed content anchor.
        if live_head != reviewed_head and not _no_trusted_module_drift(reviewed_head, live_head):
            raise TrustedOriginError(
                f"git HEAD {live_head} drifted trusted modules vs reviewed_git_head {reviewed_head}"
            )
    elif env_head == live_head and _no_trusted_module_drift(reviewed_head, live_head):
        # Two-step pin successor: launcher may name final tip when trusted modules still
        # match pin.reviewed_git_head blobs (pin-metadata-only commits after modules tip).
        pass
    else:
        raise TrustedOriginError(
            "reviewed HEAD identity mismatch (SRL_REVIEWED_HEAD vs pin.reviewed_git_head)"
        )

    # 3) Authenticate verifier + other pinned modules (loaded bytes + pin + git blobs).
    names = tuple(module_names)
    if "tools.self_improvement_v2.trusted_origin" not in names:
        names = ("tools.self_improvement_v2.trusted_origin", *names)

    origins: dict[str, str] = {}
    for name in names:
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

    combined, per = module_tree_digest_at(root, TRUSTED_MODULE_NAMES)
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
        file_digest = _sha256_bytes(Path(origins[name]).read_bytes())
        if file_digest != digest:
            raise TrustedOriginError(f"loaded module bytes mismatch pin for {name}")

    # Bind content digests to immutable git blobs at reviewed_git_head (== SRL_REVIEWED_HEAD).
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
