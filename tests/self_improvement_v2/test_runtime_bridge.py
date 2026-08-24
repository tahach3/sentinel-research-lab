"""Offline loopback verification for the Self-Improvement V2 runtime bridge."""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import build_pass_review, build_proposal, init_temp_repo, run
from tools.self_improvement_v2.git_worker import source_tree_fingerprint
from tools.self_improvement_v2.runtime_bridge import LoopbackServer, configure_logging
from tools.self_improvement_v2.runtime_config import MAX_REQUEST_BYTES, load_runtime_config, redact_log_text


TOKEN = "test-worker-token-not-for-production"
ALT_TOKEN = "different-invalid-token-value"


@pytest.fixture()
def bridge_env(tmp_path: Path):
    """Disposable checkout that is ALSO the trusted install root (R4).

    Server runs in a subprocess so parent pytest sys.modules stay clean.
    """
    import os
    import subprocess
    import sys
    import time

    repo = tmp_path / "sentinel-research-lab"
    baseline = init_temp_repo(repo, include_worker_package=True)
    state_db = tmp_path / "runtime" / "v2-state.sqlite"
    state_db.parent.mkdir(parents=True, exist_ok=True)
    root = str(repo.resolve())
    boot = tmp_path / "boot_bridge.py"
    boot.write_text(
        "import os, sys\n"
        f"os.environ['SRL_REPOSITORY_ROOT'] = {root!r}\n"
        f"os.environ['SRL_REVIEWED_HEAD'] = {baseline!r}\n"
        f"os.environ['SRL_WORKER_TOKEN'] = {TOKEN!r}\n"
        "os.environ['PYTHONDONTWRITEBYTECODE'] = '1'\n"
        f"sys.path.insert(0, {root!r})\n"
        "from tools.self_improvement_v2.runtime_config import load_runtime_config\n"
        "from tools.self_improvement_v2 import runtime_bridge as rb\n"
        "rb.consume_topology_binding_token = lambda **k: {'status': 'PASS'}\n"
        "from tools.self_improvement_v2.runtime_bridge import LoopbackServer\n"
        "config = load_runtime_config(\n"
        f"    repository_root={root!r},\n"
        f"    state_db={str(state_db.resolve())!r},\n"
        f"    worker_token={TOKEN!r},\n"
        "    worker_host='127.0.0.1',\n"
        "    worker_port=0,\n"
        ")\n"
        "server = LoopbackServer(config)\n"
        "server.start_background()\n"
        "print('READY ' + server.base_url, flush=True)\n"
        "server._thread.join()\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "SRL_REPOSITORY_ROOT": root,
        "SRL_REVIEWED_HEAD": baseline,
        "SRL_WORKER_TOKEN": TOKEN,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    proc = subprocess.Popen(
        [sys.executable, str(boot)],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    base = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"bridge boot failed: rc={proc.returncode} err={err[:2000]}")
        if line.startswith("READY "):
            base = line.split(" ", 1)[1].strip()
            break
    if not base:
        proc.kill()
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"bridge boot timeout err={err[:2000]}")
    try:
        yield {
            "proc": proc,
            "base": base,
            "repo": repo,
            "baseline": baseline,
            "state_db": state_db,
            "token": TOKEN,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _request(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = TOKEN,
    payload: dict | None = None,
    raw: bytes | None = None,
    content_type: str = "application/json; charset=utf-8",
) -> tuple[int, dict | str]:
    data = raw
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — loopback only in tests
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed: dict | str = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


def test_01_health_response(bridge_env):
    status, body = _request(bridge_env["base"], "GET", "/health", token=None)
    assert status == 200
    assert body["service"] == "sentinel-research-lab-self-improvement-v2"
    assert body["version"] == "2"
    assert body["status"] == "ready"
    assert body["repository_id"] == "sentinel-research-lab"
    assert "validate-proposal" in body["capabilities"]
    assert "token" not in json.dumps(body).lower()
    assert "C:\\" not in json.dumps(body)
    assert "/Users/" not in json.dumps(body)


def test_02_missing_token(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/validate-proposal",
        token=None,
        payload={"proposal": build_proposal(bridge_env["baseline"])},
    )
    assert status == 401
    assert body["status"] == "FAIL"


def test_03_invalid_token(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/validate-proposal",
        token=ALT_TOKEN,
        payload={"proposal": build_proposal(bridge_env["baseline"])},
    )
    assert status == 401
    assert body["status"] == "FAIL"
    assert ALT_TOKEN not in json.dumps(body)
    assert TOKEN not in json.dumps(body)


def test_04_oversized_body(bridge_env):
    huge = b'{"proposal":{"x":"' + (b"a" * (MAX_REQUEST_BYTES + 100)) + b'"}}'
    status, body = _request(bridge_env["base"], "POST", "/v2/validate-proposal", raw=huge)
    assert status == 413
    assert body["status"] == "FAIL"


def test_05_malformed_json(bridge_env):
    status, body = _request(bridge_env["base"], "POST", "/v2/validate-proposal", raw=b"{not-json")
    assert status == 400
    assert body["status"] == "FAIL"


def test_06_unknown_fields(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/validate-proposal",
        payload={"proposal": build_proposal(bridge_env["baseline"]), "extra": True},
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_07_caller_supplied_repository_root(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/validate-proposal",
        payload={
            "proposal": build_proposal(bridge_env["baseline"]),
            "repository_root": str(bridge_env["repo"]),
        },
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_08_caller_supplied_database_path(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/execute",
        payload={
            "proposal": build_proposal(bridge_env["baseline"]),
            "state_db": str(bridge_env["state_db"]),
        },
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_09_caller_supplied_command(bridge_env):
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/execute",
        payload={
            "proposal": build_proposal(bridge_env["baseline"]),
            "command": "git status",
        },
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_10_non_low_proposal(bridge_env):
    proposal = build_proposal(bridge_env["baseline"], risk_level="HIGH")
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/execute",
        payload={"proposal": proposal},
    )
    assert status == 400
    assert body["status"] == "FAIL"
    assert body.get("final_state") in {"DECISION_REQUIRED", "POLICY_REJECTED"} or body.get("error")


def test_11_baseline_mismatch(bridge_env):
    proposal = build_proposal("0" * 40)
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/execute",
        payload={"proposal": proposal},
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_12_successful_proposal_validation(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/validate-proposal",
        payload={"proposal": proposal, "topology_binding_token": "test-topology-token"},
    )
    assert status == 200
    assert body["status"] == "PASS"
    assert body["proposal_id"] == proposal["proposal_id"]
    assert len(body["proposal_sha256"]) == 64


def test_13_successful_execution(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/execute",
        payload={"proposal": proposal},
    )
    assert status == 200
    assert body["status"] == "PASS"
    execution = body["execution"]
    assert execution["final_state"] == "REVIEW_PENDING"
    assert execution.get("worktree_path_redacted") == "<redacted>"
    assert "worktree_path" not in execution or execution.get("worktree_path") in (None, "<redacted>")
    branches = run(["git", "branch", "--list", "self-improvement-v2/*"], bridge_env["repo"]).stdout.strip()
    assert branches == ""


def test_14_finalization_without_review(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution_id = exec_body["execution"]["execution_id"]
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution_id, "review_id": "missing-review"},
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_15_finalization_with_invalid_review(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution = exec_body["execution"]
    review = build_pass_review(execution, proposal)
    review["actual_diff_sha256"] = "f" * 64
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution["execution_id"], "review_id": review["review_id"], "review": review},
    )
    assert status == 400
    assert body["status"] == "FAIL"


def test_16_successful_bound_finalization(bridge_env):
    before = source_tree_fingerprint(bridge_env["repo"])
    proposal = build_proposal(bridge_env["baseline"])
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution = exec_body["execution"]
    review = build_pass_review(execution, proposal)
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution["execution_id"], "review_id": review["review_id"], "review": review},
    )
    assert status == 200
    assert body["status"] == "PASS"
    finalization = body["finalization"]
    assert finalization["final_state"] == "READY_FOR_HUMAN_PROMOTION"
    assert finalization["candidate_commit"]
    assert finalization["candidate_branch"]
    assert source_tree_fingerprint(bridge_env["repo"]) == before


