"""Narrow repair regressions for F-25-VERIFY-01 through F-25-SEQ-05."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, run
from tests.self_improvement_v2.test_option_a_rev25 import (
    CAND,
    CTREE,
    DIGEST,
    EID,
    GEN,
    HEAD,
    LiveBox,
    NID,
    TREE,
    WID,
    _hashes_for,
    _write_allowlist,
)
from tools.self_improvement_v2.export_seal import bind_observed_identity
from tools.self_improvement_v2.export_verify import verify_three_authority
from tools.self_improvement_v2.finalized_attestation import write_finalized_attestation
from tools.self_improvement_v2.git_worker import run_git
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_constants import SCHEMA_FINALIZED_ATTESTATION, WORKER_EXPORT_ALLOWLIST
from tools.self_improvement_v2.option_a_controller import run_rev25_export
from tools.self_improvement_v2.srl_git_exec import (
    REPO_ROLE_DISPOSABLE,
    REPO_ROLE_DURABLE,
    REPO_ROLE_RO_REVIEWED,
    REPO_ROLE_UNKNOWN,
    srl_git_exec,
)
from tools.self_improvement_v2.topology_consume import require_independent_live


def _real_srl_candidate_bundle(tmp: Path, *, marker: str = "cand") -> tuple[Path, str, str]:
    src = tmp / "bundle-src"
    init_temp_repo(src)
    run(["git", "checkout", "-b", "srl-candidate"], src)
    (src / "docs" / "CAND.md").write_text(f"{marker}\n", encoding="utf-8")
    run(["git", "add", "-A"], src)
    run(["git", "commit", "-m", marker], src)
    commit = run(["git", "rev-parse", "HEAD"], src).stdout.strip()
    tree = run(["git", "rev-parse", "HEAD^{tree}"], src).stdout.strip()
    bundle = tmp / "candidate.bundle"
    run(["git", "bundle", "create", str(bundle), "HEAD", "srl-candidate"], src)
    return bundle, commit, tree


def _write_allowlist_with_bundle(
    directory: Path, bundle: Path, commit: str, tree: str
) -> dict[str, bytes]:
    payloads = _write_allowlist(directory, commit=commit, tree=tree)
    payloads["candidate.bundle"] = bundle.read_bytes()
    payloads["candidate.bundle.sha256"] = (
        f"{hashlib.sha256(payloads['candidate.bundle']).hexdigest()}\n".encode()
    )
    (directory / "candidate.bundle").write_bytes(payloads["candidate.bundle"])
    (directory / "candidate.bundle.sha256").write_bytes(payloads["candidate.bundle.sha256"])
    return payloads


def _attestation(payloads: dict[str, bytes], *, commit: str = CAND, tree: str = CTREE) -> dict:
    hashes = _hashes_for(payloads)
    return {
        "execution_id": EID,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "reviewed_head": HEAD,
        "authorized_baseline": HEAD,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
        "finalization_result_sha256": hashes["finalization_result.json"],
        "sealed_artifact_hashes": hashes,
    }


def _dummy_c(*_args, **_kwargs) -> None:
    raise AssertionError("Authority C should not execute when A/B already failed")


# --- F-25-VERIFY-01 ---


def test_authority_c_omitted_refuses(tmp_path: Path) -> None:
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist(attempt)
    att = _attestation(payloads)
    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
        )
    assert ei.value.state == "FAILED_FROZEN"
    assert ei.value.code == "AUTHORITY_C_OMITTED"


def test_authority_c_fails_refuses(tmp_path: Path) -> None:
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist(attempt)
    att = _attestation(payloads)

    def boom(_bundle: Path, _dest: Path) -> None:
        raise WorkerError("AUTHORITY_C_FAILED", "clone failed", state="FAILED_FROZEN")

    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
            clone_bundle=boom,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.state == "FAILED_FROZEN"
    assert ei.value.code in {"AUTHORITY_C_FAILED", "FORGED_EXPORT"}


def test_a_and_b_pass_c_fails_refuses(tmp_path: Path) -> None:
    bundle, commit, tree = _real_srl_candidate_bundle(tmp_path)
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist_with_bundle(attempt, bundle, commit, tree)
    att = _attestation(payloads, commit=commit, tree=tree)

    def wrong_history(src: Path, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        init_temp_repo(dest)
        run(["git", "checkout", "-b", "srl-candidate"], dest)
        (dest / "docs" / "OTHER.md").write_text("other\n", encoding="utf-8")
        run(["git", "add", "-A"], dest)
        run(["git", "commit", "-m", "other"], dest)

    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
            clone_bundle=wrong_history,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_a_b_c_pass_verified(tmp_path: Path) -> None:
    bundle, commit, tree = _real_srl_candidate_bundle(tmp_path)
    attempt = tmp_path / "a"
    attempt.mkdir()
    payloads = _write_allowlist_with_bundle(attempt, bundle, commit, tree)
    att = _attestation(payloads, commit=commit, tree=tree)

    def clone(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--branch", "srl-candidate", str(src), str(dest)], tmp_path)

    verify_three_authority(
        attestation=att,
        attempt_dir=attempt,
        reviewed_head=HEAD,
        recompute_diff=lambda *_: payloads["actual.diff"],
        clone_bundle=clone,
        verify_scratch=tmp_path / "scratch",
    )


# --- F-25-BIND-01 ---


def test_bind_refuses_name_only_bundle_head() -> None:
    hashes = {name: "a" * 64 for name in WORKER_EXPORT_ALLOWLIST}
    with pytest.raises(WorkerError) as ei:
        bind_observed_identity(
            observed_commit=CAND,
            observed_tree=CTREE,
            sealed_commit_bytes=CAND,
            sealed_tree_bytes=CTREE,
            finalization_commit=CAND,
            finalization_tree=CTREE,
            bundle_heads=["refs/heads/srl-candidate"],
            sealed_bundle_sha256=hashes["candidate.bundle"],
        )
    assert ei.value.code == "SEAL_BIND_MISMATCH"


def test_bind_refuses_bundle_ref_sha_mismatch() -> None:
    hashes = {name: "a" * 64 for name in WORKER_EXPORT_ALLOWLIST}
    with pytest.raises(WorkerError) as ei:
        bind_observed_identity(
            observed_commit=CAND,
            observed_tree=CTREE,
            sealed_commit_bytes=CAND,
            sealed_tree_bytes=CTREE,
            finalization_commit=CAND,
            finalization_tree=CTREE,
            bundle_heads=[("0" * 40, "refs/heads/srl-candidate")],
            sealed_bundle_sha256=hashes["candidate.bundle"],
        )
    assert ei.value.code == "SEAL_BIND_MISMATCH"


def test_replaced_bundle_preserving_ref_name_fails(tmp_path: Path) -> None:
    bundle_a, commit_a, tree_a = _real_srl_candidate_bundle(tmp_path / "a", marker="bundle-a")
    bundle_b, commit_b, tree_b = _real_srl_candidate_bundle(tmp_path / "b", marker="bundle-b")
    assert commit_a != commit_b
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    payloads = _write_allowlist_with_bundle(attempt, bundle_a, commit_a, tree_a)
    att = _attestation(payloads, commit=commit_a, tree=tree_a)
    # Preserve srl-candidate name by installing a different bundle's bytes.
    (attempt / "candidate.bundle").write_bytes(bundle_b.read_bytes())

    def clone(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--branch", "srl-candidate", str(src), str(dest)], tmp_path)

    with pytest.raises(WorkerError) as ei:
        verify_three_authority(
            attestation=att,
            attempt_dir=attempt,
            reviewed_head=HEAD,
            recompute_diff=lambda *_: payloads["actual.diff"],
            clone_bundle=clone,
            verify_scratch=tmp_path / "scratch",
        )
    assert ei.value.state == "FAILED_FROZEN"
    _ = tree_b


def test_attestation_binds_bundle_sha256(tmp_path: Path) -> None:
    hashes = {name: "a" * 64 for name in WORKER_EXPORT_ALLOWLIST}
    fields = {
        "schema_version": SCHEMA_FINALIZED_ATTESTATION,
        "execution_id": EID,
        "reviewed_head": HEAD,
        "authorized_baseline": HEAD,
        "candidate_commit": CAND,
        "candidate_tree": CTREE,
        "srl_candidate_ref": "refs/heads/srl-candidate",
        "finalization_result_sha256": "4" * 64,
        "sealed_inventory_sha256": "5" * 64,
        "sealed_artifact_hashes": hashes,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
        "staging_generation": GEN,
        "worker_container_id": WID,
        "worker_started_at": "t0",
        "worker_image_digest": DIGEST,
        "worker_netns_identity": "net-1",
        "n8n_container_id": NID,
        "topology_attestation_identity": "6" * 64,
        "topology_attestation_sequence": 1,
        "launcher_observation_sequence": 2,
        "observed_unix_ts": 1,
    }
    record = write_finalized_attestation(tmp_path / "ledger", fields)
    assert record["candidate_bundle_sha256"] == hashes["candidate.bundle"]
    disagree = dict(fields)
    disagree["candidate_bundle_sha256"] = "b" * 64
    with pytest.raises(WorkerError) as ei:
        write_finalized_attestation(tmp_path / "ledger2", disagree)
    assert ei.value.state == "FAILED_FROZEN"


# --- F-25-ATT-02 ---


def test_authorized_baseline_must_equal_reviewed_head(tmp_path: Path) -> None:
    hashes = {name: "a" * 64 for name in WORKER_EXPORT_ALLOWLIST}
    fields = {
        "schema_version": SCHEMA_FINALIZED_ATTESTATION,
        "execution_id": EID,
        "reviewed_head": HEAD,
        "authorized_baseline": "0" * 40,
        "candidate_commit": CAND,
        "candidate_tree": CTREE,
        "srl_candidate_ref": "refs/heads/srl-candidate",
        "finalization_result_sha256": "4" * 64,
        "sealed_inventory_sha256": "5" * 64,
        "sealed_artifact_hashes": hashes,
        "candidate_bundle_sha256": hashes["candidate.bundle"],
        "staging_generation": GEN,
        "worker_container_id": WID,
        "worker_started_at": "t0",
        "worker_image_digest": DIGEST,
        "worker_netns_identity": "net-1",
        "n8n_container_id": NID,
        "topology_attestation_identity": "6" * 64,
        "topology_attestation_sequence": 1,
        "launcher_observation_sequence": 2,
        "observed_unix_ts": 1,
    }
    with pytest.raises(WorkerError) as ei:
        write_finalized_attestation(tmp_path / "ledger", fields)
    assert ei.value.state == "FAILED_FROZEN"
    assert not (tmp_path / "ledger" / "finalized_attestation.json").exists()


def test_controller_refuses_baseline_mismatch(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    gen.mkdir()
    _write_allowlist(gen)
    box = LiveBox()
    with pytest.raises(WorkerError) as ei:
        run_rev25_export(
            execution_id=EID,
            reviewed_head=HEAD,
            authorized_baseline="0" * 40,
            staging_generation=GEN,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            inspect_worker=box.worker,
            inspect_n8n=box.n8n,
            list_all_ids=box.listing,
            observe_git=lambda: (CAND, CTREE, CAND),
            bundle_heads=lambda: [(CAND, "refs/heads/srl-candidate")],
            worker_generation_dir=gen,
            ledger_root=tmp_path / "ledger",
            durable_root=tmp_path / "durable",
            copy_fn=lambda argv: Path(argv[-1]).write_bytes(b"x"),
            recompute_diff=lambda *_: b"x",
            now_ts=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


# --- F-25-GIT-03 ---


def test_reset_hard_not_self_authorized_from_argv(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    init_temp_repo(repo)
    with pytest.raises(WorkerError) as ei:
        run_git(["reset", "--hard", "HEAD"], cwd=repo)
    assert ei.value.code == "FORBIDDEN_GIT_OP"
    with pytest.raises(WorkerError):
        srl_git_exec(["reset", "--hard", "HEAD"], cwd=repo)
    with pytest.raises(WorkerError):
        srl_git_exec(
            ["reset", "--hard", "HEAD"],
            cwd=repo,
            allow_reset_hard=True,
            repository_role=REPO_ROLE_RO_REVIEWED,
        )
    with pytest.raises(WorkerError):
        srl_git_exec(
            ["reset", "--hard", "HEAD"],
            cwd=repo,
            allow_reset_hard=True,
            repository_role=REPO_ROLE_DURABLE,
        )
    with pytest.raises(WorkerError):
        srl_git_exec(
            ["reset", "--hard", "HEAD"],
            cwd=repo,
            allow_reset_hard=True,
            repository_role=REPO_ROLE_UNKNOWN,
        )
    ok = srl_git_exec(
        ["reset", "--hard", "HEAD"],
        cwd=repo,
        allow_reset_hard=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    )
    assert ok.returncode == 0


# --- F-25-TEST-04 ---


CLOSED_WORLD_UNGUARDED_GIT = {
    "validate_system.py": (
        "SI2 adversarial probes construct disposable probe repos and snapshot "
        "git config/branches; not the Revision 2.5 export runner."
    ),
}

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
_SOLE_RUNNER = "srl_git_exec.py"


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in {"subprocess", "os"}:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _first_argv_looks_like_git(node: ast.AST) -> bool:
    if isinstance(node, ast.List) and node.elts:
        first = _const_str(node.elts[0])
        if first is None:
            return False
        return Path(first).name.lower() in {"git", "git.exe"}
    text = _const_str(node)
    if text is None:
        return False
    lowered = text.strip().lower()
    return lowered == "git" or lowered.startswith("git ") or lowered.endswith("\\git") or lowered.endswith("/git")


def _call_is_os_system(func: ast.AST, aliases: dict[str, str]) -> bool:
    if isinstance(func, ast.Attribute) and func.attr == "system":
        if isinstance(func.value, ast.Name) and aliases.get(func.value.id, func.value.id) in {"os"}:
            return True
    if isinstance(func, ast.Name) and aliases.get(func.id) == "os.system":
        return True
    return False


def _call_is_subprocess(func: ast.AST, aliases: dict[str, str]) -> bool:
    if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_FUNCS:
        if isinstance(func.value, ast.Name):
            target = aliases.get(func.value.id, func.value.id)
            return target in {"subprocess"} or target.endswith("subprocess")
    if isinstance(func, ast.Name):
        mapped = aliases.get(func.id, "")
        return mapped.startswith("subprocess.") and mapped.split(".")[-1] in _SUBPROCESS_FUNCS
    return False


def _shell_true(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def detect_unguarded_git(root: Path) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _import_aliases(tree)
        hits: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_is_os_system(node.func, aliases) and node.args and _first_argv_looks_like_git(node.args[0]):
                hits.append(getattr(node, "lineno", 0))
                continue
            if not _call_is_subprocess(node.func, aliases) or not node.args:
                continue
            if _first_argv_looks_like_git(node.args[0]) or (
                _shell_true(node) and _first_argv_looks_like_git(node.args[0])
            ):
                hits.append(getattr(node, "lineno", 0))
        if hits:
            found[path.name] = hits
    return found


def test_unguarded_git_detection_is_closed_world() -> None:
    root = Path(__file__).resolve().parents[2] / "tools" / "self_improvement_v2"
    runner = root / _SOLE_RUNNER
    assert runner.is_file()
    runner_src = runner.read_text(encoding="utf-8")
    assert 'prefix = ["git"]' in runner_src
    assert "subprocess.run(" in runner_src
    found = detect_unguarded_git(root)
    production = {name: lines for name, lines in found.items() if name != _SOLE_RUNNER}
    assert set(production) == set(CLOSED_WORLD_UNGUARDED_GIT)
    for name, reason in CLOSED_WORLD_UNGUARDED_GIT.items():
        assert reason.strip()
        assert production[name]


# --- F-25-SEQ-05 ---


def test_copy_audit_sequence_is_monotonic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, commit, tree = _real_srl_candidate_bundle(tmp_path)
    gen = tmp_path / "gen"
    gen.mkdir()
    payloads = _write_allowlist_with_bundle(gen, bundle, commit, tree)
    box = LiveBox()
    sequences: list[int] = []
    original = require_independent_live

    def spy(**kwargs):
        sequences.append(int(kwargs["sequence"]))
        return original(**kwargs)

    monkeypatch.setattr(
        "tools.self_improvement_v2.option_a_controller.require_independent_live",
        spy,
    )

    def copy_fn(argv: list[str]) -> None:
        name = Path(argv[-1]).name
        Path(argv[-1]).write_bytes(payloads[name])

    def clone(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--branch", "srl-candidate", str(src), str(dest)], tmp_path)

    run_rev25_export(
        execution_id=EID,
        reviewed_head=HEAD,
        authorized_baseline=HEAD,
        staging_generation=GEN,
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        inspect_worker=box.worker,
        inspect_n8n=box.n8n,
        list_all_ids=box.listing,
        observe_git=lambda: (commit, tree, commit),
        bundle_heads=lambda: [(commit, "refs/heads/srl-candidate")],
        worker_generation_dir=gen,
        ledger_root=tmp_path / "ledger",
        durable_root=tmp_path / "durable",
        copy_fn=copy_fn,
        recompute_diff=lambda *_: payloads["actual.diff"],
        clone_bundle=clone,
        verify_scratch=tmp_path / "scratch",
        now_ts=1,
    )
    assert len(sequences) >= 3
    for prev, cur in zip(sequences, sequences[1:]):
        assert cur > prev
    _ = TREE
