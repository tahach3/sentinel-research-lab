"""Offline system validator for Self-Improvement Loop V1."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.self_improvement.policy import load_policy
from tools.self_improvement.schema_loader import SCHEMA_FILES, load_schema, specs_dir, worker_package_root
from tools.self_improvement.workflow_validator import validate_workflow

REQUIRED_FILES = [
    "docs/SELF_IMPROVEMENT_LOOP_V1.md",
    "specs/self_improvement/v1/improvement_candidate.schema.json",
    "specs/self_improvement/v1/implementation_proposal.schema.json",
    "specs/self_improvement/v1/execution_result.schema.json",
    "specs/self_improvement/v1/review_result.schema.json",
    "specs/self_improvement/v1/learning_record.schema.json",
    "specs/self_improvement/v1/policy.json",
    "tools/self_improvement/__init__.py",
    "tools/self_improvement/models.py",
    "tools/self_improvement/schema_loader.py",
    "tools/self_improvement/policy.py",
    "tools/self_improvement/git_worker.py",
    "tools/self_improvement/patch_validator.py",
    "tools/self_improvement/validation_runner.py",
    "tools/self_improvement/review_gate.py",
    "tools/self_improvement/experience_store.py",
    "tools/self_improvement/cli.py",
    "tools/self_improvement/workflow_validator.py",
    "tools/self_improvement/profile_checks.py",
    "tools/self_improvement/validate_system.py",
    "workflows/design/self_improvement_loop_v1.json",
    "tests/self_improvement/test_schemas.py",
    "tests/self_improvement/test_policy.py",
    "tests/self_improvement/test_patch_validator.py",
    "tests/self_improvement/test_git_worker.py",
    "tests/self_improvement/test_validation_runner.py",
    "tests/self_improvement/test_review_gate.py",
    "tests/self_improvement/test_experience_store.py",
    "tests/self_improvement/test_workflow_validator.py",
    "tests/self_improvement/test_end_to_end_pilot.py",
    "tests/self_improvement/fixtures/candidate.json",
    "tests/self_improvement/fixtures/proposal.json",
    "tests/self_improvement/fixtures/review_pass.json",
]

FORBIDDEN_IMPORT_ROOTS = ("requests", "httpx", "docker", "psycopg", "openai", "anthropic")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SystemValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.errors: list[dict[str, str]] = []
        self.checks: dict[str, Any] = {}

    def fail(self, code: str, message: str) -> None:
        self.errors.append({"code": code, "message": message})

    def path(self, rel: str) -> Path:
        return self.root / rel

    def check_files(self) -> None:
        missing = [rel for rel in REQUIRED_FILES if not self.path(rel).is_file()]
        self.checks["required_files_missing"] = missing
        for rel in missing:
            self.fail("MISSING_FILE", rel)

    def check_schemas(self) -> None:
        ok = 0
        for name in SCHEMA_FILES:
            schema = load_schema(name, root=self.root)
            Draft202012Validator.check_schema(schema)
            if schema.get("additionalProperties") is not False:
                self.fail("SCHEMA_LOOSE", f"{name} additionalProperties not false")
            else:
                ok += 1
        self.checks["schemas_strict"] = ok

    def check_policy(self) -> None:
        policy = load_policy(self.root)
        lane = policy["autonomous_lane"]
        self.checks["allowed_paths"] = lane["allowed_paths"]
        self.checks["forbidden_paths"] = lane["forbidden_paths"]
        self.checks["maximum_files"] = lane["limits"]["maximum_changed_files"]
        self.checks["maximum_diff"] = lane["limits"]["maximum_total_added_and_removed_lines"]
        self.checks["repair_attempts"] = lane["limits"]["maximum_autonomous_repair_attempts"]
        self.checks["deletion"] = lane["limits"]["deletion_allowed"]
        self.checks["push"] = lane["limits"]["push_allowed"]
        self.checks["merge"] = lane["limits"]["merge_allowed"]
        profiles = policy.get("validation_profiles") or {}
        for name, profile in profiles.items():
            for cmd in profile.get("commands") or []:
                if not isinstance(cmd, list):
                    self.fail("PROFILE_UNSAFE", f"{name} command not argv array")

    def check_workflow(self) -> None:
        report = validate_workflow(self.root, self.path("workflows/design/self_improvement_loop_v1.json"))
        self.checks["workflow_status"] = report["status"]
        if report["status"] != "PASS":
            for err in report["errors"]:
                self.fail(err["code"], err["message"])

    def check_worker_ast(self) -> None:
        package = self.path("tools/self_improvement")
        shell_true = 0
        eval_calls = 0
        for py in sorted(package.glob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "eval":
                        eval_calls += 1
                        self.fail("EVAL_USED", py.name)
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            shell_true += 1
                            self.fail("SHELL_TRUE", py.name)
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root in FORBIDDEN_IMPORT_ROOTS:
                            self.fail("FORBIDDEN_IMPORT", f"{py.name}:{root}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        self.fail("FORBIDDEN_IMPORT", f"{py.name}:{root}")
        self.checks["shell_true"] = shell_true
        self.checks["eval_calls"] = eval_calls

    def check_review_independence(self) -> None:
        text = self.path("tools/self_improvement/review_gate.py").read_text(encoding="utf-8")
        if "SELF_REVIEW" not in text or "independent_from_implementer" not in text:
            self.fail("REVIEW_GATE", "review independence checks missing")
        cli = self.path("tools/self_improvement/cli.py").read_text(encoding="utf-8")
        if "assert_review_pass" not in cli:
            self.fail("REVIEW_GATE", "finalize does not use review gate")
        # Worker must not auto-fabricate PASS reviews.
        if re.search(r"verdict\"\s*:\s*\"PASS\"", cli):
            self.fail("SELF_PASS", "cli fabricates PASS review")

    def check_experience_store(self) -> None:
        text = self.path("tools/self_improvement/experience_store.py").read_text(encoding="utf-8")
        for table in (
            "improvement_candidates",
            "implementation_proposals",
            "execution_runs",
            "validation_results",
            "review_results",
            "learning_records",
            "state_transitions",
        ):
            if table not in text:
                self.fail("STORE_SCHEMA", f"missing table {table}")
        if "PRAGMA foreign_keys = ON" not in text:
            self.fail("STORE_SCHEMA", "foreign keys not enabled")

    def check_pilot_fixtures(self) -> None:
        for name in ("candidate.json", "proposal.json", "review_pass.json"):
            path = self.path(f"tests/self_improvement/fixtures/{name}")
            json.loads(path.read_text(encoding="utf-8"))
        self.checks["pilot_fixtures"] = 3

    def check_hygiene(self) -> None:
        # No committed sqlite DBs under tools/self_improvement or specs.
        bad = list(self.root.glob("**/*.sqlite")) + list(self.root.glob("**/*.db"))
        tracked_bad = [p for p in bad if "self_improvement" in str(p)]
        self.checks["sqlite_artifacts"] = len(tracked_bad)
        for p in tracked_bad:
            self.fail("DB_COMMITTED", str(p.relative_to(self.root)).replace("\\", "/"))

    def run(self) -> dict[str, Any]:
        self.check_files()
        if not self.errors:
            self.check_schemas()
            self.check_policy()
            self.check_workflow()
            self.check_worker_ast()
            self.check_review_independence()
            self.check_experience_store()
            self.check_pilot_fixtures()
            self.check_hygiene()
        status = "PASS" if not self.errors else "FAIL"
        report = {
            "validator": "self_improvement_validate_system",
            "schema_version": "1.0.0",
            "final_status": status,
            "checks": self.checks,
            "errors": self.errors,
        }
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Self-Improvement Loop V1 system")
    parser.add_argument("--root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        return 2
    try:
        report = SystemValidator(root).run()
    except Exception as exc:  # usage/environment failures
        Path(args.report).write_text(
            json.dumps({"final_status": "FAIL", "errors": [{"code": "ENV", "message": str(exc)}]}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 2
    # Deterministic JSON: sorted keys, no timestamps/absolute paths.
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    report_path = Path(args.report)
    report_path.write_text(text, encoding="utf-8")
    print(json.dumps({"final_status": report["final_status"], "error_count": len(report["errors"])}, sort_keys=True))
    return 0 if report["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
