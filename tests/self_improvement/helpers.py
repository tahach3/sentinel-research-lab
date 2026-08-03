"""Helpers for self-improvement tests — temp repos only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any

REAL_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Test")
    env.setdefault("GIT_AUTHOR_EMAIL", "test@local")
    env.setdefault("GIT_COMMITTER_NAME", "Test")
    env.setdefault("GIT_COMMITTER_EMAIL", "test@local")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        shell=False,
        env=env,
    )


def init_temp_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    run(["git", "config", "user.email", "test@local"], path)
    run(["git", "config", "user.name", "Test"], path)
    # Keep LF bytes stable for postimage hashing across platforms.
    run(["git", "config", "core.autocrlf", "false"], path)
    run(["git", "config", "core.eol", "lf"], path)
    (path / "docs").mkdir(parents=True, exist_ok=True)
    (path / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "README.md").write_text("# Temp docs\n", encoding="utf-8")
    (path / "tests" / "fixtures" / ".gitkeep").write_text("", encoding="utf-8")
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "baseline"], path)
    head = run(["git", "rev-parse", "HEAD"], path).stdout.strip()
    return head


def create_file_diff(path: str, content: str) -> str:
    lines = content.splitlines()
    body = "\n".join("+" + line for line in lines)
    if not body.endswith("\n") and content.endswith("\n"):
        pass
    plus_count = len(lines) if lines else 0
    if content.endswith("\n") and lines:
        # unified diff counts newline-terminated lines
        pass
    hunk = f"@@ -0,0 +1,{plus_count} @@\n{body}\n"
    if not content:
        hunk = "@@ -0,0 +0,0 @@\n"
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"{hunk}"
    )


def modify_file_diff(path: str, old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    minus = "\n".join("-" + line for line in old_lines)
    plus = "\n".join("+" + line for line in new_lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@\n"
        f"{minus}\n"
        f"{plus}\n"
    )


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_pilot_proposal(repo: Path, baseline: str) -> dict[str, Any]:
    doc = "# Self-Improvement Pilot Note\n\nCreated by offline pilot.\n"
    fixture = "pilot_marker=1\n"
    doc_diff = create_file_diff("docs/SELF_IMPROVEMENT_NOTE.md", doc)
    fix_diff = create_file_diff("tests/fixtures/pilot_marker.txt", fixture)
    proposal = load_fixture("proposal.json")
    proposal["baseline_sha"] = baseline
    proposal["implementer_id"] = "srl-implementer-agent"
    proposal["repair_attempt"] = 0
    proposal["validation_profile"] = "DOCUMENTATION_ONLY"
    proposal["patches"] = [
        {
            "path": "docs/SELF_IMPROVEMENT_NOTE.md",
            "operation": "CREATE",
            "unified_diff": doc_diff,
            "expected_preimage_sha256": "",
            "expected_postimage_sha256": sha256_text(doc),
        },
        {
            "path": "tests/fixtures/pilot_marker.txt",
            "operation": "CREATE",
            "unified_diff": fix_diff,
            "expected_preimage_sha256": "",
            "expected_postimage_sha256": sha256_text(fixture),
        },
    ]
    return proposal


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
