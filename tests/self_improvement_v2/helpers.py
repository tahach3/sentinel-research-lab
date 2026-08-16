"""Helpers for Self-Improvement Loop V2 tests — temp repos only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

REAL_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "2.0.0"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@local",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@local",
    }
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        shell=False,
        env=env,
    )


def init_temp_repo(path: Path, *, include_worker_package: bool = False) -> str:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    run(["git", "config", "user.email", "test@local"], path)
    run(["git", "config", "user.name", "Test"], path)
    run(["git", "config", "core.autocrlf", "false"], path)
    run(["git", "config", "core.eol", "lf"], path)
    (path / "docs").mkdir(parents=True, exist_ok=True)
    (path / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "README.md").write_text("# Temp docs\n", encoding="utf-8")
    (path / "tests" / "fixtures" / ".gitkeep").write_text("", encoding="utf-8")
    # Copy V2 specs so policy/schema resolve from temp root
    dst = path / "specs" / "self_improvement" / "v2"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REAL_ROOT / "specs" / "self_improvement" / "v2", dst)
    if include_worker_package:
        # Full SI2 package + pins so SRL_REPOSITORY_ROOT can equal the temp root
        # under R4 without splitting trust from policy evaluation.
        tools_dst = path / "tools"
        tools_dst.mkdir(parents=True, exist_ok=True)
        (tools_dst / "__init__.py").write_text("", encoding="utf-8")
        shutil.copytree(
            REAL_ROOT / "tools" / "self_improvement_v2",
            tools_dst / "self_improvement_v2",
            dirs_exist_ok=True,
        )
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", "baseline"], path)
    return run(["git", "rev-parse", "HEAD"], path).stdout.strip()


def create_file_diff(path: str, content: str) -> str:
    lines = content.splitlines()
    body = "\n".join("+" + line for line in lines)
    plus_count = len(lines) if lines else 0
    hunk = f"@@ -0,0 +1,{plus_count} @@\n{body}\n"
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"{hunk}"
    )


def build_proposal(
    baseline: str,
    *,
    proposal_id: str = "prop-v2-1",
    candidate_id: str = "cand-v2-1",
    path: str = "docs/SELF_IMPROVEMENT_V2_NOTE.md",
    body: str = "# Self-Improvement V2 Pilot Note\n\nOffline.\n",
    risk_level: str = "LOW",
    repair_attempt: int = 0,
    parent_proposal_id: str | None = None,
    allowed_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "candidate_id": candidate_id,
        "repository_id": "sentinel-research-lab",
        "baseline_sha": baseline,
        "objective": "offline v2 pilot",
        "evidence_refs": ["fixture"],
        "allowed_paths": allowed_paths or ["docs/**", "tests/**"],
        "forbidden_paths": [".env", ".git/**"],
        "patches": [
            {
                "path": path,
                "operation": "CREATE",
                "unified_diff": create_file_diff(path, body),
                "expected_preimage_sha256": "",
                "expected_postimage_sha256": sha256_text(body),
            }
        ],
        "validation_profile": "DOCUMENTATION_ONLY",
        "acceptance_criteria": ["docs readable"],
        "risk_level": risk_level,
        "rollback_strategy": "delete candidate branch",
        "repair_attempt": repair_attempt,
        "parent_proposal_id": parent_proposal_id,
        "implementer_id": "srl-implementer-agent",
        "maximum_changed_files": 8,
        "maximum_total_added_and_removed_lines": 500,
    }


def build_pass_review(bundle: dict[str, Any], proposal: dict[str, Any], review_id: str = "rev-v2-1") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_id": review_id,
        "reviewer_id": "srl-independent-reviewer-agent",
        "implementer_id": proposal.get("implementer_id") or "srl-implementer-agent",
        "independent_from_implementer": True,
        "proposal_id": bundle["proposal_id"],
        "proposal_sha256": bundle["proposal_sha256"],
        "execution_id": bundle["execution_id"],
        "execution_result_sha256": bundle["execution_result_sha256"],
        "actual_diff_sha256": bundle["actual_diff_sha256"],
        "worktree_tree_sha": bundle["worktree_tree_sha"],
        "validation_results_sha256": bundle["validation_results_sha256"],
        "contract_alignment": "PASS",
        "allowed_path_compliance": "PASS",
        "acceptance_results": "PASS",
        "security_findings": [],
        "architecture_findings": [],
        "verdict": "PASS",
        "repair_instructions": [],
        "declared_risk": bundle.get("declared_risk", proposal.get("risk_level", "LOW")),
        "computed_risk_pre": bundle.get("computed_risk_pre", "LOW"),
        "effective_risk_pre": bundle.get("effective_risk_pre", "LOW"),
        "computed_risk_post": bundle.get("computed_risk_post", "LOW"),
        "effective_risk_post": bundle.get("effective_risk_post", "LOW"),
        "risk_reason_codes_pre": list(bundle.get("risk_reason_codes_pre") or []),
        "risk_reason_codes_post": list(bundle.get("risk_reason_codes_post") or []),
        "policy_sha256": bundle.get("policy_sha256", "0" * 64),
        "risk_classifier_version": bundle.get("risk_classifier_version", "2.1.0"),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
