"""Offline system validator with real adversarial probes for Self-Improvement Loop V2."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.finalizer import finalize
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.path_policy import assert_path_allowed, load_policy
from tools.self_improvement_v2.review_gate import assert_review_bound
from tools.self_improvement_v2.schema_loader import SCHEMA_FILES, load_schema, worker_package_root
from tools.self_improvement_v2.workflow_validator import validate_workflow


def _proof(
    *,
    probe_id: str,
    corruption_applied: str,
    validation_stage_executed: str,
    expected_error_code: str,
    actual_error_code: str | None,
    detected: bool,
    unrelated_failure: bool = False,
) -> dict[str, Any]:
    return {
        "probe_id": probe_id,
        "corruption_applied": corruption_applied,
        "validation_stage_executed": validation_stage_executed,
        "expected_error_code": expected_error_code,
        "actual_error_code": actual_error_code,
        "detected": detected,
        "unrelated_failure": unrelated_failure,
    }

REQUIRED_FILES = [
    "docs/SELF_IMPROVEMENT_LOOP_V2.md",
    "specs/self_improvement/v2/improvement_candidate.schema.json",
    "specs/self_improvement/v2/implementation_proposal.schema.json",
    "specs/self_improvement/v2/execution_bundle.schema.json",
    "specs/self_improvement/v2/review_result.schema.json",
    "specs/self_improvement/v2/finalization_result.schema.json",
    "specs/self_improvement/v2/learning_record.schema.json",
    "specs/self_improvement/v2/policy.json",
    "tools/self_improvement_v2/canonical.py",
    "tools/self_improvement_v2/path_policy.py",
    "tools/self_improvement_v2/patch_parser.py",
    "tools/self_improvement_v2/patch_validator.py",
    "tools/self_improvement_v2/experience_store.py",
    "tools/self_improvement_v2/git_worker.py",
    "tools/self_improvement_v2/review_gate.py",
    "tools/self_improvement_v2/finalizer.py",
    "tools/self_improvement_v2/validation_runner.py",
    "tools/self_improvement_v2/validate_system.py",
    "workflows/design/self_improvement_loop_v2.json",
]

FORBIDDEN_IMPORT_ROOTS = ("requests", "httpx", "docker", "psycopg", "openai", "anthropic")

NESTED_PATH_PROBES = [
    "docs/.env",
    "docs/.env.local",
    "tests/.env",
    "tests/fixtures/.git/HEAD",
    "docs/.git/config",
    "tools/self_improvement_v2/credentials/token.json",
    "docs/secrets/private.pem",
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_temp_repo(path: Path) -> str:
    import os
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "GIT_AUTHOR_NAME": "Probe",
        "GIT_AUTHOR_EMAIL": "probe@invalid",
        "GIT_COMMITTER_NAME": "Probe",
        "GIT_COMMITTER_EMAIL": "probe@invalid",
    }

    def run(args: list[str]) -> str:
        proc = subprocess.run(
            args,
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
            shell=False,
            env=env,
        )
        return proc.stdout.strip()

    run(["git", "init"])
    run(["git", "config", "user.email", "probe@invalid"])
    run(["git", "config", "user.name", "Probe"])
    run(["git", "config", "core.autocrlf", "false"])
    run(["git", "config", "core.eol", "lf"])
    (path / "docs").mkdir(parents=True, exist_ok=True)
    (path / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "README.md").write_text("# probe\n", encoding="utf-8")
    (path / "tests" / "fixtures" / ".gitkeep").write_text("", encoding="utf-8")
    # Specs copied by caller after init; commit only baseline tree here.
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "baseline"])
    return run(["git", "rev-parse", "HEAD"])


def _create_diff(path: str, content: str) -> str:
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


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_proposal(baseline: str, doc_path: str = "docs/SI2_NOTE.md", body: str = "# ok\n") -> dict[str, Any]:
    diff = _create_diff(doc_path, body)
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": "prop-probe-1",
        "candidate_id": "cand-probe-1",
        "repository_id": "sentinel-research-lab",
        "baseline_sha": baseline,
        "objective": "offline probe",
        "evidence_refs": ["probe"],
        "allowed_paths": ["docs/**", "tests/**"],
        "forbidden_paths": [],
        "patches": [
            {
                "path": doc_path,
                "operation": "CREATE",
                "unified_diff": diff,
                "expected_preimage_sha256": "",
                "expected_postimage_sha256": _sha_text(body),
            }
        ],
        "validation_profile": "DOCUMENTATION_ONLY",
        "acceptance_criteria": ["docs utf-8"],
        "risk_level": "LOW",
        "rollback_strategy": "delete candidate branch",
        "repair_attempt": 0,
        "parent_proposal_id": None,
        "implementer_id": "srl-implementer-agent",
    }


class SystemValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.errors: list[dict[str, str]] = []
        self.checks: dict[str, Any] = {}
        self.probe_results: dict[str, Any] = {}

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

    def check_worker_ast(self) -> None:
        package = self.path("tools/self_improvement_v2")
        shell_true = 0
        env_copy = 0
        for py in sorted(package.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "eval":
                        self.fail("EVAL_USED", py.name)
                    # Detect os.environ.copy() via AST, ignore docstrings.
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "copy":
                        val = node.func.value
                        if (
                            isinstance(val, ast.Attribute)
                            and val.attr == "environ"
                            and isinstance(val.value, ast.Name)
                            and val.value.id == "os"
                        ):
                            env_copy += 1
                            self.fail("ENV_COPY", py.name)
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
        self.checks["env_copy"] = env_copy

    def check_workflow(self) -> None:
        report = validate_workflow(self.root, self.path("workflows/design/self_improvement_loop_v2.json"))
        self.checks["workflow_status"] = report["status"]
        if report["status"] != "PASS":
            for err in report["errors"]:
                self.fail(err["code"], err["message"])

    def probe_workflow_graph_mutations(self) -> None:
        """Independent structural mutations — not source-text / marker searches."""
        wf_path = self.path("workflows/design/self_improvement_loop_v2.json")
        base = json.loads(wf_path.read_text(encoding="utf-8"))
        proofs: list[dict[str, Any]] = []
        tmp = Path(tempfile.mkdtemp(prefix="si2-wf-probe-"))
        try:
            mutations: list[tuple[str, str, str, Any]] = []

            def add(probe_id: str, expected: str, corruption: str, mutator: Any) -> None:
                mutations.append((probe_id, expected, corruption, mutator))

            def m_worker(data: dict) -> None:
                data["connections"]["Detached Worker Execute"]["main"] = [
                    data["connections"]["Detached Worker Execute"]["main"][0]
                ]

            def m_review(data: dict) -> None:
                data["connections"]["Independent Review Bind"]["main"] = [
                    data["connections"]["Independent Review Bind"]["main"][0]
                ]

            def m_high(data: dict) -> None:
                data["connections"]["Risk Classification"]["main"][2] = [
                    {"node": "LOW Auto-Authorize", "type": "main", "index": 0}
                ]

            def m_prohibited(data: dict) -> None:
                data["connections"]["Risk Classification"]["main"][3] = [
                    {"node": "Detached Worker Execute", "type": "main", "index": 0}
                ]

            def m_binding(data: dict) -> None:
                data["connections"]["Failure Router"]["main"][3] = []

            def m_marker(data: dict) -> None:
                for node in data["nodes"]:
                    if node.get("name") == "Failure Router":
                        node["type"] = "n8n-nodes-base.code"
                        node["parameters"] = {
                            "jsCode": (
                                "// failure routes: POLICY_REJECTED VALIDATION_FAILED "
                                "REVIEW_FAILED CONTENT_BINDING_MISMATCH\nreturn items;"
                            )
                        }
                data["connections"]["Failure Router"] = {"main": [[]]}

            add("wf-remove-worker-failure", ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "remove worker failure edge", m_worker)
            add("wf-remove-review-failure", ERROR_CODES["SI2-WF-MISSING-FAILURE-EDGE"], "remove review failure edge", m_review)
            add("wf-high-autoauth", ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"], "route HIGH to AUTO_AUTHORIZED", m_high)
            add("wf-prohibited-worker", ERROR_CODES["SI2-WF-INVALID-RISK-ROUTE"], "route PROHIBITED to worker", m_prohibited)
            add(
                "wf-remove-binding-route",
                ERROR_CODES["SI2-WF-DISCONNECTED-FAILURE-STATE"],
                "remove CONTENT_BINDING_MISMATCH route",
                m_binding,
            )
            add(
                "wf-marker-only-router",
                ERROR_CODES["SI2-WF-MARKER-NOT-ROUTE"],
                "replace Failure Router with disconnected marker text",
                m_marker,
            )

            for probe_id, expected, corruption, mutator in mutations:
                mutated = copy.deepcopy(base)
                mutator(mutated)
                probe_file = tmp / f"{probe_id}.json"
                probe_file.write_text(json.dumps(mutated), encoding="utf-8")
                report = validate_workflow(self.root, probe_file)
                codes = [e["code"] for e in report.get("errors") or []]
                actual = expected if expected in codes else (codes[0] if codes else None)
                detected = expected in codes
                unrelated = bool(codes) and not detected
                proofs.append(
                    _proof(
                        probe_id=probe_id,
                        corruption_applied=corruption,
                        validation_stage_executed="workflow_validator",
                        expected_error_code=expected,
                        actual_error_code=actual,
                        detected=detected,
                        unrelated_failure=unrelated,
                    )
                )
                if not detected:
                    self.fail(expected, f"workflow probe {probe_id} not detected; codes={codes}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.probe_results["workflow_graph_mutations"] = proofs

    def probe_nested_paths(self) -> None:
        policy = load_policy(self.root)
        rejected = []
        for probe in NESTED_PATH_PROBES:
            try:
                assert_path_allowed(probe, policy, {"allowed_paths": ["docs/**", "tests/**", "tools/self_improvement_v2/**"], "forbidden_paths": []})
                self.fail("PATH_PROBE_PASSED", probe)
            except WorkerError as exc:
                rejected.append({"path": probe, "code": exc.code})
        self.probe_results["nested_paths"] = rejected
        if len(rejected) != len(NESTED_PATH_PROBES):
            self.fail("PATH_PROBES", "not all nested path probes rejected")

    def probe_immutability_and_binding(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="si2-validate-"))
        try:
            repo = tmp / "repo"
            baseline = _init_temp_repo(repo)
            specs_src = self.root / "specs" / "self_improvement" / "v2"
            specs_dst = repo / "specs" / "self_improvement" / "v2"
            specs_dst.parent.mkdir(parents=True, exist_ok=True)
            if specs_dst.exists():
                shutil.rmtree(specs_dst)
            shutil.copytree(specs_src, specs_dst)
            # Specs are untracked in the probe repo; keep them out of porcelain by ignoring.
            (repo / ".git" / "info" / "exclude").write_text("specs/\n", encoding="utf-8")
            db = tmp / "state.sqlite"
            proposal = _build_proposal(baseline)

            store = ExperienceStore(db)
            bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)

            # Immutability: alter proposal same ID
            altered = dict(proposal)
            altered_patches = list(proposal["patches"])
            pwned_body = "PWNED\n"
            altered["patches"] = [
                {
                    "path": "docs/PWNED.md",
                    "operation": "CREATE",
                    "unified_diff": _create_diff("docs/PWNED.md", pwned_body),
                    "expected_preimage_sha256": "",
                    "expected_postimage_sha256": _sha_text(pwned_body),
                }
            ]
            try:
                store.insert_proposal(altered, policy_sha256=bundle["policy_sha256"])
                self.fail("IMMUTABILITY_PROBE", "altered proposal accepted")
            except WorkerError as exc:
                if exc.code != ERROR_CODES["SI2-STORE-IMMUTABILITY"]:
                    self.fail("IMMUTABILITY_PROBE", f"wrong code {exc.code}")
                self.probe_results["proposal_immutability"] = exc.code

            # Valid review
            review = {
                "schema_version": SCHEMA_VERSION,
                "review_id": "rev-probe-1",
                "reviewer_id": "srl-independent-reviewer-agent",
                "implementer_id": "srl-implementer-agent",
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
            }
            assert_review_bound(review, proposal=proposal, bundle=bundle, root=self.root)
            store.insert_review(review)

            # Stale review / wrong hash must fail independently of review_gate source-text
            stale = dict(review)
            stale["review_id"] = "rev-stale"
            stale["proposal_sha256"] = "a" * 64
            try:
                assert_review_bound(stale, proposal=proposal, bundle=bundle, root=self.root)
                self.fail("STALE_REVIEW_PROBE", "stale proposal hash accepted")
            except WorkerError as exc:
                if exc.code != ERROR_CODES["SI2-REVIEW-PROPOSAL-HASH"]:
                    self.fail("STALE_REVIEW_PROBE", f"wrong code {exc.code}")
                self.probe_results["stale_review"] = exc.code

            # V1 PWNED exploit: mutate worktree after review, finalize must reject, no commit
            wt = Path(store.get_execution(bundle["execution_id"])[1])
            (wt / "docs" / "PWNED.md").write_text("PWNED\n", encoding="utf-8")
            try:
                finalize(
                    execution_id=bundle["execution_id"],
                    review_id=review["review_id"],
                    state_db=db,
                    repository_root=repo,
                )
                self.fail("V1_PWNED_PROBE", "finalize accepted altered worktree")
            except WorkerError as exc:
                if exc.code != ERROR_CODES["CONTENT_BINDING_MISMATCH"] and exc.state != "FAILED_FROZEN":
                    # Accept CONTENT_BINDING_MISMATCH
                    if ERROR_CODES["CONTENT_BINDING_MISMATCH"] not in (exc.code,):
                        self.fail("V1_PWNED_PROBE", f"wrong failure {exc.code}/{exc.state}")
                self.probe_results["v1_pwned"] = exc.code

            # Ensure no PWNED commit on a candidate branch
            import subprocess

            branches = subprocess.run(
                ["git", "branch", "--list", "self-improvement-v2/*"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                shell=False,
            )
            if branches.stdout.strip():
                self.fail("V1_PWNED_PROBE", "candidate branch created after exploit")
            self.probe_results["oracle_independence"] = "literal_codes"
        except Exception as exc:  # pragma: no cover - environment
            self.fail("PROBE_ENV", str(exc)[:300])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def run(self) -> dict[str, Any]:
        self.check_files()
        if not self.errors:
            self.check_schemas()
            self.check_worker_ast()
            self.check_workflow()
            self.probe_workflow_graph_mutations()
            self.probe_nested_paths()
            self.probe_immutability_and_binding()
        status = "PASS" if not self.errors else "FAIL"
        return {
            "validator": "self_improvement_v2_validate_system",
            "schema_version": SCHEMA_VERSION,
            "final_status": status,
            "checks": self.checks,
            "probe_results": self.probe_results,
            "errors": self.errors,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Self-Improvement Loop V2 system")
    parser.add_argument("--root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        return 2
    try:
        report = SystemValidator(root).run()
    except Exception as exc:
        Path(args.report).write_text(
            json.dumps({"final_status": "FAIL", "errors": [{"code": "ENV", "message": str(exc)}]}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    Path(args.report).write_text(text, encoding="utf-8")
    print(json.dumps({"final_status": report["final_status"], "error_count": len(report["errors"])}, sort_keys=True))
    return 0 if report["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
