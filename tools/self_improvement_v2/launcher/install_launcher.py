#!/usr/bin/env python3
"""Install / refresh the out-of-repo SI2 worker launcher (Option A+ root).

Holds (outside the checkout):
  - authorized / reviewed HEAD
  - expected SHA-256 of tools/self_improvement_v2/trusted_origin.py
  - resolved git executable path (audit trail)

Does:
  - refuse if on-disk verifier bytes ≠ expected digest
  - set SRL_REPOSITORY_ROOT + SRL_REVIEWED_HEAD
  - sanitize ambient GIT_* before exec
  - exec the worker

Update the verifier digest in the same operator action that issues the
authorization line for that HEAD — both are attestations about one reviewed tip.

Installation preconditions (accident-class, enforced):
  - repository worktree must be clean
  - --reviewed-head must equal live git HEAD
  - in-repo worker pin must match on-disk trusted-module bytes
  - in-repo launcher pin must equal the installer static import closure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from tools.self_improvement_v2.import_closure import (
    assert_pin_covers_static_closure,
    module_file_relpath,
)
from tools.self_improvement_v2.launcher.paths import (
    ATTESTATION_NAME,
    LAUNCHER_PS1_NAME,
    LAUNCHER_SH_NAME,
    VERIFIER_REL,
    assert_outside_repository,
    default_launcher_dir,
)

WORKER_PIN_REL = Path("specs/self_improvement/v2/trusted_origin_pin.json")
LAUNCHER_PIN_REL = Path("specs/self_improvement/v2/launcher_pin.json")
LAUNCHER_ENTRYPOINT = "tools.self_improvement_v2.launcher.install_launcher"
LAUNCHER_TRUSTED_MODULE_NAMES = (
    "tools.self_improvement_v2",
    "tools.self_improvement_v2.import_closure",
    "tools.self_improvement_v2.launcher",
    "tools.self_improvement_v2.launcher.install_launcher",
    "tools.self_improvement_v2.launcher.paths",
)
WORKER_PIN_ALLOWED_KEYS = frozenset({"schema_version", "description", "combined", "modules"})
LAUNCHER_PIN_ALLOWED_KEYS = frozenset({"schema_version", "description", "combined", "modules", "entrypoint"})

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


def _canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def compute_verifier_digest(repository_root: Path) -> str:
    path = repository_root / VERIFIER_REL
    if not path.is_file():
        raise FileNotFoundError(f"verifier not found: {path}")
    return _canonical_sha256(path.read_bytes())


def resolve_git_executable() -> str:
    found = shutil.which("git")
    if not found:
        raise FileNotFoundError("git executable not found on PATH")
    return str(Path(found).resolve())


def _sanitized_git_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _GIT_ENV_BLOCKLIST_EXACT:
            continue
        if key.startswith("GIT_CONFIG"):
            continue
        out[key] = value
    return out


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    root = root.resolve()
    git_dir = root / ".git"
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", f"--work-tree={root}", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
        env=_sanitized_git_env(),
    )


def _module_relpath(root: Path, module_name: str) -> Path:
    rel = module_file_relpath(root, module_name)
    if rel is None:
        # Fall back so the missing-file error still names a path.
        return Path(*module_name.split(".")).with_suffix(".py")
    return Path(rel)


def _validate_pin_object(pin: dict, *, allowed_keys: frozenset[str], label: str) -> None:
    if not isinstance(pin, dict):
        raise ValueError(f"{label} must be a JSON object")
    unknown = sorted(set(pin) - allowed_keys)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    modules = pin.get("modules")
    if not isinstance(modules, dict) or not modules:
        raise ValueError(f"{label} modules must be a non-empty object")
    combined = pin.get("combined")
    if not isinstance(combined, str) or len(combined) != 64:
        raise ValueError(f"{label} combined digest missing or malformed")


def _module_tree_digest(root: Path, module_names: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    per: dict[str, str] = {}
    h = hashlib.sha256()
    for name in module_names:
        rel = _module_relpath(root, name)
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"pinned module missing: {rel.as_posix()}")
        digest = _canonical_sha256(path.read_bytes())
        per[name] = digest
        h.update(str(rel).replace("\\", "/").encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest(), per


def build_launcher_pin(root: Path) -> dict[str, object]:
    assert_pin_covers_static_closure(
        root, LAUNCHER_TRUSTED_MODULE_NAMES, entrypoint=LAUNCHER_ENTRYPOINT
    )
    combined, per = _module_tree_digest(root, LAUNCHER_TRUSTED_MODULE_NAMES)
    return {
        "schema_version": "1.0.0",
        "description": (
            "Content digests for the SI2 launcher installer closure "
            f"(entrypoint {LAUNCHER_ENTRYPOINT}; closed under static AST imports "
            "including package __init__ and relative imports). Separate from the worker pin."
        ),
        "entrypoint": LAUNCHER_ENTRYPOINT,
        "combined": combined,
        "modules": per,
    }


def _assert_worker_pin_matches_disk(root: Path) -> None:
    pin_path = root / WORKER_PIN_REL
    if not pin_path.is_file():
        raise FileNotFoundError(f"worker pin missing: {WORKER_PIN_REL}")
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    _validate_pin_object(pin, allowed_keys=WORKER_PIN_ALLOWED_KEYS, label="worker pin")
    modules = pin["modules"]
    assert isinstance(modules, dict)
    # Preserve pin key order — combined digest is order-sensitive (matches TRUSTED_MODULE_NAMES).
    names = tuple(modules)
    combined, per = _module_tree_digest(root, names)
    if per != modules:
        raise ValueError("in-repo worker pin does not match on-disk trusted-module bytes")
    if combined != pin["combined"]:
        raise ValueError("in-repo worker pin combined digest does not match on-disk bytes")


def _assert_launcher_pin_matches_disk(root: Path) -> None:
    pin_path = root / LAUNCHER_PIN_REL
    if not pin_path.is_file():
        raise FileNotFoundError(f"launcher pin missing: {LAUNCHER_PIN_REL}")
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    _validate_pin_object(pin, allowed_keys=LAUNCHER_PIN_ALLOWED_KEYS, label="launcher pin")
    assert_pin_covers_static_closure(
        root, LAUNCHER_TRUSTED_MODULE_NAMES, entrypoint=LAUNCHER_ENTRYPOINT
    )
    combined, per = _module_tree_digest(root, LAUNCHER_TRUSTED_MODULE_NAMES)
    if per != pin["modules"] or combined != pin["combined"]:
        raise ValueError("in-repo launcher pin does not match on-disk installer bytes")


def assert_install_preconditions(repository_root: Path, reviewed_head: str) -> str:
    """Refuse dirty / drifted installs. Returns live HEAD (must equal reviewed_head)."""
    root = repository_root.resolve()
    if not (root / ".git").exists():
        raise ValueError("repository root must be a git checkout")
    head_proc = _git(root, "rev-parse", "HEAD")
    if head_proc.returncode != 0:
        raise ValueError(f"git rev-parse HEAD failed: {head_proc.stderr.strip()}")
    live_head = head_proc.stdout.strip().lower()
    if live_head != reviewed_head.strip().lower():
        raise ValueError(
            "reviewed_head must equal live HEAD at install time "
            f"(reviewed={reviewed_head.strip().lower()} live={live_head})"
        )
    dirty = _git(root, "status", "--porcelain")
    if dirty.returncode != 0:
        raise ValueError(f"git status failed: {dirty.stderr.strip()}")
    if dirty.stdout.strip():
        raise ValueError(
            "refuse launcher install from a dirty worktree "
            "(commit or stash before refreshing the trust root)"
        )
    _assert_worker_pin_matches_disk(root)
    _assert_launcher_pin_matches_disk(root)
    return live_head


def _git_env_unset_bash() -> str:
    names = " ".join(sorted(_GIT_ENV_BLOCKLIST_EXACT))
    return f"""# Clear ambient git overrides (accident-class drift vs N11).