def test_17_duplicate_finalization(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution = exec_body["execution"]
    review = build_pass_review(execution, proposal)
    first = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution["execution_id"], "review_id": review["review_id"], "review": review},
    )
    second = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution["execution_id"], "review_id": review["review_id"], "review": review},
    )
    assert first[0] == 200
    assert second[0] == 200
    assert first[1]["finalization"]["candidate_commit"] == second[1]["finalization"]["candidate_commit"]


def test_18_no_push_or_merge(bridge_env):
    proposal = build_proposal(bridge_env["baseline"])
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution = exec_body["execution"]
    review = build_pass_review(execution, proposal)
    status, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/finalize",
        payload={"execution_id": execution["execution_id"], "review_id": review["review_id"], "review": review},
    )
    assert status == 200
    remotes = run(["git", "remote"], bridge_env["repo"]).stdout.strip()
    assert remotes == ""
    # Candidate exists locally only; source HEAD unchanged.
    head = run(["git", "rev-parse", "HEAD"], bridge_env["repo"]).stdout.strip()
    assert head == bridge_env["baseline"]
    blob = json.dumps(body).lower()
    assert "git push" not in blob
    assert "git merge" not in blob


def test_19_source_checkout_unchanged(bridge_env):
    before = source_tree_fingerprint(bridge_env["repo"])
    proposal = build_proposal(bridge_env["baseline"], proposal_id="prop-unchanged-1", candidate_id="cand-unchanged-1")
    _, exec_body = _request(bridge_env["base"], "POST", "/v2/execute", payload={"proposal": proposal})
    execution_id = exec_body["execution"]["execution_id"]
    status, body = _request(bridge_env["base"], "GET", f"/v2/executions/{execution_id}")
    assert status == 200
    assert body["execution_id"] == execution_id
    assert body["execution"]["worktree_path_redacted"] == "<redacted>"
    assert "worktree_path" not in body["execution"]
    assert source_tree_fingerprint(bridge_env["repo"]) == before
    head = run(["git", "rev-parse", "HEAD"], bridge_env["repo"]).stdout.strip()
    assert head == bridge_env["baseline"]


