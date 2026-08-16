"""Fail-closed trusted-code origin pin for Self-Improvement V2 (Option A+).

Trust requires separately authenticated launcher anchors:
  SRL_REPOSITORY_ROOT + SRL_REVIEWED_HEAD

The pin is content-digest attestation only (no reviewed HEAD claim). Authority for
HEAD identity is exclusively the launcher. Bootstrap verifies pinned modules
(including runtime_bridge + git_worker) via direct filesystem reads and raw git
subprocess before trusting imported helpers.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError

# Closed under static AST imports (Option A+ execution pin).
# Must equal the static AST import closure of runtime_bridge (+ import_closure itself).
# Does NOT cover dynamic importlib/__import__/string-built loaders — see import_closure.
TRUSTED_MODULE_NAMES = (
    "tools.self_improvement_v2",
    "tools.self_improvement_v2.agent_runtime_contract",
    "tools.self_improvement_v2.canonical",
    "tools.self_improvement_v2.executor",
    "tools.self_improvement_v2.experience_store",
    "tools.self_improvement_v2.finalizer",
    "tools.self_improvement_v2.git_worker",
    "tools.self_improvement_v2.import_closure",
    "tools.self_improvement_v2.models",
    "tools.self_improvement_v2.patch_parser",
    "tools.self_improvement_v2.patch_validator",
    "tools.self_improvement_v2.path_policy",
    "tools.self_improvement_v2.pilot_budget",
    "tools.self_improvement_v2.repair_policy",
    "tools.self_improvement_v2.review_gate",
    "tools.self_improvement_v2.risk_authority",
    "tools.self_improvement_v2.runtime_bridge",
    "tools.self_improvement_v2.runtime_config",
    "tools.self_improvement_v2.schema_loader",
    "tools.self_improvement_v2.trusted_origin",
    "tools.self_improvement_v2.validation_runner",
    "tools.self_improvement_v2.wall_reassert",
    "tools.self_improvement_v2.workflow_normalizer",
    "tools.self_improvement_v2.workflow_validator",
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


def _module_relpath(module_name: str, *, root: Path | None = None) -> str:
    """Repo-relative path for a pinned module or package ``__init__.py``."""
    from tools.self_improvement_v2.import_closure import module_file_relpath, module_name_to_relpath

    base = root if root is not None else Path.cwd()
    rel = module_file_relpath(base, module_name)
    if rel is not None:
        return rel
    return module_name_to_relpath(module_name)


def _canonical_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(_canonical_bytes(data)).hexdigest()


_GIT_ENV_BLOCKLIST_EXACT = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }
)


def _sanitized_git_env() -> dict[str, str]:
    """Drop ambient GIT_* overrides that would rebind the install root (R2-A)."""
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _GIT_ENV_BLOCKLIST_EXACT:
            continue
        if key.startswith("GIT_CONFIG"):
            continue
        out[key] = value
    return out


def _raw_git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    root = Path(cwd).resolve()
    git_dir = root / ".git"
    proc = subprocess.run(
        ["git", f"--git-dir={git_dir}", f"--work-tree={root}", *args],
        cwd=str(root),
        capture_output=True,
        check=False,
        env=_sanitized_git_env(),
    )
    if check and proc.returncode != 0:
        raise TrustedOriginError(f"git {' '.join(args)} failed in reviewed install")
    return proc


def _git_head(root: Path) -> str:
    return _raw_git(["rev-parse", "HEAD"], cwd=root, check=True).stdout.decode("utf-8").strip()


def _git_blob_digest(root: Path, reviewed_head: str, rel: str) -> str:
    proc = _raw_git(["show", f"{reviewed_head}:{rel}"], cwd=root, check=False)
    if proc.returncode != 0:
        raise TrustedOriginError(f"reviewed git blob missing: {reviewed_head}:{rel}")
    return _sha256_bytes(proc.stdout)


def _require_launcher_anchors() -> tuple[Path, str]:
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
    if any(ch in env_head for ch in ("\n", "\r", "\0", " ")):
        raise TrustedOriginError("SRL_REVIEWED_HEAD must be a single canonical git object name")
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
    root, _env_head = _require_launcher_anchors()
    if explicit is not None and Path(explicit).expanduser().resolve() != root:
        raise TrustedOriginError(
            "install_root is not the reviewed worker install (SRL_REPOSITORY_ROOT)"
        )
    return root


def module_tree_digest_at(root: Path, module_names: Iterable[str] = TRUSTED_MODULE_NAMES) -> tuple[str, dict[str, str]]:
    per: dict[str, str] = {}
    h = hashlib.sha256()
    for name in module_names:
        rel = _module_relpath(name, root=root)
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
    root = resolve_reviewed_install_root(install_root)
    return module_tree_digest_at(root)


def head_content_binding_digest(reviewed_head: str, content_combined: str) -> str:
    h = hashlib.sha256()
    h.update(reviewed_head.encode("ascii"))
    h.update(b"\0")
    h.update(content_combined.encode("ascii"))
    h.update(b"\0")
    return h.hexdigest()


def trusted_modules_git_head_digest(install_root: Path | None = None) -> str:
    root = resolve_reviewed_install_root(install_root)
    content, _ = trusted_modules_tree_digest(root)
    _root, env_head = _require_launcher_anchors()
    return head_content_binding_digest(env_head, content)


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


def _reject_forged_preloaded_verifier(root: Path, expected_digest: str) -> None:
    name = "tools.self_improvement_v2.trusted_origin"
    rel = _module_relpath(name, root=root)
    disk_path = (root / rel).resolve()
    disk_digest = _sha256_bytes(disk_path.read_bytes())
    if disk_digest != expected_digest:
        raise TrustedOriginError("trusted_origin on-disk digest mismatch vs pin")
    existing = sys.modules.get(name)
    if existing is None:
        return
    path = _module_file(existing)
    if path is None or path != disk_path:
        raise TrustedOriginError("preloaded trusted_origin module origin rejected")
    # Compare the *loaded module file bytes* — forged modules often point __file__
    # at a different path; if __file__ matches disk but code was replaced in-memory,
    # still require disk digest == pin (already checked) and reject if module was
    # injected without coming from that file (no __spec__.origin match).
    origin = getattr(getattr(existing, "__spec__", None), "origin", None)
    if origin and Path(origin).resolve() != disk_path:
        raise TrustedOriginError("preloaded forged trusted_origin rejected")
    # If a different object was stuffed into sys.modules with a fake __file__ that
    # somehow matched, compare sha of that path again.
    loaded_digest = _sha256_bytes(path.read_bytes())
    if loaded_digest != expected_digest:
        raise TrustedOriginError("preloaded forged trusted_origin rejected")


def assert_trusted_code_origin(
    *,
    install_root: Path | None = None,
    module_names: Iterable[str] = TRUSTED_MODULE_NAMES,
    explicit_forbidden_worktrees: Iterable[Path] | None = None,
) -> dict[str, Any]:
    root, env_head = _require_launcher_anchors()
    if install_root is not None:
        reject_worktree_as_import_root(Path(install_root), install_root=root)
        if Path(install_root).expanduser().resolve() != root:
            raise TrustedOriginError(
                "alternate checkout/import root rejected; not the reviewed worker install"
            )
    reject_worktree_as_import_root(root, install_root=root)
    assert_no_worktree_on_sys_path(explicit_forbidden=explicit_forbidden_worktrees)

    pin = json.loads((root / PIN_REL).read_text(encoding="utf-8"))
    if not isinstance(pin, dict):
        raise TrustedOriginError("trusted origin pin must be an object")
    allowed_pin_keys = frozenset({"schema_version", "description", "combined", "modules"})
    unknown = sorted(set(pin) - allowed_pin_keys)
    if unknown:
        raise TrustedOriginError(f"trusted origin pin has unknown keys: {unknown}")
    reviewed_head = env_head

    live_head = _git_head(root)
    names = tuple(dict.fromkeys((*module_names, *TRUSTED_MODULE_NAMES)))

    # N11: authorization line binds the live checkout HEAD — no drift tolerance.
    if env_head != live_head:
        raise TrustedOriginError(
            "reviewed HEAD identity mismatch "
            f"(SRL_REVIEWED_HEAD={env_head} != live HEAD={live_head})"
        )

    from tools.self_improvement_v2.import_closure import assert_pin_covers_static_closure

    try:
        assert_pin_covers_static_closure(root, TRUSTED_MODULE_NAMES)
    except AssertionError as exc:
        raise TrustedOriginError(str(exc)) from exc

    combined, per = module_tree_digest_at(root, TRUSTED_MODULE_NAMES)
    expected_combined = pin.get("combined")
    if not isinstance(expected_combined, str) or expected_combined != combined:
        raise TrustedOriginError(
            "trusted modules tree digest mismatch vs reviewed pin "
            f"(expected {expected_combined}, got {combined})"
        )
    pin_modules = pin.get("modules") or {}
    if not isinstance(pin_modules, dict):
        raise TrustedOriginError("trusted origin pin modules must be an object")

    for name, digest in per.items():
        if pin_modules.get(name) != digest:
            raise TrustedOriginError(f"trusted module digest mismatch for {name}")
        rel = _module_relpath(name, root=root)
        dirty = _raw_git(["diff", "--quiet", "HEAD", "--", rel], cwd=root, check=False)
        if dirty.returncode != 0:
            raise TrustedOriginError(f"trusted module dirty vs HEAD: {rel}")
        blob_digest = _git_blob_digest(root, reviewed_head, rel)
        if blob_digest != digest:
            raise TrustedOriginError(
                f"trusted module git blob at reviewed HEAD mismatches pin/file for {name}"
            )

    _reject_forged_preloaded_verifier(root, per["tools.self_improvement_v2.trusted_origin"])

    origins: dict[str, str] = {}
    for name in names:
        if name not in TRUSTED_MODULE_NAMES:
            continue
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
        path = assert_module_from_worker_install(module, install_root=root)
        rel = _module_relpath(name, root=root)
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
        file_digest = _sha256_bytes(path.read_bytes())
        if file_digest != per[name]:
            raise TrustedOriginError(f"loaded module bytes mismatch pin for {name}")
        origins[name] = str(path)

    # head_content_binding removed: optional-if-present checks decayed silently once
    # the pin stopped carrying the field. HEAD authority is SRL_REVIEWED_HEAD alone.
    binding = head_content_binding_digest(reviewed_head, combined)

    return {
        "install_root": str(root),
        "modules": origins,
        "module_content_sha256": per,
        "trusted_modules_git_head_digest": binding,
        "git_head": live_head,
        "reviewed_git_head": reviewed_head,
        "pin_path": str(PIN_REL).replace("\\", "/"),
    }


def build_content_only_pin(root: Path) -> dict[str, Any]:
    combined, per = module_tree_digest_at(root, TRUSTED_MODULE_NAMES)
    return {
        "schema_version": "2.1.0",
        "description": (
            "Content digests for Self-Improvement V2 modules closed under static AST imports. "
            "Does not cover dynamic importlib/__import__/string-built loaders. "
            "Reviewed HEAD identity is supplied exclusively by SRL_REVIEWED_HEAD."
        ),
        "combined": combined,
        "modules": per,
    }


def gated_assert_trusted_code_origin(
    *,
    install_root: Path | None = None,
    explicit_forbidden_worktrees: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Load verifier from pin-matching on-disk bytes, displacing any preloaded forge."""
    root, _env_head = _require_launcher_anchors()
    pin = json.loads((root / PIN_REL).read_text(encoding="utf-8"))
    pin_modules = pin.get("modules") or {}
    name = "tools.self_improvement_v2.trusted_origin"
    rel = _module_relpath(name, root=root)
    path = (root / rel).resolve()
    digest = _sha256_bytes(path.read_bytes())
    expected = pin_modules.get(name)
    if not isinstance(expected, str) or expected != digest:
        raise TrustedOriginError("trusted_origin digest mismatch before gated load")
    # Always displace sys.modules entry so a forged preload cannot supply assert_*.
    existing = sys.modules.get(name)
    if existing is not None:
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise TrustedOriginError("unable to gated-load trusted_origin")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.assert_trusted_code_origin(
        install_root=install_root,
        explicit_forbidden_worktrees=explicit_forbidden_worktrees,
    )
