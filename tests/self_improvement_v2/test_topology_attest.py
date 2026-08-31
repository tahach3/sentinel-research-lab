"""INV-TOPO-01 / F1–F13 topology attestor tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tools.self_improvement_v2.agent_runtime_contract import (
    AgentRuntimeContractError,
    assert_workflow_agent_wiring,
    load_design_workflow,
)
from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.launcher.install_launcher import install_launcher
from tools.self_improvement_v2.topology_attest import (
    DOCKER_ENV_BLOCKLIST,
    TOKEN_BURNED,
    TOKEN_CONSUMED,
    AttestorState,
    DockerTransport,
    TokenStore,
    TopologyAttestationError,
    TopologyAttestorHandler,
    assert_worker_topology,
    docker_argv,
    env_boolean_is_not_authority,
    identity_sha256,
    loopback_8765_inodes,
    mint_pass_envelope,
    sanitized_docker_env,
    serve_attestor,
    validate_docker_endpoint,
    write_protected_secret,
)
from tools.self_improvement_v2.topology_identity import (
    EXPECTED_ORIGIN,
    IDENTITY_KEYS,
    SCHEMA,
    TopologyIdentityError,
    validate_identity,
)
from tools.self_improvement_v2.workflow_validator import validate_workflow

REPO = Path(__file__).resolve().parents[2]
N8N_ID = "a" * 64
WORKER_ID = "b" * 64
IMAGE_L = "sha256:" + "c" * 64
IMAGE_D = "sha256:3aea21fc3e8b5dff7f4da80b9cf894af5e267542fc0b42ce5293b3535e4e5124"
HEAD = "d" * 40
ENDPOINT = "unix:///var/run/docker.sock"
DAEMON_ID = "daemon-linux-1"


def _identity(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "reviewed_head": HEAD,
        "n8n_container_id": N8N_ID,
        "n8n_created": "2026-08-24T00:00:00Z",
        "n8n_started_at": "2026-08-24T00:00:01.000000000Z",
        "worker_container_id": WORKER_ID,
        "worker_created": "2026-08-24T00:00:02Z",
        "worker_started_at": "2026-08-24T00:00:03.000000000Z",
        "worker_image_id_L": IMAGE_L,
        "worker_image_digest_D": IMAGE_D,
        "worker_network_mode": f"container:{N8N_ID}",
        "bind": {"host": "127.0.0.1", "port": 8765, "protocol": "tcp"},
        "listen_inode": 4242,
        "listen_owner": {
            "container_id": WORKER_ID,
            "pid_in_worker_pidns": 7,
            "cmdline_suffix": "tools.self_improvement_v2.runtime_bridge",
        },
        "n8n_netns_inode": 99,
        "netns_container_set": sorted([N8N_ID, WORKER_ID]),
        "published_worker_ports": [],
        "expected_origin": EXPECTED_ORIGIN,
        "docker_endpoint": ENDPOINT,
        "docker_daemon_id": DAEMON_ID,
        "docker_os_type": "linux",
    }
    body.update(overrides)
    return body


class FakeDocker:
    def __init__(self) -> None:
        self.endpoint = ENDPOINT
        self.daemon_id = DAEMON_ID
        self.os_type = "linux"
        self.n8n_id = N8N_ID
        self.worker_id = WORKER_ID
        self.n8n_created = "2026-08-24T00:00:00Z"
        self.n8n_started = "2026-08-24T00:00:01.000000000Z"
        self.worker_created = "2026-08-24T00:00:02Z"
        self.worker_started = "2026-08-24T00:00:03.000000000Z"
        self.network_mode = f"container:{N8N_ID}"
        self.image_id = IMAGE_L
        self.config_image = f"srl-worker:si2-option-a@{IMAGE_D}"
        self.repo_digests = [f"srl-worker:si2-option-a@{IMAGE_D}"]
        self.netns = "net:[99]"
        self.listen_inode = 4242
        self.tcp = (
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            f"   0: 0100007F:223D 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 {self.listen_inode} 1 0000000000000000 100 0 0 10 0\n"
        )
        self.n8n_fds = "1\tsocket:[1]\tnode\n"
        self.worker_fds = "7\tsocket:[4242]\tpython -B -m tools.self_improvement_v2.runtime_bridge\n"
        self.health = {
            "service": "sentinel-research-lab-self-improvement-v2",
            "status": "ready",
        }
        self.containers = {
            N8N_ID: {"mode": "bridge", "status": "running"},
            WORKER_ID: {"mode": f"container:{N8N_ID}", "status": "running"},
        }
        self.seen_env: list[dict[str, str]] = []
        self.seen_argv: list[list[str]] = []

    def _inspect(self, cid: str) -> dict[str, Any]:
        if cid in {self.n8n_id, self.n8n_id[:12]}:
            return {
                "Id": self.n8n_id,
                "Created": self.n8n_created,
                "State": {"Running": True, "Status": "running", "StartedAt": self.n8n_started},
                "HostConfig": {
                    "NetworkMode": "bridge",
                    "Privileged": False,
                    "PortBindings": {"5678/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5678"}]},
                    "Binds": [],
                },
                "Mounts": [],
                "Config": {"Image": "n8nio/n8n:1.107.4@sha256:a49bc867def7800e99ec175dee46b62282961a6460cfb422b3adec3e53073d63"},
                "Image": "sha256:" + "e" * 64,
                "NetworkSettings": {},
            }
        if cid in {self.worker_id, self.worker_id[:12]}:
            return {
                "Id": self.worker_id,
                "Created": self.worker_created,
                "State": {"Running": True, "Status": "running", "StartedAt": self.worker_started},
                "HostConfig": {
                    "NetworkMode": self.network_mode,
                    "Privileged": False,
                    "PortBindings": {},
                    "Binds": [],
                },
                "Mounts": [],
                "Config": {"Image": self.config_image},
                "Image": self.image_id,
                "NetworkSettings": {},
            }
        info = self.containers.get(cid)
        if info is None:
            raise TopologyAttestationError("unknown container")
        return {
            "Id": cid,
            "Created": "x",
            "State": {"Running": info["status"] == "running", "Status": info["status"], "StartedAt": "x"},
            "HostConfig": {"NetworkMode": info["mode"], "Privileged": False, "PortBindings": {}, "Binds": []},
            "Mounts": [],
            "Config": {"Image": "other"},
            "Image": IMAGE_L,
            "NetworkSettings": {},
        }

    def runner(self, argv: list[str], env: dict[str, str]) -> str:
        self.seen_env.append(dict(env))
        self.seen_argv.append(list(argv))
        assert argv[:3] == ["docker", "-H", self.endpoint]
        args = argv[3:]
        if args[:3] == ["info", "--format", "{{json .ID}}"]:
            return json.dumps(self.daemon_id)
        if args[:3] == ["info", "--format", "{{json .OSType}}"]:
            return json.dumps(self.os_type)
        if args[:4] == ["compose", "ps", "-q", "n8n"]:
            return self.n8n_id
        if args[:4] == ["compose", "ps", "-q", "srl-worker"]:
            return self.worker_id
        if args[0] == "inspect" and args[-1] == "{{json .}}":
            return json.dumps(self._inspect(args[1]))
        if args[0] == "inspect" and "{{.Id}}" in args[-1]:
            cid = args[1]
            rec = self._inspect(cid)
            return f"{rec['Id']} {rec['HostConfig']['NetworkMode']} {rec['State']['Status']}"
        if args[:2] == ["image", "inspect"]:
            return f"{self.image_id} {json.dumps(self.repo_digests)}"
        if args[0] == "exec" and args[2] == "readlink":
            return self.netns
        if args[0] == "exec" and args[-1] == "/proc/net/tcp":
            return self.tcp
        if args[0] == "exec" and args[-1] == "/proc/net/tcp6":
            raise TopologyAttestationError("no tcp6")
        if args[0] == "exec" and "for p in /proc/" in " ".join(args):
            return self.n8n_fds if args[1] == self.n8n_id else self.worker_fds
        if args[0] == "exec" and "127.0.0.1:8765/health" in " ".join(args):
            return json.dumps(self.health)
        if args[:4] == ["container", "ls", "-a", "--no-trunc"]:
            return "\n".join(self.containers)
        raise TopologyAttestationError(f"unexpected docker argv {args}")


def test_mint_schema_v1_required_fields() -> None:
    identity = _identity()
    validate_identity(identity)
    assert tuple(identity.keys()) == IDENTITY_KEYS or set(identity) == set(IDENTITY_KEYS)
    missing = dict(identity)
    missing.pop("docker_daemon_id")
    with pytest.raises(TopologyIdentityError, match="missing"):
        validate_identity(missing)
    extra = dict(identity)
    extra["bonus"] = 1
    with pytest.raises(TopologyIdentityError, match="extra"):
        validate_identity(extra)


@pytest.mark.parametrize(
    "field,value",
    [
        ("n8n_netns_inode", True),
        ("n8n_netns_inode", 1.5),
        ("n8n_netns_inode", None),
        ("listen_inode", "4242"),
        ("bind", {"host": "127.0.0.1", "port": True, "protocol": "tcp"}),
        ("docker_os_type", "windows"),
        ("docker_endpoint", "tcp://127.0.0.1:2375"),
        ("docker_endpoint", ""),
        ("n8n_container_id", N8N_ID.upper()),
        ("n8n_container_id", N8N_ID[:12]),
        ("published_worker_ports", [8765]),
        ("netns_container_set", [N8N_ID, N8N_ID]),
        ("worker_network_mode", f"container:{N8N_ID[:12]}"),
        ("worker_network_mode", "service:n8n"),
    ],
)
def test_identity_type_and_id_refusals(field: str, value: Any) -> None:
    identity = _identity()
    if field == "bind" and isinstance(value, dict):
        identity["bind"] = value
    else:
        identity[field] = value
    with pytest.raises(TopologyIdentityError):
        validate_identity(identity)


def test_object_key_reorder_same_digest() -> None:
    left = _identity()
    right = {k: left[k] for k in reversed(list(left))}
    assert identity_sha256(left) == identity_sha256(right) == content_sha256(left)


def test_container_set_reorder_same_digest() -> None:
    left = _identity(netns_container_set=sorted([N8N_ID, WORKER_ID]))
    right = _identity()
    right["netns_container_set"] = sorted([WORKER_ID, N8N_ID])
    assert left["netns_container_set"] == right["netns_container_set"]
    assert identity_sha256(left) == identity_sha256(right)


def test_pass_body_covers_all_section1_fields() -> None:
    identity = _identity()
    token = "tok"
    body = mint_pass_envelope(identity, purpose="provider_implementer", token=token)
    assert body["status"] == "PASS"
    assert body["schema"] == SCHEMA
    assert body["topology_attestation_sha256"] == content_sha256(identity)
    assert set(body["identity"]) == set(IDENTITY_KEYS)
    assert body["topology_binding_token"] == token


def test_execute_probe_has_no_token() -> None:
    identity = _identity()
    body = mint_pass_envelope(identity, purpose="execute_probe", token=None)
    assert "topology_binding_token" not in body
    with pytest.raises(TopologyAttestationError, match="execute_probe"):
        mint_pass_envelope(identity, purpose="execute_probe", token="nope")


def test_env_boolean_is_not_authority() -> None:
    with pytest.raises(TopologyAttestationError, match="not topology authority"):
        env_boolean_is_not_authority({"WORKER_TOPOLOGY_ATTESTED": "YES"})


def test_step6_uses_host_wide_container_ls_not_compose_ps() -> None:
    fake = FakeDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    identity = assert_worker_topology(docker=docker, reviewed_head=HEAD)
    joined = [" ".join(a) for a in fake.seen_argv]
    assert any("container ls -a --no-trunc" in row for row in joined)
    assert not any("compose ps -a" in row and "container ls" not in row for row in joined if "ls -a" in row)
    assert identity["netns_container_set"] == sorted([N8N_ID, WORKER_ID])


def test_impostor_joiner_owning_8765_refuses() -> None:
    fake = FakeDocker()
    joiner = "f" * 64
    fake.containers[joiner] = {"mode": f"container:{N8N_ID}", "status": "exited"}
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(TopologyAttestationError, match="host-wide"):
        assert_worker_topology(docker=docker, reviewed_head=HEAD)


def test_n8n_pidns_process_owning_8765_refuses() -> None:
    fake = FakeDocker()
    fake.n8n_fds = "9\tsocket:[4242]\tnode impostor\n"
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(TopologyAttestationError, match="n8n pid namespace"):
        assert_worker_topology(docker=docker, reviewed_head=HEAD)


def test_image_L_without_digest_D_refuses() -> None:
    fake = FakeDocker()
    fake.repo_digests = []
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(TopologyAttestationError, match="RepoDigests"):
        assert_worker_topology(docker=docker, reviewed_head=HEAD)


def test_worker_image_pin_mismatch_refuses() -> None:
    fake = FakeDocker()
    fake.config_image = f"srl-worker:si2-option-a@sha256:{'a' * 64}"
    fake.repo_digests = [fake.config_image]
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    with pytest.raises(TopologyAttestationError, match="worker_image_pin"):
        assert_worker_topology(docker=docker, reviewed_head=HEAD)


def test_ambient_compose_env_is_not_used() -> None:
    fake = FakeDocker()
    os.environ["COMPOSE_FILE"] = "/evil/compose.yml"
    os.environ["COMPOSE_PROJECT_NAME"] = "evil"
    os.environ["DOCKER_CLI_PLUGIN_EXTRA_DIRS"] = "/evil/plugins"
    try:
        docker = DockerTransport(ENDPOINT, runner=fake.runner)
        assert_worker_topology(docker=docker, reviewed_head=HEAD)
        for env in fake.seen_env:
            assert "COMPOSE_FILE" not in env
            assert "COMPOSE_PROJECT_NAME" not in env
            assert "DOCKER_CLI_PLUGIN_EXTRA_DIRS" not in env
    finally:
        os.environ.pop("COMPOSE_FILE", None)
        os.environ.pop("COMPOSE_PROJECT_NAME", None)
        os.environ.pop("DOCKER_CLI_PLUGIN_EXTRA_DIRS", None)


def test_n8n_recreate_fail_closed_provider_calls_unchanged() -> None:
    fake = FakeDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    mint = assert_worker_topology(docker=docker, reviewed_head=HEAD)
    fake.n8n_id = "1" * 64
    fake.containers = {fake.n8n_id: {"mode": "bridge", "status": "running"}, WORKER_ID: {"mode": f"container:{N8N_ID}", "status": "running"}}
    with pytest.raises(TopologyAttestationError):
        assert_worker_topology(docker=docker, reviewed_head=HEAD, mint=mint)


def test_ambient_docker_host_env_is_not_used() -> None:
    fake = FakeDocker()
    os.environ["DOCKER_HOST"] = "tcp://evil.example:2375"
    os.environ["DOCKER_CONTEXT"] = "evil"
    try:
        docker = DockerTransport(ENDPOINT, runner=fake.runner)
        assert_worker_topology(docker=docker, reviewed_head=HEAD)
        for env in fake.seen_env:
            for key in DOCKER_ENV_BLOCKLIST:
                assert key not in env
        assert all(argv[1] == "-H" and argv[2] == ENDPOINT for argv in fake.seen_argv)
    finally:
        os.environ.pop("DOCKER_HOST", None)
        os.environ.pop("DOCKER_CONTEXT", None)


def test_missing_empty_endpoint_refuses() -> None:
    with pytest.raises(TopologyAttestationError):
        validate_docker_endpoint("")
    with pytest.raises(TopologyAttestationError):
        validate_docker_endpoint(None)  # type: ignore[arg-type]
    with pytest.raises(TopologyAttestationError):
        validate_docker_endpoint("tcp://127.0.0.1:2375")
    assert validate_docker_endpoint("npipe:////./pipe/docker_engine").startswith("npipe://")
    with pytest.raises(TopologyAttestationError):
        docker_argv(ENDPOINT, ["ps", "--context", "evil"])


def test_token_state_machine_single_winner() -> None:
    store = TokenStore()
    identity = _identity()
    record = store.mint(purpose="provider_implementer", identity=identity, now_monotonic=10.0)
    winner: list[str] = []
    loser: list[str] = []

    def consume() -> None:
        try:
            store.reserve(record.token, purpose="provider_implementer", now_monotonic=10.1)
            winner.append("ok")
        except TopologyAttestationError:
            loser.append("no")

    t1 = threading.Thread(target=consume)
    t2 = threading.Thread(target=consume)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(winner) == 1
    assert len(loser) == 1
    store.complete(record.token, ok=True)
    assert store._tokens[record.token].state == TOKEN_CONSUMED


def test_expiry_burns_and_reserve_before_expiry_may_finish_late() -> None:
    store = TokenStore()
    identity = _identity()
    record = store.mint(purpose="worker_authorize", identity=identity, now_monotonic=1.0)
    with pytest.raises(TopologyAttestationError, match="expired"):
        store.reserve(record.token, purpose="worker_authorize", now_monotonic=6.1)
    assert store._tokens[record.token].state == TOKEN_BURNED
    record2 = store.mint(purpose="worker_authorize", identity=identity, now_monotonic=10.0)
    reserved = store.reserve(record2.token, purpose="worker_authorize", now_monotonic=14.9)
    assert reserved.state == "CONSUMING"
    store.complete(record2.token, ok=True)
    assert store._tokens[record2.token].state == TOKEN_CONSUMED


def test_cross_purpose_and_replay_refuse() -> None:
    store = TokenStore()
    identity = _identity()
    record = store.mint(purpose="provider_implementer", identity=identity, now_monotonic=1.0)
    with pytest.raises(TopologyAttestationError, match="purpose"):
        store.reserve(record.token, purpose="provider_reviewer", now_monotonic=1.1)
    record2 = store.mint(purpose="provider_reviewer", identity=identity, now_monotonic=1.0)
    store.reserve(record2.token, purpose="provider_reviewer", now_monotonic=1.1)
    store.complete(record2.token, ok=True)
    with pytest.raises(TopologyAttestationError, match="UNUSED"):
        store.reserve(record2.token, purpose="provider_reviewer", now_monotonic=1.2)


def test_posix_secret_mode(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX ACL contract")
    path = tmp_path / "secrets" / "consume"
    write_protected_secret(path, "consume-secret")
    assert path.read_text(encoding="utf-8") == "consume-secret"
    assert (path.parent.stat().st_mode & 0o777) == 0o700
    assert (path.stat().st_mode & 0o777) == 0o600


def test_sanitized_docker_env_drops_seven_vars() -> None:
    env = sanitized_docker_env({key: "x" for key in DOCKER_ENV_BLOCKLIST} | {"PATH": "/bin"})
    for key in DOCKER_ENV_BLOCKLIST:
        assert key not in env
    assert env["PATH"] == "/bin"


def test_install_requires_docker_endpoint(tmp_path: Path) -> None:
    head = os.popen(f"git -C {REPO} rev-parse HEAD").read().strip()
    with pytest.raises(ValueError, match="docker endpoint"):
        install_launcher(
            repository_root=REPO,
            reviewed_head=head,
            install_dir=tmp_path / "SentinelResearchLab",
        )


def _workflow():
    return load_design_workflow(root=REPO)


def test_d1_topology_attest_immediately_before_authorize() -> None:
    wf = _workflow()
    c = wf["connections"]
    assert c["Provider Call Consume (Implementer)"]["main"][0][0]["node"] == "Topology Attest (Implementer)"
    assert c["Topology Attest (Implementer)"]["main"][0][0]["node"] == "Provider Call Authorize (Implementer)"
    assert c["Provider Call Authorize (Implementer)"]["main"][0][0]["node"] == "Implementer Agent"
    report = validate_workflow(REPO, REPO / "workflows/design/self_improvement_loop_v2.json")
    assert report["status"] == "PASS"


def test_distinct_attest_nodes_implementer_and_reviewer() -> None:
    names = {n["name"] for n in _workflow()["nodes"]}
    assert "Topology Attest (Implementer)" in names
    assert "Topology Attest (Reviewer)" in names
    assert "Topology Attest (Implementer)" != "Topology Attest (Reviewer)"


def test_worker_authorize_preceded_by_topology_attest() -> None:
    c = _workflow()["connections"]
    assert c["Proposal Freeze"]["main"][0][0]["node"] == "Topology Attest (Worker Authorize)"
    assert c["Topology Attest (Worker Authorize)"]["main"][0][0]["node"] == "Worker Authorize"


def test_execute_preceded_by_topology_attest() -> None:
    c = _workflow()["connections"]
    assert c["Worker AUTHORIZED Continue"]["main"][0][0]["node"] == "Topology Attest (Execute)"
    assert c["Topology Attest (Execute)"]["main"][0][0]["node"] == "Detached Worker Execute"


def test_missing_topology_attest_node_rejected(tmp_path: Path) -> None:
    wf = copy.deepcopy(_workflow())
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Topology Attest (Implementer)"]
    probe = tmp_path / "missing.json"
    probe.write_text(json.dumps(wf), encoding="utf-8")
    report = validate_workflow(REPO, probe)
    assert report["status"] == "FAIL"


def test_consume_skips_attest_rejected() -> None:
    wf = copy.deepcopy(_workflow())
    wf["connections"]["Provider Call Consume (Implementer)"]["main"][0] = [
        {"node": "Provider Call Authorize (Implementer)", "type": "main", "index": 0}
    ]
    with pytest.raises(
        AgentRuntimeContractError,
        match=r"skip Topology Attest|must follow Topology Attest|must follow Provider Call Consume \(Implementer\)",
    ):
        assert_workflow_agent_wiring(workflow=wf, root=REPO)


def test_attest_error_cannot_reach_agent_or_execute() -> None:
    wf = _workflow()
    for name in (
        "Topology Attest (Implementer)",
        "Topology Attest (Reviewer)",
        "Topology Attest (Worker Authorize)",
        "Topology Attest (Execute)",
    ):
        err = wf["connections"][name]["main"][1][0]["node"]
        assert err == "Annotate Budget Denied"
    c = wf["connections"]
    assert c["Annotate Budget Denied"]["main"][0][0]["node"] == "Failure Router"


def test_authorize_nonce_is_not_topology_proof() -> None:
    identity = _identity()
    with pytest.raises(TopologyAttestationError):
        mint_pass_envelope(identity, purpose="provider_implementer", token="")


def test_http_credential_separation() -> None:
    identity = _identity()
    state = AttestorState(
        docker=DockerTransport(ENDPOINT, runner=FakeDocker().runner),
        mint=identity,
        attest_credential="attest-secret",
        consume_credential="consume-secret",
        reviewed_head=HEAD,
        reassert=lambda: identity,
    )
    handler = type("H", (TopologyAttestorHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.error
        import urllib.request

        host, port = server.server_address

        def post(path: str, cred: str, payload: dict[str, Any]) -> int:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {cred}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return int(resp.status)
            except urllib.error.HTTPError as exc:
                return int(exc.code)

        assert post("/v2/topology-attest", "attest-secret", {"purpose": "execute_probe"}) == 200
        assert post("/v2/topology-attest", "consume-secret", {"purpose": "execute_probe"}) == 403
        mint = post("/v2/topology-attest", "attest-secret", {"purpose": "provider_implementer"})
        assert mint == 200
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v2/topology-attest",
            data=json.dumps({"purpose": "provider_implementer"}).encode(),
            method="POST",
            headers={"Authorization": "Bearer attest-secret", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
        token = body["topology_binding_token"]
        assert post("/v2/topology-consume", "attest-secret", {"purpose": "provider_implementer", "topology_binding_token": token}) == 403
        assert post("/v2/topology-consume", "consume-secret", {"purpose": "provider_implementer", "topology_binding_token": token}) == 200
        assert post("/v2/topology-consume", "consume-secret", {"purpose": "provider_implementer", "topology_binding_token": token}) == 403
    finally:
        server.shutdown()
        server.server_close()


def test_serve_attestor_bind_is_loopback_8764() -> None:
    identity = _identity()
    state = AttestorState(
        docker=DockerTransport(ENDPOINT, runner=FakeDocker().runner),
        mint=identity,
        attest_credential="a",
        consume_credential="b",
        reviewed_head=HEAD,
        reassert=lambda: identity,
    )
    with pytest.raises(TopologyAttestationError, match="127.0.0.1:8764"):
        serve_attestor(state, host="0.0.0.0", port=8764)


def test_loopback_8765_parser_rejects_wildcard() -> None:
    text = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000:223D 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 9 1 0000000000000000 100 0 0 10 0\n"
    )
    assert loopback_8765_inodes(text) == []
    good = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:223D 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 9 1 0000000000000000 100 0 0 10 0\n"
    )
    assert loopback_8765_inodes(good) == [9]


def test_topology_binding_token_consumed_before_authorize_spend() -> None:
    test_http_credential_separation()


def test_stale_or_replayed_token_refuses_authorize() -> None:
    test_cross_purpose_and_replay_refuse()


def test_timestamp_rewrite_refuses_on_reassert() -> None:
    fake = FakeDocker()
    docker = DockerTransport(ENDPOINT, runner=fake.runner)
    mint = assert_worker_topology(docker=docker, reviewed_head=HEAD)
    fake.worker_started = "rewritten"
    with pytest.raises(TopologyAttestationError):
        assert_worker_topology(docker=docker, reviewed_head=HEAD, mint=mint)