def test_20_token_absent_from_logs_and_responses(bridge_env, caplog):
    configure_logging()
    logger = logging.getLogger("self_improvement_v2.runtime_bridge")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.INFO):
            status, body = _request(
                bridge_env["base"],
                "POST",
                "/v2/validate-proposal",
                token=ALT_TOKEN,
                payload={"proposal": build_proposal(bridge_env["baseline"])},
            )
        assert status == 401
        response_text = json.dumps(body)
        log_text = stream.getvalue() + caplog.text
        redacted = redact_log_text(f"Authorization: Bearer {TOKEN}")
        assert TOKEN not in response_text
        assert ALT_TOKEN not in response_text
        assert TOKEN not in log_text
        assert ALT_TOKEN not in log_text
        assert TOKEN not in redacted
        assert "[REDACTED]" in redacted
    finally:
        logger.removeHandler(handler)


def test_bind_rejects_public_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "sentinel-research-lab"
    init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    with pytest.raises(Exception):
        load_runtime_config(
            repository_root=str(repo),
            state_db=str(tmp_path / "db.sqlite"),
            worker_token=TOKEN,
            worker_host="0.0.0.0",
            worker_port=8765,
        )


def test_state_db_inside_repo_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "sentinel-research-lab"
    init_temp_repo(repo)
    monkeypatch.setenv("SRL_REPOSITORY_ROOT", str(repo.resolve()))
    with pytest.raises(Exception):
        load_runtime_config(
            repository_root=str(repo),
            state_db=str(repo / "state.sqlite"),
            worker_token=TOKEN,
            worker_host="127.0.0.1",
            worker_port=8765,
        )


def test_provider_call_permit_refuses_seventh_call(bridge_env):
    """Live-path adversarial proof: bridge refuses the 7th provider-call permit."""
    status, opened = _request(
        bridge_env["base"],
        "POST",
        "/v2/budget/open",
        payload={"session_id": "bridge-budget-1"},
    )
    assert status == 200
    assert opened["status"] == "PASS"
    assert opened["max_calls"] == 6
    assert opened["worst_case_usd"] < 5.0
    sid = opened["session_id"]
    for _ in range(6):
        st, body = _request(
            bridge_env["base"],
            "POST",
            "/v2/provider-call-permit",
            payload={"session_id": sid, "role": "implementer"},
        )
        assert st == 200
        assert body["permit"]["status"] == "GRANTED"
        assert body["permit"]["provider_call_params"]["max_output_tokens"] >= 1
        assert body["permit"]["permit_nonce"]
    st, body = _request(
        bridge_env["base"],
        "POST",
        "/v2/provider-call-permit",
        payload={"session_id": sid, "role": "implementer"},
    )
    assert st == 400
    assert body["error"] == "PILOT_CALL_LIMIT"


def test_wall_capture_and_assert_via_bridge(bridge_env):
    status, captured = _request(bridge_env["base"], "POST", "/v2/wall/capture", payload={})
    assert status == 200
    snap = captured["snapshot"]
    status, asserted = _request(
        bridge_env["base"],
        "POST",
        "/v2/wall/assert",
        payload={"before": snap},
    )
    assert status == 200
    assert asserted["status"] == "PASS"
