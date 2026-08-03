"""Allowlisted validation profile execution with confined subprocesses."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError
from tools.self_improvement.policy import get_validation_profile
from tools.self_improvement.schema_loader import worker_package_root

# Profiles may only use these executables.
ALLOWED_EXECUTABLES = frozenset({"python", "python.exe"})


def _bounded_text(data: bytes, limit: int) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text.encode("utf-8")) <= limit:
        return text
    # Truncate by characters roughly within byte bound.
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
    # Reject anything that looks like shell / injection via profile field.
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
        # No shell metacharacter join — pass argv list only.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONPATH": str(worker_root),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "SRL_SELF_IMPROVEMENT_WORKER_ROOT": str(worker_root),
            "SRL_SELF_IMPROVEMENT_TARGET_ROOT": str(cwd.resolve()),
        }
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd.resolve()),
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
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
            ) from None

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
