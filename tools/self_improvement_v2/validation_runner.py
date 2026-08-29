"""Allowlisted validation profiles with sanitized environments (no os.environ.copy)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.path_policy import get_validation_profile
from tools.self_improvement_v2.schema_loader import worker_package_root
# Static import keeps workflow_validator inside the trusted-origin pin closure.
from tools.self_improvement_v2 import workflow_validator as workflow_validator  # noqa: F401

ALLOWED_EXECUTABLES = frozenset({"python", "python.exe"})

ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "PYTHONUTF8",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPATH",
        "PYTHONNOUSERSITE",
        "COMSPEC",
        "PATHEXT",
    }
)

BLOCKED_ENV_FRAGMENTS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "DATABASE_URL",
    "POSTGRES",
    "AWS_",
    "AZURE_",
    "GCP_",
    "SSH_",
    "GIT_ASKPASS",
    "GIT_CREDENTIAL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


def sanitized_environ(*, pythonpath: str) -> dict[str, str]:
    """Build a minimal environment. Never inherit the full process environment map."""
    env: dict[str, str] = {}
    for key in ALLOWED_ENV_KEYS:
        if key in ("PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE"):
            continue
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PYTHONPATH"] = pythonpath
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    # Defense: drop anything that looks like credentials if somehow added.
    for key in list(env):
        upper = key.upper()
        if any(frag in upper for frag in BLOCKED_ENV_FRAGMENTS):
            del env[key]
    return env


def _bounded_text(data: bytes, limit: int) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text.encode("utf-8")) <= limit:
        return text
    return text.encode("utf-8")[:limit].decode("utf-8", errors="replace") + "\n<truncated>"


def run_validation_profile(
    *,
    policy: dict[str, Any],
    profile_name: str,
    cwd: Path,
    timeout_override: int | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(profile_name, str) or not profile_name:
        raise WorkerError(
            ERROR_CODES["PROHIBITED_VALIDATION_PROFILE"],
            "missing validation profile",
            state="POLICY_REJECTED",
        )
    if any(ch in profile_name for ch in (" ", ";", "|", "&", "$", "`", "\n", "\r")):
        raise WorkerError(
            ERROR_CODES["COMMAND_INJECTION"],
            "validation profile looks like a command",
            state="POLICY_REJECTED",
        )

    profile = get_validation_profile(policy, profile_name)
    commands = profile["commands"]
    timeout = int(timeout_override or profile.get("timeout_seconds") or 60)
    max_output = int(profile.get("max_output_bytes") or 16384)
    worker_root = worker_package_root()
    env = sanitized_environ(pythonpath=str(worker_root))

    results: list[dict[str, Any]] = []
    for index, cmd in enumerate(commands):
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
            raise WorkerError(
                ERROR_CODES["COMMAND_INJECTION"],
                "command is not a fixed argv array",
                state="POLICY_REJECTED",
            )
        exe = Path(cmd[0]).name.lower()
        if exe not in ALLOWED_EXECUTABLES and cmd[0] not in ALLOWED_EXECUTABLES:
            raise WorkerError(
                ERROR_CODES["COMMAND_INJECTION"],
                f"executable not allowlisted: {cmd[0]}",
                state="POLICY_REJECTED",
            )
        argv = list(cmd)
        # Policy argv uses the portable name "python"; resolve to this process's
        # interpreter so host CI without a `python` symlink still runs profiles.
        # -P (PYTHONSAFEPATH) keeps the candidate worktree cwd off sys.path so
        # profile_checks loads from the reviewed PYTHONPATH install only.
        if Path(argv[0]).name.lower() in ALLOWED_EXECUTABLES:
            argv[0] = sys.executable
            flags: list[str] = []
            if "-B" not in argv:
                flags.append("-B")
            if "-P" not in argv:
                flags.append("-P")
            if flags:
                argv[1:1] = flags
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd.resolve()),
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "profile": profile_name,
                    "command_index": index,
                    "status": "TIMEOUT",
                    "exit_code": None,
                    "error_code": ERROR_CODES["VALIDATION_TIMEOUT"],
                    "output_truncated": "",
                }
            )
            raise WorkerError(
                ERROR_CODES["VALIDATION_TIMEOUT"],
                f"validation timed out: {profile_name}",
                state="VALIDATION_FAILED",
            ) from exc

        out = _bounded_text((proc.stdout or b"") + b"\n" + (proc.stderr or b""), max_output)
        status = "PASS" if proc.returncode == 0 else "FAIL"
        error_code = None if status == "PASS" else ERROR_CODES["ACCEPTANCE_FAILED"]
        results.append(
            {
                "profile": profile_name,
                "command_index": index,
                "status": status,
                "exit_code": proc.returncode,
                "error_code": error_code,
                "output_truncated": out[-2048:],
            }
        )
        if status != "PASS":
            raise WorkerError(
                ERROR_CODES["ACCEPTANCE_FAILED"],
                f"validation failed: {profile_name}#{index}",
                state="VALIDATION_FAILED",
            )
    return results
