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
    "tools/self_improvement_v2/risk_authority.py",
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


def _review_from_bundle(bundle: dict[str, Any], review_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_id": review_id,
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
        "declared_risk": bundle["declared_risk"],
        "computed_risk_pre": bundle["computed_risk_pre"],
        "effective_risk_pre": bundle["effective_risk_pre"],
        "computed_risk_post": bundle["computed_risk_post"],
        "effective_risk_post": bundle["effective_risk_post"],
        "risk_reason_codes_pre": list(bundle.get("risk_reason_codes_pre") or []),
        "risk_reason_codes_post": list(bundle.get("risk_reason_codes_post") or []),
        "policy_sha256": bundle["policy_sha256"],
        "risk_classifier_version": bundle["risk_classifier_version"],
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
                data["connections"]["Worker Decision Router"]["main"][1] = [
                    {"node": "Worker AUTHORIZED Continue", "type": "main", "index": 0}
                ]

            def m_prohibited(data: dict) -> None:
                data["connections"]["Worker Decision Router"]["main"][2] = [
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
            add(
                "wf-decision-required-autoauth",
                ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"],
                "route DECISION_REQUIRED to AUTHORIZED continue",
                m_high,
            )
            add(
                "wf-policy-rejected-worker",
                ERROR_CODES["SI2-WF-AUTOAUTH-NONLOW"],
                "route POLICY_REJECTED to worker",
                m_prohibited,
            )
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

    def probe_git_hooks_and_signing(self) -> None:
        """Real malicious hook + inherited signing probes against create_local_commit."""
        import stat
        import subprocess

        from tools.self_improvement_v2.git_worker import DetachedWorktree, create_local_commit

        tmp = Path(tempfile.mkdtemp(prefix="si2-git-probe-"))
        proofs: list[dict[str, Any]] = []
        try:
            repo = tmp / "repo"
            baseline = _init_temp_repo(repo)
            wt = DetachedWorktree(repo, baseline, "probehooks01abcdef")
            worktree = wt.prepare()
            marker = tmp / "hook-fired.txt"

            def install_hook(hooks_dir: Path, name: str) -> None:
                hooks_dir.mkdir(parents=True, exist_ok=True)
                script = hooks_dir / name
                script.write_text(
                    "#!/bin/sh\n"
                    f'echo hooked > "{marker.as_posix()}"\n'
                    "exit 1\n",
                    encoding="utf-8",
                    newline="\n",
                )
                script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            git_dir = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                check=True,
                shell=False,
            ).stdout.strip()
            hooks_path = Path(git_dir)
            if not hooks_path.is_absolute():
                hooks_path = (worktree / hooks_path).resolve()
            hooks_path = hooks_path / "hooks"
            for name in ("pre-commit", "commit-msg", "post-commit"):
                install_hook(hooks_path, name)

            subprocess.run(
                ["git", "config", "commit.gpgsign", "true"],
                cwd=str(worktree),
                check=True,
                shell=False,
            )
            subprocess.run(
                ["git", "config", "user.signingkey", "PROBEKEY"],
                cwd=str(worktree),
                check=True,
                shell=False,
            )
            subprocess.run(
                ["git", "config", "credential.helper", "store"],
                cwd=str(worktree),
                check=True,
                shell=False,
            )
            before_local = subprocess.run(
                ["git", "config", "--local", "--list"],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            ).stdout
            before_global = subprocess.run(
                ["git", "config", "--global", "--list"],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            ).stdout

            (worktree / "docs" / "GIT_PROBE.md").write_text("# probe\n", encoding="utf-8")
            try:
                sha = create_local_commit(worktree, "validator git probe")
                hook_ok = not marker.exists() and bool(sha)
                actual = None if hook_ok else ERROR_CODES["SI2-GIT-HOOKS-NOT-ISOLATED"]
                proofs.append(
                    _proof(
                        probe_id="git-malicious-hooks",
                        corruption_applied="pre-commit/commit-msg/post-commit exit 1 + marker",
                        validation_stage_executed="create_local_commit",
                        expected_error_code="HOOKS_NOT_EXECUTED",
                        actual_error_code="HOOKS_NOT_EXECUTED" if hook_ok else actual,
                        detected=hook_ok,
                    )
                )
                if not hook_ok:
                    self.fail(ERROR_CODES["SI2-GIT-HOOKS-NOT-ISOLATED"], "malicious hook executed or commit failed")
            except WorkerError as exc:
                proofs.append(
                    _proof(
                        probe_id="git-malicious-hooks",
                        corruption_applied="pre-commit/commit-msg/post-commit exit 1 + marker",
                        validation_stage_executed="create_local_commit",
                        expected_error_code="HOOKS_NOT_EXECUTED",
                        actual_error_code=exc.code,
                        detected=False,
                        unrelated_failure=True,
                    )
                )
                self.fail(exc.code, f"commit failed under hook/signing probe: {exc.message}")

            after_local = subprocess.run(
                ["git", "config", "--local", "--list"],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            ).stdout
            after_global = subprocess.run(
                ["git", "config", "--global", "--list"],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            ).stdout
            config_ok = after_local == before_local and after_global == before_global
            proofs.append(
                _proof(
                    probe_id="git-config-unchanged",
                    corruption_applied="gpgsign=true; signingkey; credential.helper=store",
                    validation_stage_executed="create_local_commit",
                    expected_error_code="CONFIG_UNCHANGED",
                    actual_error_code="CONFIG_UNCHANGED" if config_ok else ERROR_CODES["SI2-GIT-CONFIG-MUTATION"],
                    detected=config_ok,
                )
            )
            if not config_ok:
                self.fail(ERROR_CODES["SI2-GIT-CONFIG-MUTATION"], "git config mutated")

            signing_ok = "commit.gpgsign=true" in after_local and not marker.exists()
            proofs.append(
                _proof(
                    probe_id="git-signing-disabled",
                    corruption_applied="commit.gpgsign=true + signingkey",
                    validation_stage_executed="create_local_commit",
                    expected_error_code="SIGNING_NOT_INVOKED",
                    actual_error_code="SIGNING_NOT_INVOKED" if signing_ok else ERROR_CODES["SI2-GIT-SIGNING-NOT-DISABLED"],
                    detected=signing_ok,
                )
            )
            if not signing_ok:
                self.fail(ERROR_CODES["SI2-GIT-SIGNING-NOT-DISABLED"], "signing probe failed")
            wt.cleanup()
        except Exception as exc:  # pragma: no cover
            self.fail("GIT_PROBE_ENV", str(exc)[:300])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.probe_results["git_hooks_signing"] = proofs

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
            review = _review_from_bundle(bundle, "rev-probe-1")
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
                detected = exc.code == ERROR_CODES["CONTENT_BINDING_MISMATCH"]
                self.probe_results["v1_pwned"] = _proof(
                    probe_id="v1-pwned-worktree",
                    corruption_applied="write docs/PWNED.md in frozen worktree",
                    validation_stage_executed="finalize",
                    expected_error_code=ERROR_CODES["CONTENT_BINDING_MISMATCH"],
                    actual_error_code=exc.code,
                    detected=detected,
                    unrelated_failure=not detected,
                )
                if not detected:
                    self.fail("V1_PWNED_PROBE", f"wrong failure {exc.code}/{exc.state}")

            # Ensure no PWNED commit on a candidate branch
            import sqlite3
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

            # Fresh execution for proposal DB tampering / hash mutation probes.
            db2 = tmp / "state2.sqlite"
            proposal2 = _build_proposal(baseline, doc_path="docs/SI2_NOTE2.md", body="# ok2\n")
            proposal2["proposal_id"] = "prop-probe-2"
            proposal2["candidate_id"] = "cand-probe-2"
            bundle2 = execute_proposal(root=repo, proposal=proposal2, state_db=db2)
            store2 = ExperienceStore(db2)
            review2 = _review_from_bundle(bundle2, "rev-probe-2")
            store2.insert_review(review2)

            def _drop_triggers(path: Path) -> None:
                conn = sqlite3.connect(str(path))
                try:
                    for (name,) in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'si2_deny_%'"
                    ):
                        conn.execute(f"DROP TRIGGER IF EXISTS {name}")
                    conn.commit()
                finally:
                    conn.close()

            binding_proofs: list[dict[str, Any]] = []

            # Proposal payload tampering
            _drop_triggers(db2)
            conn = sqlite3.connect(str(db2))
            try:
                row = conn.execute(
                    "SELECT payload_json FROM proposal_snapshots WHERE proposal_id = ?",
                    (bundle2["proposal_id"],),
                ).fetchone()
                payload = json.loads(row[0])
                payload["objective"] = "TAMPERED"
                conn.execute(
                    "UPDATE proposal_snapshots SET payload_json = ? WHERE proposal_id = ?",
                    (json.dumps(payload, sort_keys=True), bundle2["proposal_id"]),
                )
                conn.commit()
            finally:
                conn.close()
            try:
                finalize(
                    execution_id=bundle2["execution_id"],
                    review_id=review2["review_id"],
                    state_db=db2,
                    repository_root=repo,
                )
                self.fail("PROPOSAL_TAMPER_PROBE", "finalize accepted tampered proposal payload")
                actual = None
                detected = False
            except WorkerError as exc:
                detected = exc.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"] and exc.state == "FAILED_FROZEN"
                actual = exc.code
                if not detected:
                    self.fail("PROPOSAL_TAMPER_PROBE", f"wrong failure {exc.code}/{exc.state}")
            binding_proofs.append(
                _proof(
                    probe_id="proposal-payload-tamper",
                    corruption_applied="SQLite UPDATE proposal_snapshots.payload_json",
                    validation_stage_executed="finalize.proposal_hash_recompute",
                    expected_error_code=ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
                    actual_error_code=actual,
                    detected=detected,
                    unrelated_failure=bool(actual) and not detected,
                )
            )

            # Stored-hash mutation probe (fresh DB)
            db3 = tmp / "state3.sqlite"
            proposal3 = _build_proposal(baseline, doc_path="docs/SI2_NOTE3.md", body="# ok3\n")
            proposal3["proposal_id"] = "prop-probe-3"
            proposal3["candidate_id"] = "cand-probe-3"
            bundle3 = execute_proposal(root=repo, proposal=proposal3, state_db=db3)
            store3 = ExperienceStore(db3)
            review3 = _review_from_bundle(bundle3, "rev-probe-3")
            store3.insert_review(review3)
            _drop_triggers(db3)
            conn = sqlite3.connect(str(db3))
            try:
                conn.execute(
                    "UPDATE proposal_snapshots SET content_sha256 = ? WHERE proposal_id = ?",
                    ("d" * 64, bundle3["proposal_id"]),
                )
                conn.commit()
            finally:
                conn.close()
            try:
                finalize(
                    execution_id=bundle3["execution_id"],
                    review_id=review3["review_id"],
                    state_db=db3,
                    repository_root=repo,
                )
                self.fail("STORED_HASH_PROBE", "finalize accepted mutated stored hash")
                actual = None
                detected = False
            except WorkerError as exc:
                detected = exc.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
                actual = exc.code
                if not detected:
                    self.fail("STORED_HASH_PROBE", f"wrong failure {exc.code}/{exc.state}")
            binding_proofs.append(
                _proof(
                    probe_id="stored-hash-mutation",
                    corruption_applied="SQLite UPDATE proposal_snapshots.content_sha256",
                    validation_stage_executed="finalize.proposal_hash_recompute",
                    expected_error_code=ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
                    actual_error_code=actual,
                    detected=detected,
                    unrelated_failure=bool(actual) and not detected,
                )
            )

            # Review-hash mismatch probe
            db4 = tmp / "state4.sqlite"
            proposal4 = _build_proposal(baseline, doc_path="docs/SI2_NOTE4.md", body="# ok4\n")
            proposal4["proposal_id"] = "prop-probe-4"
            proposal4["candidate_id"] = "cand-probe-4"
            bundle4 = execute_proposal(root=repo, proposal=proposal4, state_db=db4)
            store4 = ExperienceStore(db4)
            review4 = _review_from_bundle(bundle4, "rev-probe-4")
            store4.insert_review(review4)
            _drop_triggers(db4)
            conn = sqlite3.connect(str(db4))
            try:
                row = conn.execute(
                    "SELECT payload_json FROM review_snapshots WHERE review_id = ?",
                    (review4["review_id"],),
                ).fetchone()
                payload = json.loads(row[0])
                payload["proposal_sha256"] = "e" * 64
                conn.execute(
                    "UPDATE review_snapshots SET payload_json = ? WHERE review_id = ?",
                    (json.dumps(payload, sort_keys=True), review4["review_id"]),
                )
                conn.commit()
            finally:
                conn.close()
            try:
                finalize(
                    execution_id=bundle4["execution_id"],
                    review_id=review4["review_id"],
                    state_db=db4,
                    repository_root=repo,
                )
                self.fail("REVIEW_HASH_PROBE", "finalize accepted mutated review hash")
                actual = None
                detected = False
            except WorkerError as exc:
                detected = exc.code == ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"]
                actual = exc.code
                if not detected:
                    self.fail("REVIEW_HASH_PROBE", f"wrong failure {exc.code}/{exc.state}")
            binding_proofs.append(
                _proof(
                    probe_id="review-hash-mismatch",
                    corruption_applied="SQLite UPDATE review_snapshots.payload_json proposal_sha256",
                    validation_stage_executed="finalize.proposal_hash_recompute",
                    expected_error_code=ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
                    actual_error_code=actual,
                    detected=detected,
                    unrelated_failure=bool(actual) and not detected,
                )
            )

            # Confirm no candidate branches from tamper probes
            branches2 = subprocess.run(
                ["git", "branch", "--list", "self-improvement-v2/*"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                shell=False,
            )
            if branches2.stdout.strip():
                self.fail("PROPOSAL_TAMPER_PROBE", "candidate branch created after hash tamper")

            self.probe_results["proposal_binding"] = binding_proofs
            self.probe_results["oracle_independence"] = "literal_codes"
        except Exception as exc:  # pragma: no cover - environment
            self.fail("PROBE_ENV", str(exc)[:300])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def probe_risk_authority(self) -> None:
        """Executable risk-authority probes — not source-text / name presence checks."""
        from tools.self_improvement_v2.path_policy import load_policy
        from tools.self_improvement_v2.risk_authority import (
            DECISION_AUTHORIZED,
            DECISION_POLICY_REJECTED,
            DECISION_REQUIRED,
            authorize_execution,
            enforce_authorization,
        )

        tmp = Path(tempfile.mkdtemp(prefix="si2-risk-probe-"))
        proofs: list[dict[str, Any]] = []
        try:
            repo = tmp / "repo"
            baseline = _init_temp_repo(repo)
            specs_src = self.root / "specs" / "self_improvement" / "v2"
            specs_dst = repo / "specs" / "self_improvement" / "v2"
            specs_dst.parent.mkdir(parents=True, exist_ok=True)
            if specs_dst.exists():
                shutil.rmtree(specs_dst)
            shutil.copytree(specs_src, specs_dst)
            (repo / ".git" / "info" / "exclude").write_text("specs/\n", encoding="utf-8")
            policy = load_policy(repo)

            def record(
                probe_id: str,
                corruption: str,
                expected_decision: str,
                expected_code: str,
                actual_decision: str | None,
                actual_code: str | None,
                worktree_created: bool,
                commit_created: bool,
                stage: str,
            ) -> None:
                detected = actual_decision == expected_decision and (
                    not expected_code or actual_code == expected_code
                )
                unrelated = bool(actual_code) and actual_code != expected_code and not detected
                proofs.append(
                    {
                        "probe_id": probe_id,
                        "corruption_or_attack": corruption,
                        "stage_reached": stage,
                        "expected_decision": expected_decision,
                        "actual_decision": actual_decision,
                        "expected_error_code": expected_code,
                        "actual_error_code": actual_code,
                        "worktree_created": worktree_created,
                        "commit_created": commit_created,
                        "detected": detected,
                        "unrelated_failure": unrelated,
                    }
                )
                if not detected:
                    self.fail(expected_code or "RISK_PROBE", f"{probe_id} not detected")

            # Migration patch declares LOW.
            mig = _build_proposal(baseline, doc_path="database/migrations/001.sql", body="SELECT 1;\n")
            mig["allowed_paths"] = ["database/migrations/**", "docs/**"]
            auth = authorize_execution(mig, policy)
            record(
                "risk-migration-low-declared",
                "LOW declaration + migration path",
                DECISION_POLICY_REJECTED,
                ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
                auth.decision,
                auth.error_code,
                False,
                False,
                "authorize_execution",
            )

            # Credential-sensitive path.
            cred = _build_proposal(baseline, doc_path="docs/.env", body="SECRET=1\n")
            auth = authorize_execution(cred, policy)
            record(
                "risk-credential-low-declared",
                "LOW declaration + .env path",
                DECISION_POLICY_REJECTED,
                ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
                auth.decision,
                auth.error_code,
                False,
                False,
                "authorize_execution",
            )

            # Declared MEDIUM with otherwise LOW docs change.
            med = _build_proposal(baseline, doc_path="docs/MED.md", body="# m\n")
            med["risk_level"] = "MEDIUM"
            auth = authorize_execution(med, policy)
            record(
                "risk-declared-medium",
                "MEDIUM declaration with LOW computed content",
                DECISION_REQUIRED,
                ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
                auth.decision,
                auth.error_code,
                False,
                False,
                "authorize_execution",
            )

            # Replay / caller-supplied authorization.
            ok = _build_proposal(baseline, doc_path="docs/OK.md", body="# ok\n")
            try:
                authorize_execution(ok, policy, caller_authorization={"decision": "AUTHORIZED"})
                actual_decision, actual_code = DECISION_AUTHORIZED, None
            except WorkerError as exc:
                actual_decision, actual_code = DECISION_POLICY_REJECTED, exc.code
            record(
                "risk-auth-replay",
                "caller_authorization replay",
                DECISION_POLICY_REJECTED,
                ERROR_CODES["RISK_AUTH_REPLAY"],
                actual_decision,
                actual_code,
                False,
                False,
                "authorize_execution",
            )

            # Execute path must not create worktree when unauthorized.
            db = tmp / "risk.sqlite"
            worktree_before = list((tmp).glob("**/si2-*"))
            try:
                execute_proposal(root=repo, proposal=mig, state_db=db)
                stage = "execute_completed"
                actual_code = None
                wt_created = True
            except WorkerError as exc:
                stage = "execute_pre_auth"
                actual_code = exc.code
                wt_created = False
            record(
                "risk-execute-no-worktree",
                "execute migration proposal",
                DECISION_POLICY_REJECTED,
                ERROR_CODES["RISK_NOT_AUTO_AUTHORIZED"],
                DECISION_POLICY_REJECTED if actual_code else DECISION_AUTHORIZED,
                actual_code,
                wt_created,
                False,
                stage,
            )

            # Prove DetachedWorktree is not reachable via authorize failure path.
            # (No public bypass API; skip_risk_check rejected.)
            try:
                execute_proposal(root=repo, proposal=ok, state_db=tmp / "bypass.sqlite", skip_risk_check=True)
                actual_code = None
            except WorkerError as exc:
                actual_code = exc.code
            record(
                "risk-skip-flag-bypass",
                "skip_risk_check=True",
                DECISION_POLICY_REJECTED,
                ERROR_CODES["POLICY_REJECTED"],
                DECISION_POLICY_REJECTED if actual_code else DECISION_AUTHORIZED,
                actual_code,
                False,
                False,
                "execute_proposal",
            )

            # Successful authorize still produces AUTHORIZED for docs LOW.
            auth = authorize_execution(ok, policy)
            enforce_authorization(auth)
            record(
                "risk-docs-authorized",
                "control: docs LOW",
                DECISION_AUTHORIZED,
                "",
                auth.decision,
                auth.error_code or "",
                False,
                False,
                "authorize_execution",
            )
        except Exception as exc:  # pragma: no cover
            self.fail("RISK_PROBE_ENV", str(exc)[:300])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.probe_results["risk_authority"] = proofs

    def run(self) -> dict[str, Any]:
        self.check_files()
        if not self.errors:
            self.check_schemas()
            self.check_worker_ast()
            self.check_workflow()
            self.probe_workflow_graph_mutations()
            self.probe_nested_paths()
            self.probe_git_hooks_and_signing()
            self.probe_immutability_and_binding()
            self.probe_risk_authority()
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
