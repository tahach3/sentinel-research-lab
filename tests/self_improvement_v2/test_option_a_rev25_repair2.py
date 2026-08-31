"""Repair #2: production wiring, reviewed-source isolation, Wall refs, argv guard."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import (
    REAL_ROOT,
    build_pass_review,
    build_proposal,
    init_temp_repo,
    run,
)
from tests.self_improvement_v2.test_option_a_rev25 import (
    DIGEST,
    LiveBox,
    NID,
    RecordingDocker,
    WID,
)
from tests.self_improvement_v2.test_option_a_rev25_repair1 import (
    CLOSED_WORLD_UNGUARDED_GIT,
    _SOLE_RUNNER,
    classify_process_launch_sites,
    detect_unguarded_git,
    test_a_and_b_pass_c_fails_refuses,
    test_a_b_c_pass_verified,
    test_authority_c_fails_refuses,
    test_authority_c_omitted_refuses,
    test_authorized_baseline_must_equal_reviewed_head,
    test_bind_refuses_bundle_ref_sha_mismatch,
    test_bind_refuses_name_only_bundle_head,
    test_copy_audit_sequence_is_monotonic,
    test_reset_hard_not_self_authorized_from_argv,
    test_unguarded_git_detection_is_closed_world,
)
from tools.self_improvement_v2.executor import execute_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.export_verify import reconstruct_authority_c
from tools.self_improvement_v2.git_worker import create_branch_at_commit, run_git
from tools.self_improvement_v2.import_closure import compute_static_import_closure
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_controller import (
    Rev25RuntimeDeps,
    run_rev25_export,
    run_rev25_production_finalize,
)
from tools.self_improvement_v2.runtime_bridge import finalize_operation
from tools.self_improvement_v2.runtime_config import RuntimeConfig
from tools.self_improvement_v2.srl_git_exec import REPO_ROLE_DISPOSABLE, REPO_ROLE_RO_REVIEWED
from tools.self_improvement_v2.trusted_origin import PIN_REL, TRUSTED_MODULE_NAMES
from tools.self_improvement_v2.wall_reassert import (
    WallReassertError,
    assert_wall_artifacts_unchanged,
    capture_wall_artifact_snapshot,
)

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "tools" / "self_improvement_v2" / "runtime_bridge.py"
CONTROLLER = REPO / "tools" / "self_improvement_v2" / "option_a_controller.py"
REQUIRED_REV25 = (
    "tools.self_improvement_v2.option_a_controller",
    "tools.self_improvement_v2.export_seal",
    "tools.self_improvement_v2.export_verify",
    "tools.self_improvement_v2.export_transport",
    "tools.self_improvement_v2.finalized_attestation",
    "tools.self_improvement_v2.option_a_constants",
    "tools.self_improvement_v2.topology_consume",
    "tools.self_improvement_v2.topology_identity",
    "tools.self_improvement_v2.srl_git_exec",
)


def _rev25_deps() -> Rev25RuntimeDeps:
    box = LiveBox()
    docker = RecordingDocker()
    return Rev25RuntimeDeps(
        inspect_worker=box.worker,
        inspect_n8n=box.n8n,
        list_all_ids=box.listing,
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        copy_fn=docker.copy_fn,
        clone_bundle=reconstruct_authority_c,
        exec_docker=docker.exec_docker,
    )


def _ready_execution(tmp_path: Path, *, env_reviewed: bool = True, monkeypatch=None):
    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo, include_worker_package=True)
    db = tmp_path / "runtime" / "v2-state.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    proposal = build_proposal(baseline)
    bundle = execute_proposal(root=repo, proposal=proposal, state_db=db)
    store = ExperienceStore(db)
    review = build_pass_review(bundle, proposal)
    store.insert_review(review)
    if env_reviewed and monkeypatch is not None:
        monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
        monkeypatch.setenv("SRL_REVIEWED_HEAD", baseline)
    return repo, db, proposal, bundle, review, store, baseline


def _config(repo: Path, db: Path) -> RuntimeConfig:
    return RuntimeConfig(
        repository_root=repo,
        state_db=db,
        worker_token="test-worker-token-not-for-production",
        worker_host="127.0.0.1",
        worker_port=0,
        rev25_deps=_rev25_deps(),
    )


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return names


def _function_name_refs(path: Path, func_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    refs: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    refs.add(child.id)
                elif isinstance(child, ast.Attribute):
                    refs.add(child.attr)
    return refs


def test_production_entrypoint_reaches_rev25_controller() -> None:
    imported = _imported_names(BRIDGE)
    assert "tools.self_improvement_v2.option_a_controller" in imported
    assert "run_rev25_production_finalize" in imported
    refs = _function_name_refs(BRIDGE, "finalize_operation")
    assert "run_rev25_production_finalize" in refs
    assert "run_rev25_export" in CONTROLLER.read_text(encoding="utf-8")
    closure = compute_static_import_closure(REPO)
    assert "tools.self_improvement_v2.option_a_controller" in closure


def test_production_entrypoint_cannot_reach_legacy_source_branch() -> None:
    imported = _imported_names(BRIDGE)
    assert "finalize_or_freeze" not in imported
    assert "tools.self_improvement_v2.finalizer" not in imported
    refs = _function_name_refs(BRIDGE, "finalize_operation")
    assert "finalize_or_freeze" not in refs
    assert "finalize" not in refs
    assert "create_branch_at_commit" not in refs
    controller_src = CONTROLLER.read_text(encoding="utf-8")
    assert "create_branch_at_commit" not in controller_src
    assert "from tools.self_improvement_v2.finalizer" not in controller_src


def test_production_finalize_does_not_create_source_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    monkeypatch.setattr(
        "tools.self_improvement_v2.runtime_bridge.assert_trusted_code_origin",
        lambda: {"status": "PASS"},
    )
    result = finalize_operation(
        _config(repo, db),
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        review=None,
    )
    assert result["status"] == "PASS"
    assert result["finalization"]["candidate_commit"]
    branches = run(["git", "branch", "--list", "self-improvement-v2/*"], repo).stdout.strip()
    assert branches == ""
    heads = run(["git", "for-each-ref", "--format=%(refname)", "refs/heads"], repo).stdout
    assert "self-improvement-v2/" not in heads


def test_reviewed_source_git_branch_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "sentinel-research-lab"
    head = init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    with pytest.raises(WorkerError) as ei:
        run_git(["branch", "evil-branch", head], cwd=repo, repository_role=REPO_ROLE_RO_REVIEWED)
    assert ei.value.code == "REVIEWED_SOURCE_WRITE"
    with pytest.raises(WorkerError):
        create_branch_at_commit(repo, "evil-branch", head)


@pytest.mark.parametrize(
    "args",
    [
        ["branch", "x"],
        ["update-ref", "refs/heads/evil", "HEAD"],
        ["checkout", "HEAD"],
        ["reset", "--hard", "HEAD"],
        ["add", "-A"],
        ["config", "--local", "user.name", "evil"],
    ],
)
def test_reviewed_source_mutation_ops_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    repo = tmp_path / "sentinel-research-lab"
    init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    with pytest.raises(WorkerError) as ei:
        run_git(args, cwd=repo, allow_reset_hard=True, repository_role=REPO_ROLE_DISPOSABLE)
    assert ei.value.code in {"REVIEWED_SOURCE_WRITE", "FORBIDDEN_GIT_OP"}


def test_wall_snapshot_detects_refs_heads_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = init_temp_repo(repo)
    before = capture_wall_artifact_snapshot(repo)
    assert "git_authority_surface_fingerprint" in before
    run(["git", "branch", "wall-sneak", head], repo)
    with pytest.raises(WallReassertError) as exc:
        assert_wall_artifacts_unchanged(repo, before)
    assert "git_authority_surface_fingerprint" in exc.value.message


def test_wall_snapshot_detects_packed_refs_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    run(["git", "pack-refs", "--all"], repo)
    packed = repo / ".git" / "packed-refs"
    assert packed.is_file()
    before = capture_wall_artifact_snapshot(repo)
    sha = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    packed.write_bytes(packed.read_bytes() + f"{sha} refs/heads/packed-sneak\n".encode())
    with pytest.raises(WallReassertError) as exc:
        assert_wall_artifacts_unchanged(repo, before)
    assert "git_authority_surface_fingerprint" in exc.value.message


def test_rev25_module_modification_invalidates_trusted_pin(tmp_path: Path) -> None:
    from tools.self_improvement_v2.trusted_origin import (
        ENV_REPOSITORY_ROOT,
        ENV_REVIEWED_HEAD,
        TrustedOriginError,
        assert_trusted_code_origin,
        build_content_only_pin,
    )

    pin = json.loads((REPO / PIN_REL).read_text(encoding="utf-8"))
    live = build_content_only_pin(REPO)
    assert set(pin["modules"]) == set(live["modules"])
    assert pin["combined"] == live["combined"]
    target = "tools.self_improvement_v2.option_a_controller"
    assert target in pin["modules"]
    forged = dict(pin)
    forged["modules"] = dict(pin["modules"])
    forged["modules"][target] = "0" * 64
    forged_root = tmp_path / "sentinel-research-lab"
    init_temp_repo(forged_root, include_worker_package=True)
    (forged_root / PIN_REL).write_text(json.dumps(forged, indent=2) + "\n", encoding="utf-8")
    run(["git", "add", "-A"], forged_root)
    run(["git", "commit", "-m", "forge pin"], forged_root)
    head = run(["git", "rev-parse", "HEAD"], forged_root).stdout.strip()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(forged_root.resolve()))
        monkeypatch.setenv(ENV_REVIEWED_HEAD, head)
        with pytest.raises(TrustedOriginError):
            assert_trusted_code_origin()
    finally:
        monkeypatch.undo()


def test_trusted_pin_equals_actual_reachable_closure() -> None:
    closure = compute_static_import_closure(REPO)
    pin = json.loads((REPO / PIN_REL).read_text(encoding="utf-8"))
    assert frozenset(TRUSTED_MODULE_NAMES) == closure
    assert set(pin["modules"]) == set(closure)
    for name in REQUIRED_REV25:
        assert name in closure
        assert name in pin["modules"]


def test_dynamic_subprocess_argv_without_classification_fails() -> None:
    snippets = [
        "import subprocess\ncmd = ['git', 'push']\nsubprocess.run(cmd)\n",
        "import subprocess\nGIT = 'git'\nsubprocess.run([GIT, 'push'])\n",
        "import subprocess\nsubprocess.run(['gi' + 't', 'push'])\n",
    ]
    for src in snippets:
        tree = ast.parse(src)
        sites = classify_process_launch_sites(tree, filename="probe.py")
        assert sites, src


def test_classified_validation_runner_argv_remains_accepted() -> None:
    root = REPO / "tools" / "self_improvement_v2"
    found = detect_unguarded_git(root)
    assert "validation_runner.py" not in found
    sites = classify_process_launch_sites(
        ast.parse((root / "validation_runner.py").read_text(encoding="utf-8")),
        filename="validation_runner.py",
    )
    assert sites == []


def test_process_launch_sites_are_closed_world() -> None:
    root = REPO / "tools" / "self_improvement_v2"
    unclassified: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sites = classify_process_launch_sites(tree, filename=path.name)
        if sites:
            unclassified[path.name] = [line for line, _reason in sites]
    assert _SOLE_RUNNER not in unclassified
    assert "validation_runner.py" not in unclassified
    assert set(unclassified) <= set(CLOSED_WORLD_UNGUARDED_GIT)


def test_repair1_regressions_remain_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("c1", "c2", "c3", "c4", "c5", "c6", "c7"):
        (tmp_path / name).mkdir()
    test_authority_c_omitted_refuses(tmp_path / "c1")
    test_authority_c_fails_refuses(tmp_path / "c2")
    test_a_and_b_pass_c_fails_refuses(tmp_path / "c3")
    test_a_b_c_pass_verified(tmp_path / "c4")
    test_bind_refuses_name_only_bundle_head()
    test_bind_refuses_bundle_ref_sha_mismatch()
    test_authorized_baseline_must_equal_reviewed_head(tmp_path / "c5")
    test_reset_hard_not_self_authorized_from_argv(tmp_path / "c6")
    test_unguarded_git_detection_is_closed_world()
    test_copy_audit_sequence_is_monotonic(tmp_path / "c7", monkeypatch)


def test_production_finalize_calls_controller_not_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    called: list[str] = []
    original = run_rev25_export

    def spy(**kwargs):
        called.append("run_rev25_export")
        return original(**kwargs)

    monkeypatch.setattr(
        "tools.self_improvement_v2.option_a_controller.run_rev25_export",
        spy,
    )
    run_rev25_production_finalize(
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        state_db=db,
        repository_root=repo,
        deps=_rev25_deps(),
    )
    assert called == ["run_rev25_export"]


def test_pin_path_uses_repo_root() -> None:
    assert (REAL_ROOT / PIN_REL).is_file()
