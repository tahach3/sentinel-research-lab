"""Repair #4: production Compose/launcher wiring for complete Revision 2.5 transport."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.self_improvement_v2.test_option_a_rev25 import (
    DIGEST,
    EID,
    GEN,
    NID,
    RecordingDocker,
    WID,
)
from tests.self_improvement_v2.test_option_a_rev25_repair2 import _ready_execution
from tools.self_improvement_v2.docker_cli import (
    docker_cp_file_argv,
    docker_cp_into_worker_argv,
    docker_exec_cat_argv,
    docker_exec_mkdir_argv,
    run_docker_argv,
)
from tools.self_improvement_v2.export_verify import reconstruct_authority_c
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_constants import RO_REVIEWED_ROOT, WORKER_EXPORT_ALLOWLIST
from tools.self_improvement_v2.option_a_controller import (
    Rev25RuntimeDeps,
    run_rev25_export,
    run_rev25_production_finalize,
)
from tools.self_improvement_v2.runtime_bridge import finalize_operation
from tools.self_improvement_v2.runtime_config import load_runtime_config

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
CONTROLLER = REPO / "tools" / "self_improvement_v2" / "option_a_controller.py"
CONFIG = REPO / "tools" / "self_improvement_v2" / "runtime_config.py"
TOKEN = "test-worker-token-not-for-production"
FORBIDDEN_PROVIDER_MODULES = ("openai", "anthropic", "httpx", "requests")
WORKER_MODULE = "tools.self_improvement_v2.runtime_bridge"


def _worker_block(text: str) -> str:
    match = re.search(
        r"(?ms)^  srl-worker:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:|^volumes:|\Z)",
        text,
    )
    if not match:
        raise AssertionError("srl-worker service block not found in docker-compose.yml")
    return match.group(0)


def _operator_env(repo: Path, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    monkeypatch.setenv("SRL_STATE_DB", str(db.resolve()))
    monkeypatch.setenv("SRL_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("SRL_WORKER_HOST", "127.0.0.1")
    monkeypatch.setenv("SRL_WORKER_PORT", "0")
    monkeypatch.setenv("SRL_WORKER_CONTAINER_ID", WID)
    monkeypatch.setenv("SRL_N8N_CONTAINER_ID", NID)
    monkeypatch.setenv("SRL_WORKER_IMAGE_DIGEST", DIGEST)


def _live_deps(docker: RecordingDocker) -> Rev25RuntimeDeps:
    import json

    def inspect_one(cid: str) -> dict:
        code, out, err = docker.runner(["docker", "inspect", cid])
        if code != 0:
            raise WorkerError("FAILED_FROZEN", err, state="FAILED_FROZEN")
        payload = json.loads(out)
        return payload[0] if isinstance(payload, list) else payload

    def list_all_ids() -> list[str]:
        code, out, err = docker.runner(["docker", "ps", "--all", "--quiet", "--no-trunc"])
        if code != 0:
            raise WorkerError("FAILED_FROZEN", err, state="FAILED_FROZEN")
        return [line.strip().lower() for line in out.splitlines() if line.strip()]

    return Rev25RuntimeDeps(
        inspect_worker=inspect_one,
        inspect_n8n=inspect_one,
        list_all_ids=list_all_ids,
        worker_id=WID,
        n8n_id=NID,
        expected_image_digest=DIGEST,
        copy_fn=docker.copy_fn,
        clone_bundle=reconstruct_authority_c,
        exec_docker=docker.exec_docker,
    )


# --- Compose / worker launch contract ---


def test_compose_supplies_mandatory_identities_without_embedding_secrets() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    worker = _worker_block(text)
    assert f"working_dir: {RO_REVIEWED_ROOT}" in worker
    assert f"PYTHONPATH: {RO_REVIEWED_ROOT}" in worker
    assert f"SRL_REPOSITORY_ROOT: {RO_REVIEWED_ROOT}" in worker
    assert "SRL_STATE_DB: /tmp/srl-zone-p/v2-state.sqlite" in worker
    assert "SRL_WORKER_TOKEN: ${SRL_WORKER_TOKEN:?SRL_WORKER_TOKEN is required}" in worker
    assert "SRL_REVIEWED_HEAD: ${SRL_REVIEWED_HEAD:?SRL_REVIEWED_HEAD is required}" in worker
    assert (
        "SRL_WORKER_CONTAINER_ID: ${SRL_WORKER_CONTAINER_ID:?SRL_WORKER_CONTAINER_ID is required}"
        in worker
    )
    assert "SRL_N8N_CONTAINER_ID: ${SRL_N8N_CONTAINER_ID:?SRL_N8N_CONTAINER_ID is required}" in worker
    assert (
        "SRL_WORKER_IMAGE_DIGEST: ${SRL_WORKER_IMAGE_DIGEST:?SRL_WORKER_IMAGE_DIGEST is required}"
        in worker
    )
    assert WORKER_MODULE in worker
    assert "python" in worker
    assert "./:/srl/sentinel-research-lab:ro" in worker
    assert "SRL_WORKER_TOKEN: ${SRL_WORKER_TOKEN:-" not in worker
    assert not re.search(r"SRL_WORKER_TOKEN:\s+[\"']?[A-Za-z0-9_\-]{8,}", worker)


def test_compose_launch_command_resolves_rev25_module_from_mounted_source(
    tmp_path: Path,
) -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    worker = _worker_block(text)
    assert f"working_dir: {RO_REVIEWED_ROOT}" in worker
    assert f"PYTHONPATH: {RO_REVIEWED_ROOT}" in worker
    assert f"-m\",\n        \"{WORKER_MODULE}\"" in text.replace(" ", "") or WORKER_MODULE in worker
    cwd = tmp_path / "not-the-repo"
    cwd.mkdir()
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tools.self_improvement_v2.runtime_bridge as m; print(m.__file__)",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    resolved = Path(proc.stdout.strip()).resolve()
    expected = (REPO / "tools" / "self_improvement_v2" / "runtime_bridge.py").resolve()
    assert resolved == expected


def test_worker_source_not_importable_without_launch_pythonpath(tmp_path: Path) -> None:
    cwd = tmp_path / "empty"
    cwd.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", f"import {WORKER_MODULE}"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "ModuleNotFoundError" in (proc.stderr + proc.stdout)


# --- Complete production deps ---


def test_load_runtime_config_constructs_complete_rev25_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    docker = RecordingDocker()
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=docker.runner,
    )
    deps = config.rev25_deps
    assert isinstance(deps, Rev25RuntimeDeps)
    assert deps.copy_fn is not None
    assert deps.clone_bundle is not None
    assert deps.exec_docker is not None
    src = CONFIG.read_text(encoding="utf-8")
    assert "_copy_from_generation" not in src
    assert "copy_fn=" in src
    assert "clone_bundle=" in src
    assert "exec_docker=" in src or "docker_exec" in src


def test_load_runtime_config_clone_bundle_is_authority_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    docker = RecordingDocker()
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=docker.runner,
    )
    assert config.rev25_deps.clone_bundle is reconstruct_authority_c


# --- Integration: compose-equivalent env → load_runtime_config → finalize ---


def test_production_boundary_finalize_exercises_exec_cp_and_authority_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    _operator_env(repo, db, monkeypatch)
    docker = RecordingDocker()
    authority_c = {"n": 0}
    real_c = reconstruct_authority_c

    def spy_clone(src: Path, dest: Path, **kwargs) -> None:
        authority_c["n"] += 1
        return real_c(src, dest, **kwargs)

    monkeypatch.setattr(
        "tools.self_improvement_v2.runtime_config.reconstruct_authority_c",
        spy_clone,
    )
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=docker.runner,
    )
    monkeypatch.setattr(
        "tools.self_improvement_v2.runtime_bridge.assert_trusted_code_origin",
        lambda: {"status": "PASS"},
    )
    result = finalize_operation(
        config,
        execution_id=bundle["execution_id"],
        review_id=review["review_id"],
        review=None,
    )
    assert result["status"] == "PASS"
    assert docker.has_inspect_or_ps()
    assert docker.has_exec(), docker.ops
    assert docker.has_per_file_cp(), docker.ops
    assert not docker.inspect_only()
    inbound = [
        argv
        for argv in docker.ops
        if len(argv) == 4 and argv[1] == "cp" and argv[3].startswith(f"{WID}:")
    ]
    outbound = [
        argv
        for argv in docker.ops
        if len(argv) == 4 and argv[1] == "cp" and argv[2].startswith(f"{WID}:")
    ]
    assert inbound, "production must inbound per-file docker cp into the worker"
    assert outbound, "production must outbound per-file docker cp to the host attempt"
    assert len(outbound) == len(WORKER_EXPORT_ALLOWLIST)
    assert docker.directory_cp == 0
    assert docker.local_copy_fallback == 0
    assert authority_c["n"] >= 1
    assert all("/." not in " ".join(argv) for argv in docker.ops if "cp" in argv)


def test_inspect_only_trace_is_not_a_successful_transport() -> None:
    docker = RecordingDocker()
    docker.runner(["docker", "ps", "--all", "--quiet", "--no-trunc"])
    docker.runner(["docker", "inspect", WID])
    assert docker.inspect_only()
    assert not (docker.has_exec() and docker.has_per_file_cp())


# --- Negative production-boundary tests ---


def test_missing_worker_token_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    monkeypatch.delenv("SRL_WORKER_TOKEN", raising=False)
    docker = RecordingDocker()
    with pytest.raises(WorkerError) as ei:
        load_runtime_config(
            repository_root=str(repo.resolve()),
            state_db=str(db.resolve()),
            worker_host="127.0.0.1",
            worker_port=0,
            docker_runner=docker.runner,
        )
    assert ei.value.state == "FAILED_FROZEN"
    assert "SRL_WORKER_TOKEN is required" in ei.value.message


def test_invalid_worker_identity_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    monkeypatch.setenv("SRL_WORKER_CONTAINER_ID", "not-a-64-hex-id")
    docker = RecordingDocker()
    with pytest.raises(WorkerError) as ei:
        load_runtime_config(
            repository_root=str(repo.resolve()),
            state_db=str(db.resolve()),
            worker_token=TOKEN,
            worker_host="127.0.0.1",
            worker_port=0,
            docker_runner=docker.runner,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_missing_docker_exec_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    docker = RecordingDocker()
    deps = _live_deps(docker)
    object.__setattr__(deps, "exec_docker", None)
    with pytest.raises(WorkerError) as ei:
        run_rev25_production_finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
            deps=deps,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_missing_copy_fn_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    docker = RecordingDocker()
    deps = _live_deps(docker)
    object.__setattr__(deps, "copy_fn", None)
    with pytest.raises(WorkerError) as ei:
        run_rev25_production_finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
            deps=deps,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_missing_clone_bundle_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    docker = RecordingDocker()
    deps = _live_deps(docker)
    object.__setattr__(deps, "clone_bundle", None)
    with pytest.raises(WorkerError) as ei:
        run_rev25_production_finalize(
            execution_id=bundle["execution_id"],
            review_id=review["review_id"],
            state_db=db,
            repository_root=repo,
            deps=deps,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_run_rev25_export_missing_clone_bundle_fails_frozen(tmp_path: Path) -> None:
    gen = tmp_path / "gen"
    gen.mkdir()
    docker = RecordingDocker()
    with pytest.raises(WorkerError) as ei:
        run_rev25_export(
            execution_id=EID,
            reviewed_head="f" * 40,
            authorized_baseline="f" * 40,
            staging_generation=GEN,
            worker_id=WID,
            n8n_id=NID,
            expected_image_digest=DIGEST,
            inspect_worker=lambda cid: docker.runner(["docker", "inspect", cid]) and {},
            inspect_n8n=lambda cid: {},
            list_all_ids=lambda: [WID, NID],
            observe_git=lambda: ("2" * 40, "3" * 40, "2" * 40),
            bundle_heads=lambda: [("2" * 40, "refs/heads/srl-candidate")],
            worker_generation_dir=gen,
            ledger_root=tmp_path / "ledger",
            durable_root=tmp_path / "durable",
            copy_fn=docker.copy_fn,
            recompute_diff=lambda *_: b"x",
            clone_bundle=None,
            now_ts=1,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_local_transport_fallback_attempt_refuses() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "deps.copy_fn or _copy_from_generation" not in controller
    assert "deps.clone_bundle or reconstruct_authority_c" not in controller
    tree = ast.parse(controller)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_rev25_production_finalize":
            src = ast.get_source_segment(controller, node) or ""
            assert "_copy_from_generation" not in src
            assert "or reconstruct_authority_c" not in src
        if isinstance(node, ast.FunctionDef) and node.name == "run_rev25_export":
            src = ast.get_source_segment(controller, node) or ""
            assert "clone_bundle = reconstruct_authority_c" not in src


def test_unclassified_docker_exec_fails_frozen() -> None:
    with pytest.raises(WorkerError) as ei:
        run_docker_argv(["docker", "exec", WID, "bash"])
    assert ei.value.state == "FAILED_FROZEN"


def test_docker_exec_and_inbound_cp_argv_use_exact_container_and_sealed_paths() -> None:
    mkdir = docker_exec_mkdir_argv(WID, EID, GEN)
    assert mkdir == [
        "docker",
        "exec",
        WID,
        "mkdir",
        "-p",
        f"/tmp/srl-exec/{EID}/export/{GEN}",
    ]
    cat = docker_exec_cat_argv(WID, EID, GEN, "candidate_commit")
    assert cat == [
        "docker",
        "exec",
        WID,
        "cat",
        f"/tmp/srl-exec/{EID}/export/{GEN}/candidate_commit",
    ]
    inbound = docker_cp_into_worker_argv(
        WID, EID, GEN, "candidate.bundle", Path("candidate.bundle")
    )
    assert inbound[0:2] == ["docker", "cp"]
    assert inbound[2].endswith("candidate.bundle")
    assert inbound[3] == f"{WID}:/tmp/srl-exec/{EID}/export/{GEN}/candidate.bundle"
    outbound = docker_cp_file_argv(WID, EID, GEN, "candidate.bundle", Path("out"))
    assert outbound[2] == inbound[3]


def test_no_provider_modules_on_repair4_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-must-not-be-read")
    before = {name for name in FORBIDDEN_PROVIDER_MODULES if name in sys.modules}
    docker = RecordingDocker()
    load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=docker.runner,
    )
    after = {name for name in FORBIDDEN_PROVIDER_MODULES if name in sys.modules}
    assert after == before
    for name in FORBIDDEN_PROVIDER_MODULES:
        assert name not in CONFIG.read_text(encoding="utf-8")
        assert name not in CONTROLLER.read_text(encoding="utf-8")


def test_production_does_not_bind_local_copy_helper() -> None:
    assert "_copy_from_generation" not in CONFIG.read_text(encoding="utf-8")