unset {names} || true
# Clear GIT_CONFIG* without relying on associative arrays.
while IFS= read -r __srl_git_cfg; do
  [[ -n "$__srl_git_cfg" ]] || continue
  unset "$__srl_git_cfg" || true
done < <(env | awk -F= '/^GIT_CONFIG/ {{print $1}}')
"""


def _git_env_unset_ps1() -> str:
    lines = [
        "# Clear ambient git overrides (accident-class drift vs N11).",
    ]
    for name in sorted(_GIT_ENV_BLOCKLIST_EXACT):
        lines.append(f"Remove-Item Env:{name} -ErrorAction SilentlyContinue")
    lines.append(
        "Get-ChildItem Env:GIT_CONFIG* -ErrorAction SilentlyContinue | "
        "ForEach-Object { Remove-Item -LiteralPath $_.Name -ErrorAction SilentlyContinue }"
    )
    return "\n".join(lines) + "\n"


def _ps1_single_quote(value: str) -> str:
    """Embed value in a PowerShell single-quoted literal ('' escapes ')."""
    return "'" + value.replace("'", "''") + "'"


def _refuse_unsafe_interpolants(*values: str) -> None:
    for value in values:
        if any(ch in value for ch in ("\0", "\n", "\r")):
            raise ValueError("launcher path/digest values must not contain NUL or newlines")


def _ps1_script(
    *,
    repository_root: Path,
    reviewed_head: str,
    expected_digest: str,
    git_executable: str,
) -> str:
    root = str(repository_root.resolve())
    git_exe = str(Path(git_executable).resolve()) if git_executable else git_executable
    _refuse_unsafe_interpolants(root, reviewed_head, expected_digest, git_exe)
    return f"""# Sentinel Research Lab — SI2 worker launcher (OUTSIDE repository; unversioned root)
# Update expected digest in the same operator action as the authorization line.
$ErrorActionPreference = 'Stop'
$ReviewedHead = {_ps1_single_quote(reviewed_head)}
$RepositoryRoot = {_ps1_single_quote(root)}
$ExpectedVerifierDigest = {_ps1_single_quote(expected_digest)}
$GitExecutable = {_ps1_single_quote(git_exe)}
$VerifierRel = 'tools\\self_improvement_v2\\trusted_origin.py'
$VerifierPath = Join-Path $RepositoryRoot $VerifierRel
{_git_env_unset_ps1()}if (-not (Test-Path -LiteralPath $VerifierPath)) {{
  Write-Error "launcher refuse: verifier missing at $VerifierPath"
  exit 2
}}
$sha = [System.Security.Cryptography.SHA256]::Create()
$bytes = [System.IO.File]::ReadAllBytes($VerifierPath)
# Canonicalize CRLF → LF before digest (matches in-repo trusted_origin)
$text = [System.Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"
$canon = [System.Text.Encoding]::UTF8.GetBytes($text)
$actual = ([System.BitConverter]::ToString($sha.ComputeHash($canon)) -replace '-', '').ToLowerInvariant()
if ($actual -ne $ExpectedVerifierDigest) {{
  Write-Error "launcher refuse: trusted_origin digest mismatch expected=$ExpectedVerifierDigest actual=$actual"
  exit 3
}}
$env:SRL_REPOSITORY_ROOT = $RepositoryRoot
$env:SRL_REVIEWED_HEAD = $ReviewedHead
Set-Location -LiteralPath $RepositoryRoot
Write-Host "launcher ok: HEAD=$ReviewedHead verifier=$actual git=$GitExecutable"
& python -m tools.self_improvement_v2.runtime_bridge @args
exit $LASTEXITCODE
"""


def _sh_script(
    *,
    repository_root: Path,
    reviewed_head: str,
    expected_digest: str,
    git_executable: str,
) -> str:
    root = str(repository_root.resolve())
    git_exe = str(Path(git_executable).resolve()) if git_executable else git_executable
    _refuse_unsafe_interpolants(root, reviewed_head, expected_digest, git_exe)
    return f"""#!/usr/bin/env bash
# Sentinel Research Lab — SI2 worker launcher (OUTSIDE repository; unversioned root)
set -euo pipefail
REVIEWED_HEAD={shlex.quote(reviewed_head)}
REPOSITORY_ROOT={shlex.quote(root)}
EXPECTED_VERIFIER_DIGEST={shlex.quote(expected_digest)}
GIT_EXECUTABLE={shlex.quote(git_exe)}
VERIFIER_PATH="$REPOSITORY_ROOT/tools/self_improvement_v2/trusted_origin.py"
{_git_env_unset_bash()}if [[ ! -f "$VERIFIER_PATH" ]]; then
  echo "launcher refuse: verifier missing at $VERIFIER_PATH" >&2
  exit 2
fi
ACTUAL="$(python3 -c 'import hashlib,sys; from pathlib import Path; data=Path(sys.argv[1]).read_bytes().replace(b"\\r\\n", b"\\n"); print(hashlib.sha256(data).hexdigest())' "$VERIFIER_PATH")"
if [[ "$ACTUAL" != "$EXPECTED_VERIFIER_DIGEST" ]]; then
  echo "launcher refuse: trusted_origin digest mismatch expected=$EXPECTED_VERIFIER_DIGEST actual=$ACTUAL" >&2
  exit 3
fi
export SRL_REPOSITORY_ROOT="$REPOSITORY_ROOT"
export SRL_REVIEWED_HEAD="$REVIEWED_HEAD"
cd "$REPOSITORY_ROOT"
echo "launcher ok: HEAD=$REVIEWED_HEAD verifier=$ACTUAL git=$GIT_EXECUTABLE"
exec python3 -m tools.self_improvement_v2.runtime_bridge "$@"
"""


def install_launcher(
    *,
    repository_root: Path,
    reviewed_head: str,
    install_dir: Path | None = None,
    expected_digest: str | None = None,
) -> dict[str, str]:
    root = repository_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"repository root not found: {root}")
    head = reviewed_head.strip().lower()
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("reviewed_head must be a full 40-char lowercase hex SHA")
    assert_install_preconditions(root, head)
    digest = expected_digest or compute_verifier_digest(root)
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("expected_digest must be a 64-char lowercase hex SHA-256")
    # expected_digest override still must match on-disk verifier (no silent backdoor mint).
    on_disk = compute_verifier_digest(root)
    if digest != on_disk:
        raise ValueError(
            "expected_digest must match on-disk trusted_origin.py "
            f"(expected={digest} on_disk={on_disk})"
        )
    git_executable = resolve_git_executable()
    target = (install_dir or default_launcher_dir()).resolve()
    assert_outside_repository(target, root)
    target.mkdir(parents=True, exist_ok=True)

    ps1_path = target / LAUNCHER_PS1_NAME
    sh_path = target / LAUNCHER_SH_NAME
    att_path = target / ATTESTATION_NAME
    ps1_path.write_text(
        _ps1_script(
            repository_root=root,
            reviewed_head=head,
            expected_digest=digest,
            git_executable=git_executable,
        ),
        encoding="utf-8",
        newline="\n",
    )
    sh_path.write_text(
        _sh_script(
            repository_root=root,
            reviewed_head=head,
            expected_digest=digest,
            git_executable=git_executable,
        ),
        encoding="utf-8",
        newline="\n",
    )
    sh_path.chmod(sh_path.stat().st_mode | 0o111)
    launcher_pin_path = root / LAUNCHER_PIN_REL
    launcher_pin_digest = _canonical_sha256(launcher_pin_path.read_bytes())
    attestation = {
        "schema": "srl.launcher_attestation.v1",
        "reviewed_head": head,
        "repository_root": str(root),
        "verifier_relpath": str(VERIFIER_REL).replace("\\", "/"),
        "expected_verifier_digest": digest,
        "git_executable": git_executable,
        "launcher_pin_relpath": str(LAUNCHER_PIN_REL).replace("\\", "/"),
        "launcher_pin_sha256": launcher_pin_digest,
        "note": "Update this attestation in the same operator action as the authorization line.",
    }
    att_path.write_text(json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
    return {
        "install_dir": str(target),
        "launch_worker_ps1": str(ps1_path),
        "launch_worker_sh": str(sh_path),
        "attestation": str(att_path),
        "reviewed_head": head,
        "expected_verifier_digest": digest,
        "git_executable": git_executable,
        "launcher_pin_sha256": launcher_pin_digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        default=os.environ.get("SRL_REPOSITORY_ROOT") or str(Path.cwd()),
        help="Reviewed git checkout (absolute recommended)",
    )
    parser.add_argument(
        "--reviewed-head",
        required=True,
        help="Full 40-char SHA; must equal live HEAD; update together with the authorization line",
    )
    parser.add_argument(
        "--install-dir",
        default=None,
        help="Override out-of-repo install dir (default: LOCALAPPDATA or XDG data home)",
    )
    parser.add_argument(
        "--expected-digest",
        default=None,
        help="Optional override; must still match on-disk trusted_origin.py",
    )
    parser.add_argument(
        "--write-launcher-pin",
        action="store_true",
        help="Regenerate specs/self_improvement/v2/launcher_pin.json and exit",
    )
    args = parser.parse_args(argv)
    root = Path(args.repository_root)
    if args.write_launcher_pin:
        pin = build_launcher_pin(root)
        path = root.resolve() / LAUNCHER_PIN_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"wrote": str(path), "combined": pin["combined"]}, indent=2))
        return 0
    result = install_launcher(
        repository_root=root,
        reviewed_head=args.reviewed_head,
        install_dir=Path(args.install_dir) if args.install_dir else None,
        expected_digest=args.expected_digest,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
