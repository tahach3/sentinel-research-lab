"""Repair #3: production Rev25RuntimeDeps is built by load_runtime_config."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from tests.self_improvement_v2.test_option_a_rev25 import DIGEST, NID, RecordingDocker, WID
from tests.self_improvement_v2.test_option_a_rev25_repair2 import _ready_execution
from tools.self_improvement_v2.docker_cli import docker_inspect_argv
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.option_a_controller import Rev25RuntimeDeps, run_rev25_export
from tools.self_improvement_v2.runtime_bridge import finalize_operation
from tools.self_improvement_v2.runtime_config import load_runtime_config
from tools.self_improvement_v2.trusted_origin import PIN_REL, TRUSTED_MODULE_NAMES

REPO = Path(__file__).resolve().parents[2]
TOKEN = "test-worker-token-not-for-production"
CLI = REPO / "tools" / "self_improvement_v2" / "cli.py"
CONFIG = REPO / "tools" / "self_improvement_v2" / "runtime_config.py"
BRIDGE = REPO / "tools" / "self_improvement_v2" / "runtime_bridge.py"
FORBIDDEN_PROVIDER_MODULES = ("openai", "anthropic", "httpx", "requests")


def _operator_env(repo: Path, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    monkeypatch.setenv("SRL_STATE_DB", str(db.resolve()))
    monkeypatch.setenv("SRL_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("SRL_WORKER_HOST", "127.0.0.1")
    monkeypatch.setenv("SRL_WORKER_PORT", "0")
    monkeypatch.setenv("SRL_WORKER_CONTAINER_ID", WID)
    monkeypatch.setenv("SRL_N8N_CONTAINER_ID", NID)
    monkeypatch.setenv("SRL_WORKER_IMAGE_DIGEST", DIGEST)


def _recording_docker_runner() -> tuple[list[list[str]], object]:
    docker = RecordingDocker()
    return docker.ops, docker.runner


def test_load_runtime_config_constructs_rev25_deps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    seen, runner = _recording_docker_runner()
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=runner,
    )
    assert isinstance(config.rev25_deps, Rev25RuntimeDeps)
    assert config.rev25_deps is not None
    assert config.rev25_deps.worker_id == WID
    assert config.rev25_deps.n8n_id == NID
    assert config.rev25_deps.expected_image_digest == DIGEST
    inspected = config.rev25_deps.inspect_worker(WID)
    assert inspected["Id"] == WID
    listed = config.rev25_deps.list_all_ids()
    assert WID in listed and NID in listed
    assert any(argv[:2] == ["docker", "inspect"] for argv in seen)
    assert docker_inspect_argv(WID) in seen
    assert any(argv[:2] == ["docker", "ps"] for argv in seen)
    assert ["docker", "ps", "--all", "--quiet", "--no-trunc"] in seen


def test_load_runtime_config_missing_docker_identity_fails_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    monkeypatch.setenv("SRL_STATE_DB", str(db.resolve()))
    monkeypatch.setenv("SRL_WORKER_TOKEN", TOKEN)
    monkeypatch.delenv("SRL_WORKER_CONTAINER_ID", raising=False)
    monkeypatch.delenv("SRL_N8N_CONTAINER_ID", raising=False)
    monkeypatch.delenv("SRL_WORKER_IMAGE_DIGEST", raising=False)
    _seen, runner = _recording_docker_runner()
    with pytest.raises(WorkerError) as ei:
        load_runtime_config(
            repository_root=str(repo.resolve()),
            state_db=str(db.resolve()),
            worker_token=TOKEN,
            worker_host="127.0.0.1",
            worker_port=0,
            docker_runner=runner,
        )
    assert ei.value.state == "FAILED_FROZEN"


def test_load_runtime_config_does_not_construct_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, *_rest = _ready_execution(tmp_path, monkeypatch=monkeypatch)
    _operator_env(repo, db, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-must-not-be-read")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-must-not-be-read")
    before = {name for name in FORBIDDEN_PROVIDER_MODULES if name in sys.modules}
    seen, runner = _recording_docker_runner()
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=runner,
    )
    after = {name for name in FORBIDDEN_PROVIDER_MODULES if name in sys.modules}
    assert after == before
    blob = json.dumps(seen)
    assert "sk-test-must-not-be-read" not in blob
    assert config.rev25_deps is not None
    src = CONFIG.read_text(encoding="utf-8")
    for name in FORBIDDEN_PROVIDER_MODULES:
        assert name not in src


def test_loaded_config_finalize_reaches_rev25_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, db, _proposal, bundle, review, _store, _baseline = _ready_execution(
        tmp_path, monkeypatch=monkeypatch
    )
    _operator_env(repo, db, monkeypatch)
    _seen, runner = _recording_docker_runner()
    config = load_runtime_config(
        repository_root=str(repo.resolve()),
        state_db=str(db.resolve()),
        worker_token=TOKEN,
        worker_host="127.0.0.1",
        worker_port=0,
        docker_runner=runner,
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
    assert called == ["run_rev25_export"]
    assert result["finalization"]["candidate_commit"]


def test_loaded_config_cannot_reach_legacy_source_writing_finalize() -> None:
    config_src = CONFIG.read_text(encoding="utf-8")
    cli_src = CLI.read_text(encoding="utf-8")
    bridge_src = BRIDGE.read_text(encoding="utf-8")
    for src in (config_src, cli_src, bridge_src):
        assert "finalize_or_freeze" not in src
        assert "tools.self_improvement_v2.finalizer" not in src
    tree = ast.parse(cli_src)
    finalize_refs: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "finalize_cmd":
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    finalize_refs.add(child.id)
    assert "load_runtime_config" in finalize_refs
    assert "run_rev25_production_finalize" in finalize_refs
    assert "finalize_or_freeze" not in finalize_refs


def test_rev25_deps_not_only_in_tests() -> None:
    src = CONFIG.read_text(encoding="utf-8")
    assert "Rev25RuntimeDeps" in src
    assert "load_runtime_config" in src
    tree = ast.parse(src)
    assigned = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "Rev25RuntimeDeps":
                assigned = True
    assert assigned
    assert "tools.self_improvement_v2.runtime_config" in TRUSTED_MODULE_NAMES
    assert (REPO / PIN_REL).is_file()
