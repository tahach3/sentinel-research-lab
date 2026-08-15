#!/usr/bin/env python3
"""Install / refresh the out-of-repo SI2 worker launcher (Option A+ root).

Holds (outside the checkout):
  - authorized / reviewed HEAD
  - expected SHA-256 of tools/self_improvement_v2/trusted_origin.py

Does:
  - refuse if on-disk verifier bytes ≠ expected digest
  - set SRL_REPOSITORY_ROOT + SRL_REVIEWED_HEAD
  - exec the worker

Update the verifier digest in the same operator action that issues the
authorization line for that HEAD — both are attestations about one reviewed tip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from tools.self_improvement_v2.launcher.paths import (
    ATTESTATION_NAME,
    LAUNCHER_PS1_NAME,
    LAUNCHER_SH_NAME,
    VERIFIER_REL,
    assert_outside_repository,
    default_launcher_dir,
)


def _canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def compute_verifier_digest(repository_root: Path) -> str:
    path = repository_root / VERIFIER_REL
    if not path.is_file():
        raise FileNotFoundError(f"verifier not found: {path}")
    return _canonical_sha256(path.read_bytes())


def _ps1_script(
    *,
    repository_root: Path,
    reviewed_head: str,
    expected_digest: str,
) -> str:
    root = str(repository_root.resolve())
    return f"""# Sentinel Research Lab — SI2 worker launcher (OUTSIDE repository; unversioned root)
# Update expected digest in the same operator action as the authorization line.
$ErrorActionPreference = 'Stop'
$ReviewedHead = '{reviewed_head}'
$RepositoryRoot = '{root}'
$ExpectedVerifierDigest = '{expected_digest}'
$VerifierRel = 'tools\\self_improvement_v2\\trusted_origin.py'
$VerifierPath = Join-Path $RepositoryRoot $VerifierRel
if (-not (Test-Path -LiteralPath $VerifierPath)) {{
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
Write-Host "launcher ok: HEAD=$ReviewedHead verifier=$actual"
& python -m tools.self_improvement_v2.runtime_bridge @args
exit $LASTEXITCODE
"""


def _sh_script(
    *,
    repository_root: Path,
    reviewed_head: str,
    expected_digest: str,
) -> str:
    root = str(repository_root.resolve())
    return f"""#!/usr/bin/env bash
# Sentinel Research Lab — SI2 worker launcher (OUTSIDE repository; unversioned root)
set -euo pipefail
REVIEWED_HEAD='{reviewed_head}'
REPOSITORY_ROOT='{root}'
EXPECTED_VERIFIER_DIGEST='{expected_digest}'
VERIFIER_PATH="$REPOSITORY_ROOT/tools/self_improvement_v2/trusted_origin.py"
if [[ ! -f "$VERIFIER_PATH" ]]; then
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
echo "launcher ok: HEAD=$REVIEWED_HEAD verifier=$ACTUAL"
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
    digest = expected_digest or compute_verifier_digest(root)
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("expected_digest must be a 64-char lowercase hex SHA-256")
    target = (install_dir or default_launcher_dir()).resolve()
    assert_outside_repository(target, root)
    target.mkdir(parents=True, exist_ok=True)

    ps1_path = target / LAUNCHER_PS1_NAME
    sh_path = target / LAUNCHER_SH_NAME
    att_path = target / ATTESTATION_NAME
    ps1_path.write_text(
        _ps1_script(repository_root=root, reviewed_head=head, expected_digest=digest),
        encoding="utf-8",
        newline="\n",
    )
    sh_path.write_text(
        _sh_script(repository_root=root, reviewed_head=head, expected_digest=digest),
        encoding="utf-8",
        newline="\n",
    )
    sh_path.chmod(sh_path.stat().st_mode | 0o111)
    attestation = {
        "schema": "srl.launcher_attestation.v1",
        "reviewed_head": head,
        "repository_root": str(root),
        "verifier_relpath": str(VERIFIER_REL).replace("\\", "/"),
        "expected_verifier_digest": digest,
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
        help="Full 40-char SHA; update together with the operator authorization line",
    )
    parser.add_argument(
        "--install-dir",
        default=None,
        help="Override out-of-repo install dir (default: LOCALAPPDATA or XDG data home)",
    )
    parser.add_argument(
        "--expected-digest",
        default=None,
        help="Optional override; default = SHA-256 of trusted_origin.py at repository-root",
    )
    args = parser.parse_args(argv)
    result = install_launcher(
        repository_root=Path(args.repository_root),
        reviewed_head=args.reviewed_head,
        install_dir=Path(args.install_dir) if args.install_dir else None,
        expected_digest=args.expected_digest,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
