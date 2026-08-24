"""Host topology attestor — Docker proof, mint, live attest, single-use token.

Runs on the operator host (127.0.0.1:8764). Must not be imported by the
worker HTTP bridge as a self-check. Launcher is the intended importer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.topology_identity import (
    ALL_PURPOSES,
    ATTESTOR_BIND_HOST,
    ATTESTOR_BIND_PORT,
    ATTESTOR_ORIGIN,
    DOCKER_OS_TYPE,
    EXPECTED_ORIGIN,
    LISTEN_CMDLINE_SUFFIX,
    SCHEMA,
    TOKEN_PURPOSES,
    TOKEN_TTL_SECONDS,
    WORKER_BIND_HOST,
    WORKER_BIND_PORT,
    TopologyIdentityError,
    identity_sha256,
    validate_identity,
)

DOCKER_ENV_BLOCKLIST = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CERT_PATH",
    "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY",
    "DOCKER_TLS",
    "DOCKER_API_VERSION",
)

LOOPBACK_8765_HEX = "0100007F:223D"
LISTEN_STATE = "0A"
_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_ENDPOINT_RE = re.compile(r"^(npipe|unix)://.+$")
_NETNS_RE = re.compile(r"^net:\[(\d+)\]$")
_SECRET_MODE_DIR = 0o700
_SECRET_MODE_FILE = 0o600

FD_LIST_SCRIPT = (
    "for p in /proc/[0-9]*; do "
    'pid=${p#/proc/}; '
    "for f in \"$p\"/fd/*; do "
    'link=$(readlink "$f" 2>/dev/null) || continue; '
    'cmd=$(tr "\\0" " " < "$p/cmdline" 2>/dev/null); '
    'printf "%s\\t%s\\t%s\\n" "$pid" "$link" "$cmd"; '
    "done; done"
)
HEALTH_SCRIPT = (
    "node -e "
    "\"require('http').get('http://127.0.0.1:8765/health',r=>{"
    "let d='';r.on('data',c=>d+=c);r.on('end',()=>{"
    "process.stdout.write(d);process.exit(r.statusCode===200?0:1)"
    "})}).on('error',()=>process.exit(1))\""
)

CommandRunner = Callable[..., Any]


def credential_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(
        hashlib.sha256((left or "").encode("utf-8")).digest(),
        hashlib.sha256((right or "").encode("utf-8")).digest(),
    )


def parse_fd_socket_owners(listing: str, inode: int) -> list[dict[str, Any]]:
    target = f"socket:[{inode}]"
    owners: list[dict[str, Any]] = []
    seen: set[int] = set()
    for line in listing.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if parts[1].strip() != target:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        cmd = parts[2].strip() if len(parts) > 2 else ""
        owners.append({"pid": pid, "cmdline": cmd})
    return owners


class TopologyAttestationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "TOPOLOGY_ATTESTATION_MISMATCH"


def validate_docker_endpoint(endpoint: str | None) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise TopologyAttestationError("docker endpoint is required (npipe:// or unix://)")
    value = endpoint.strip()
    if value.startswith("tcp://") or "://" not in value:
        raise TopologyAttestationError("docker endpoint must be npipe:// or unix://")
    if _ENDPOINT_RE.fullmatch(value) is None:
        raise TopologyAttestationError("docker endpoint must be npipe:// or unix://")
    return value


def sanitized_docker_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in DOCKER_ENV_BLOCKLIST:
        env.pop(key, None)
    return env


def docker_argv(endpoint: str, args: list[str]) -> list[str]:
    ep = validate_docker_endpoint(endpoint)
    if "--context" in args or "--config" in args:
        raise TopologyAttestationError("docker --context/--config is forbidden")
    return ["docker", "-H", ep, *args]


def _fail(message: str) -> None:
    raise TopologyAttestationError(message)


def _require_id(value: str, name: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        _fail(f"{name} must be a full 64-lowercase-hex container id")
    return value


def parse_proc_net_tcp(text: str) -> list[tuple[str, int, str, int]]:
    """Return (hex_local, port, state, inode) rows."""
    rows: list[tuple[str, int, str, int]] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        local = parts[1]
        state = parts[3]
        try:
            inode = int(parts[9])
        except ValueError:
            continue
        if ":" not in local:
            continue
        hex_ip, hex_port = local.split(":", 1)
        try:
            port = int(hex_port, 16)
        except ValueError:
            continue
        rows.append((hex_ip.upper() + ":" + hex_port.upper(), port, state.upper(), inode))
    return rows


def loopback_8765_inodes(tcp_text: str) -> list[int]:
    hits: list[int] = []
    for local, port, state, inode in parse_proc_net_tcp(tcp_text):
        if local == LOOPBACK_8765_HEX and state == LISTEN_STATE and port == WORKER_BIND_PORT:
            hits.append(inode)
    return hits


def wildcard_8765_present(tcp_text: str, tcp6_text: str = "") -> bool:
    for local, port, state, _inode in parse_proc_net_tcp(tcp_text):
        if state == LISTEN_STATE and port == WORKER_BIND_PORT and local != LOOPBACK_8765_HEX:
            return True
    for _local, port, state, _inode in parse_proc_net_tcp(tcp6_text):
        if state == LISTEN_STATE and port == WORKER_BIND_PORT:
            return True
    return False


@dataclass
class DockerInspect:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("Id") or "")

    @property
    def running(self) -> bool:
        state = self.raw.get("State") or {}
        return bool(state.get("Running")) and str(state.get("Status") or "") == "running"

    @property
    def created(self) -> str:
        return str(self.raw.get("Created") or "")

    @property
    def started_at(self) -> str:
        return str((self.raw.get("State") or {}).get("StartedAt") or "")

    @property
    def network_mode(self) -> str:
        return str((self.raw.get("HostConfig") or {}).get("NetworkMode") or "")

    @property
    def privileged(self) -> bool:
        return bool((self.raw.get("HostConfig") or {}).get("Privileged"))

    @property
    def image_id(self) -> str:
        return str(self.raw.get("Image") or "")

    @property
    def config_image(self) -> str:
        return str((self.raw.get("Config") or {}).get("Image") or "")

    @property
    def port_bindings(self) -> dict[str, Any]:
        return dict((self.raw.get("HostConfig") or {}).get("PortBindings") or {})

    def mounts_docker_socket(self) -> bool:
        for mount in self.raw.get("Mounts") or []:
            src = str(mount.get("Source") or "")
            dest = str(mount.get("Destination") or "")
            if "docker.sock" in src or "docker.sock" in dest:
                return True
        binds = (self.raw.get("HostConfig") or {}).get("Binds") or []
        for bind in binds:
            if "docker.sock" in str(bind):
                return True
        return False


class DockerTransport:
    """Every command is docker -H <E> with sanitized env. Injectable for tests."""

    def __init__(
        self,
        endpoint: str,
        *,
        runner: Callable[[list[str], dict[str, str]], Any] | None = None,
    ) -> None:
        self.endpoint = validate_docker_endpoint(endpoint)
        self._runner = runner

    def run(self, args: list[str]) -> str:
        argv = docker_argv(self.endpoint, args)
        env = sanitized_docker_env()
        if self._runner is not None:
            result = self._runner(argv, env)
            if isinstance(result, str):
                return result
            if getattr(result, "returncode", 0) != 0:
                _fail(f"docker {' '.join(args)} failed")
            stdout = getattr(result, "stdout", "")
            return stdout.decode("utf-8") if isinstance(stdout, bytes) else str(stdout)
        import subprocess

        proc = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            env=env,
            timeout=30,
        )
        if proc.returncode != 0:
            _fail(f"docker {' '.join(args)} failed")
        return proc.stdout.decode("utf-8")


def _json_load(text: str, name: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TopologyAttestationError(f"{name} is not JSON") from exc


def _netns_inode(link: str) -> int:
    match = _NETNS_RE.fullmatch(link.strip())
    if match is None:
        _fail("netns readlink must return net:[N]")
    inode = int(match.group(1))
    if inode < 1:
        _fail("netns inode must be positive")
    return inode


def _published_n8n_ok(inspect: DockerInspect) -> bool:
    bindings = inspect.port_bindings
    allowed = {"5678/tcp"}
    extra = set(bindings) - allowed
    if extra:
        return False
    rows = bindings.get("5678/tcp") or []
    if not isinstance(rows, list) or len(rows) != 1:
        return False
    row = rows[0] or {}
    return str(row.get("HostIp") or "") == "127.0.0.1" and str(row.get("HostPort") or "") == "5678"


def assert_worker_topology(
    *,
    docker: DockerTransport,
    reviewed_head: str,
    mint: dict[str, Any] | None = None,
    health_get: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the closed proof. Compare to mint when provided (live reassert)."""
    if not isinstance(reviewed_head, str) or _HEAD_RE.fullmatch(reviewed_head) is None:
        _fail("reviewed_head must be 40-lowercase-hex")

    daemon_id_raw = docker.run(["info", "--format", "{{json .ID}}"]).strip()
    os_type_raw = docker.run(["info", "--format", "{{json .OSType}}"]).strip()
    daemon_id = _json_load(daemon_id_raw, "docker daemon ID")
    os_type = _json_load(os_type_raw, "docker OSType")
    if not isinstance(daemon_id, str) or not daemon_id:
        _fail("docker daemon ID missing")
    if os_type != DOCKER_OS_TYPE:
        _fail("docker OSType must be linux")

    n8n_q = docker.run(["compose", "ps", "-q", "n8n"]).strip()
    worker_q = docker.run(["compose", "ps", "-q", "srl-worker"]).strip()
    if not n8n_q or not worker_q:
        _fail("compose ps must return n8n and srl-worker ids")

    n8n = DockerInspect(_json_load(docker.run(["inspect", n8n_q, "--format", "{{json .}}"]), "n8n inspect"))
    worker = DockerInspect(
        _json_load(docker.run(["inspect", worker_q, "--format", "{{json .}}"]), "worker inspect")
    )
    n8n_id = _require_id(n8n.id, "n8n_container_id")
    worker_id = _require_id(worker.id, "worker_container_id")
    if not n8n.running or not worker.running:
        _fail("n8n and srl-worker must be running")
    if n8n.network_mode in {"host"} or n8n.network_mode.startswith("container:"):
        _fail("n8n must remain on a bridge network")
    if n8n.privileged or worker.privileged:
        _fail("privileged containers refused")
    if n8n.mounts_docker_socket() or worker.mounts_docker_socket():
        _fail("docker.sock mount refused")
    if not _published_n8n_ok(n8n):
        _fail("n8n publication must be 127.0.0.1:5678:5678 only")
    expected_mode = f"container:{n8n_id}"
    if worker.network_mode != expected_mode:
        _fail("worker HostConfig.NetworkMode must be container:<full n8n id>")
    if worker.port_bindings:
        _fail("worker PortBindings must be empty")
    if "8765" in json.dumps(worker.raw.get("NetworkSettings") or {}):
        _fail("worker must not publish 8765")

    if not _SHA_RE.fullmatch(worker.image_id):
        _fail("worker image id L must be sha256:<64-hex>")
    if f"@sha256:" not in worker.config_image:
        _fail("worker Config.Image must contain @sha256:D")
    digest_d = "sha256:" + worker.config_image.rsplit("@sha256:", 1)[1].split()[0]
    if _SHA_RE.fullmatch(digest_d) is None:
        _fail("worker image digest D malformed")
    image_text = docker.run(["image", "inspect", worker.image_id, "--format", "{{.Id}} {{json .RepoDigests}}"])
    parts = image_text.strip().split(" ", 1)
    if len(parts) != 2 or parts[0] != worker.image_id:
        _fail("image inspect L mismatch")
    repo_digests = _json_load(parts[1], "RepoDigests")
    if not isinstance(repo_digests, list) or not repo_digests:
        _fail("empty RepoDigests refuses")
    if not any(str(item).endswith("@" + digest_d) or str(item) == digest_d for item in repo_digests):
        _fail("RepoDigests must contain digest D")

    n8n_ns = docker.run(["exec", n8n_id, "readlink", "/proc/1/ns/net"]).strip()
    worker_ns = docker.run(["exec", worker_id, "readlink", "/proc/1/ns/net"]).strip()
    if n8n_ns != worker_ns:
        _fail("n8n and worker netns must be equal")
    netns_inode = _netns_inode(n8n_ns)

    tcp = docker.run(["exec", n8n_id, "cat", "/proc/net/tcp"])
    tcp6 = ""
    try:
        tcp6 = docker.run(["exec", n8n_id, "cat", "/proc/net/tcp6"])
    except TopologyAttestationError:
        tcp6 = ""
    if wildcard_8765_present(tcp, tcp6):
        _fail("wildcard or non-loopback 8765 listener refused")
    inodes = loopback_8765_inodes(tcp)
    if len(inodes) != 1:
        _fail("exactly one 127.0.0.1:8765 LISTEN inode required")
    listen_inode = inodes[0]

    n8n_owners = parse_fd_socket_owners(
        docker.run(["exec", n8n_id, "sh", "-c", FD_LIST_SCRIPT]),
        listen_inode,
    )
    worker_owners = parse_fd_socket_owners(
        docker.run(["exec", worker_id, "sh", "-c", FD_LIST_SCRIPT]),
        listen_inode,
    )
    if n8n_owners:
        _fail("n8n pid namespace must not own the 8765 listen inode")
    if not isinstance(worker_owners, list) or len(worker_owners) != 1:
        _fail("exactly one worker pid must own the 8765 listen inode")
    owner = worker_owners[0]
    if not isinstance(owner, dict):
        _fail("listen owner record malformed")
    pid = owner.get("pid")
    cmd = str(owner.get("cmdline") or "")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        _fail("listen owner pid must be a positive integer")
    if not cmd.endswith(LISTEN_CMDLINE_SUFFIX):
        _fail("listen owner cmdline must end with runtime_bridge")

    listed = docker.run(["container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}"])
    members: list[str] = []
    for raw_id in listed.splitlines():
        cid = raw_id.strip()
        if not cid:
            continue
        _require_id(cid, "host-wide container id")
        info = docker.run(["inspect", cid, "--format", "{{.Id}} {{.HostConfig.NetworkMode}} {{.State.Status}}"]).strip()
        bits = info.split(" ", 2)
        if len(bits) < 2:
            _fail("host-wide inspect malformed")
        full_id, mode = bits[0], bits[1]
        _require_id(full_id, "inspected container id")
        if full_id == n8n_id or mode == expected_mode:
            members.append(full_id)
    netset = sorted(set(members))
    if netset != sorted({n8n_id, worker_id}):
        _fail("host-wide netns container set must be exactly {n8n, worker}")

    def _health() -> dict[str, Any]:
        if health_get is not None:
            return health_get()
        payload = docker.run(["exec", n8n_id, "sh", "-c", HEALTH_SCRIPT])
        data = _json_load(payload, "health")
        if not isinstance(data, dict):
            _fail("health body must be an object")
        return data

    inodes1 = loopback_8765_inodes(docker.run(["exec", n8n_id, "cat", "/proc/net/tcp"]))
    if inodes1 != [listen_inode]:
        _fail("listen inode drifted before health")
    health = _health()
    if health.get("service") != "sentinel-research-lab-self-improvement-v2" or health.get("status") != "ready":
        _fail("health is reachability evidence only and did not match ready worker")
    inodes2 = loopback_8765_inodes(docker.run(["exec", n8n_id, "cat", "/proc/net/tcp"]))
    if inodes2 != [listen_inode]:
        _fail("listen inode drifted after health")
    n8n2 = DockerInspect(_json_load(docker.run(["inspect", n8n_id, "--format", "{{json .}}"]), "n8n reinspect"))
    worker2 = DockerInspect(
        _json_load(docker.run(["inspect", worker_id, "--format", "{{json .}}"]), "worker reinspect")
    )
    if n8n2.id != n8n_id or worker2.id != worker_id:
        _fail("container ids drifted during health sandwich")

    identity = {
        "schema": SCHEMA,
        "reviewed_head": reviewed_head,
        "n8n_container_id": n8n_id,
        "n8n_created": n8n.created,
        "n8n_started_at": n8n.started_at,
        "n8n_netns_inode": netns_inode,
        "worker_container_id": worker_id,
        "worker_created": worker.created,
        "worker_started_at": worker.started_at,
        "worker_image_id_L": worker.image_id,
        "worker_image_digest_D": digest_d,
        "worker_network_mode": expected_mode,
        "bind": {"host": WORKER_BIND_HOST, "port": WORKER_BIND_PORT, "protocol": "tcp"},
        "listen_inode": listen_inode,
        "listen_owner": {
            "container_id": worker_id,
            "pid_in_worker_pidns": pid,
            "cmdline_suffix": LISTEN_CMDLINE_SUFFIX,
        },
        "netns_container_set": netset,
        "published_worker_ports": [],
        "expected_origin": EXPECTED_ORIGIN,
        "docker_endpoint": docker.endpoint,
        "docker_daemon_id": daemon_id,
        "docker_os_type": DOCKER_OS_TYPE,
    }
    try:
        validate_identity(identity)
    except TopologyIdentityError as exc:
        raise TopologyAttestationError(str(exc)) from exc
    digest = identity_sha256(identity)
    if mint is not None:
        try:
            validate_identity(mint)
        except TopologyIdentityError as exc:
            raise TopologyAttestationError("mint identity invalid") from exc
        if mint != identity or identity_sha256(mint) != digest:
            _fail("TOPOLOGY_ATTESTATION=STALE live identity mismatch")
        if mint.get("docker_daemon_id") != daemon_id or mint.get("docker_os_type") != os_type:
            _fail("TOPOLOGY_ATTESTATION=STALE daemon identity mismatch")
    return identity


TOKEN_UNUSED = "UNUSED"
TOKEN_CONSUMING = "CONSUMING"
TOKEN_CONSUMED = "CONSUMED"
TOKEN_BURNED = "BURNED"


@dataclass
class TokenRecord:
    token: str
    purpose: str
    digest: str
    n8n_container_id: str
    worker_container_id: str
    listen_inode: int
    state: str = TOKEN_UNUSED
    issued_at_utc: str = ""
    expires_at_utc: str = ""
    issued_monotonic: float = 0.0
    expires_monotonic: float = 0.0


class TokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, TokenRecord] = {}

    def mint(
        self,
        *,
        purpose: str,
        identity: dict[str, Any],
        now_monotonic: float | None = None,
    ) -> TokenRecord:
        if purpose not in TOKEN_PURPOSES:
            raise TopologyAttestationError("purpose does not mint a binding token")
        digest = identity_sha256(identity)
        now = time.monotonic() if now_monotonic is None else now_monotonic
        record = TokenRecord(
            token=secrets.token_urlsafe(32),
            purpose=purpose,
            digest=digest,
            n8n_container_id=str(identity["n8n_container_id"]),
            worker_container_id=str(identity["worker_container_id"]),
            listen_inode=int(identity["listen_inode"]),
            issued_monotonic=now,
            expires_monotonic=now + float(TOKEN_TTL_SECONDS),
            issued_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            expires_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + TOKEN_TTL_SECONDS)),
        )
        with self._lock:
            self._tokens[record.token] = record
        return record

    def reserve(
        self,
        token: str,
        *,
        purpose: str,
        now_monotonic: float | None = None,
    ) -> TokenRecord:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        with self._lock:
            record = self._tokens.get(token)
            if record is None:
                raise TopologyAttestationError("unknown topology binding token")
            if record.state != TOKEN_UNUSED:
                raise TopologyAttestationError("topology binding token is not UNUSED")
            if record.purpose != purpose:
                record.state = TOKEN_BURNED
                raise TopologyAttestationError("topology binding token purpose mismatch")
            if now >= record.expires_monotonic:
                record.state = TOKEN_BURNED
                raise TopologyAttestationError("topology binding token expired")
            record.state = TOKEN_CONSUMING
            return record

    def complete(self, token: str, *, ok: bool) -> str:
        with self._lock:
            record = self._tokens.get(token)
            if record is None:
                raise TopologyAttestationError("unknown topology binding token")
            if record.state != TOKEN_CONSUMING:
                raise TopologyAttestationError("topology binding token is not CONSUMING")
            record.state = TOKEN_CONSUMED if ok else TOKEN_BURNED
            return record.state


@dataclass
class AttestorState:
    docker: DockerTransport
    mint: dict[str, Any]
    attest_credential: str
    consume_credential: str
    reviewed_head: str
    tokens: TokenStore = field(default_factory=TokenStore)
    health_get: Callable[[], dict[str, Any]] | None = None
    reassert_timeout_seconds: float = 8.0
    reassert: Callable[[], dict[str, Any]] | None = None

    def live_identity(self) -> dict[str, Any]:
        if self.reassert is not None:
            return self.reassert()
        return assert_worker_topology(
            docker=self.docker,
            reviewed_head=self.reviewed_head,
            mint=self.mint,
            health_get=self.health_get,
        )


def _fail_body(message: str) -> bytes:
    return json.dumps(
        {
            "status": "FAIL",
            "error": "TOPOLOGY_ATTESTATION_MISMATCH",
            "message": message,
            "final_state": "POLICY_REJECTED",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _pass_attest(identity: dict[str, Any], *, purpose: str, token: TokenRecord | None) -> bytes:
    digest = identity_sha256(identity)
    body: dict[str, Any] = {
        "status": "PASS",
        "schema": SCHEMA,
        "topology_attestation_sha256": digest,
        "purpose": purpose,
        "identity": identity,
    }
    if token is not None:
        body["topology_binding_token"] = token.token
        body["token_ttl_seconds"] = TOKEN_TTL_SECONDS
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _bearer(header: str) -> str:
    if not header.startswith("Bearer "):
        return ""
    return header[len("Bearer ") :]


class TopologyAttestorHandler(BaseHTTPRequestHandler):
    state: AttestorState

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TopologyAttestationError("request is not JSON") from exc
        if not isinstance(payload, dict):
            raise TopologyAttestationError("request must be an object")
        return payload

    def _write(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        cred = _bearer(self.headers.get("Authorization") or "")
        try:
            payload = self._read_json()
            purpose = payload.get("purpose")
            if purpose not in ALL_PURPOSES:
                raise TopologyAttestationError("purpose refused")
            if self.path == "/v2/topology-attest":
                if not credential_equals(cred, self.state.attest_credential):
                    raise TopologyAttestationError("attest credential refused")
                if credential_equals(cred, self.state.consume_credential):
                    raise TopologyAttestationError("consume credential cannot attest")
                identity = self.state.live_identity()
                token = None
                if purpose in TOKEN_PURPOSES:
                    token = self.state.tokens.mint(purpose=purpose, identity=identity)
                elif purpose == "execute_probe":
                    token = None
                self._write(200, _pass_attest(identity, purpose=purpose, token=token))
                return
            if self.path == "/v2/topology-consume":
                if not credential_equals(cred, self.state.consume_credential):
                    raise TopologyAttestationError("consume credential refused")
                if credential_equals(cred, self.state.attest_credential):
                    raise TopologyAttestationError("attest credential cannot consume")
                token = payload.get("topology_binding_token")
                if not isinstance(token, str) or not token:
                    raise TopologyAttestationError("topology_binding_token required")
                record = self.state.tokens.reserve(token, purpose=str(purpose))
                ok = False
                try:
                    deadline = time.monotonic() + self.state.reassert_timeout_seconds
                    identity = self.state.live_identity()
                    if time.monotonic() > deadline:
                        raise TopologyAttestationError("topology reassert timeout")
                    digest = identity_sha256(identity)
                    if (
                        digest != record.digest
                        or identity["n8n_container_id"] != record.n8n_container_id
                        or identity["worker_container_id"] != record.worker_container_id
                        or identity["listen_inode"] != record.listen_inode
                    ):
                        raise TopologyAttestationError("live topology no longer matches token binding")
                    ok = True
                    self.state.tokens.complete(token, ok=True)
                    self._write(
                        200,
                        json.dumps(
                            {"status": "PASS", "topology_attestation_sha256": digest, "purpose": purpose},
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("utf-8"),
                    )
                    return
                finally:
                    if not ok:
                        try:
                            self.state.tokens.complete(token, ok=False)
                        except TopologyAttestationError:
                            pass
                return
            raise TopologyAttestationError("unknown attestor path")
        except TopologyAttestationError as exc:
            self._write(403, _fail_body(str(exc)))
        except TopologyIdentityError as exc:
            self._write(403, _fail_body(str(exc)))
        except Exception:
            self._write(403, _fail_body("topology attestor failed closed"))


def serve_attestor(state: AttestorState, *, host: str = ATTESTOR_BIND_HOST, port: int = ATTESTOR_BIND_PORT) -> ThreadingHTTPServer:
    if host != ATTESTOR_BIND_HOST or port != ATTESTOR_BIND_PORT:
        raise TopologyAttestationError("attestor must bind 127.0.0.1:8764")
    handler = type("BoundTopologyAttestorHandler", (TopologyAttestorHandler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    return server


def write_protected_secret(path: Path, value: str) -> None:
    path = Path(path)
    if any(ch in value for ch in ("\0", "\n", "\r")):
        raise TopologyAttestationError("secret value must be a single line")
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        _apply_windows_acl(directory)
        path.write_text(value, encoding="utf-8", newline="\n")
        _apply_windows_acl(path)
        _assert_windows_acl(directory)
        _assert_windows_acl(path)
        return
    os.chmod(directory, _SECRET_MODE_DIR)
    path.write_text(value, encoding="utf-8", newline="\n")
    os.chmod(path, _SECRET_MODE_FILE)
    _assert_posix_secret_mode(directory, path)


def _assert_posix_secret_mode(directory: Path, path: Path) -> None:
    dir_mode = stat.S_IMODE(directory.stat().st_mode)
    file_mode = stat.S_IMODE(path.stat().st_mode)
    if dir_mode != _SECRET_MODE_DIR or file_mode != _SECRET_MODE_FILE:
        raise TopologyAttestationError("secret POSIX mode must be 0700/0600")


def _apply_windows_acl(path: Path) -> None:
    import subprocess

    user = os.environ.get("USERNAME") or ""
    if not user:
        raise TopologyAttestationError("Windows secret ACL requires USERNAME")
    quoted = str(path)
    script = (
        f"$p = {json.dumps(quoted)}; "
        "$acl = Get-Acl -LiteralPath $p; "
        "$acl.SetAccessRuleProtection($true, $false); "
        "$acl.Access | ForEach-Object { [void]$acl.RemoveAccessRule($_) }; "
        "$idUser = New-Object System.Security.Principal.NTAccount($env:USERNAME); "
        "$idSys = New-Object System.Security.Principal.NTAccount('NT AUTHORITY\\SYSTEM'); "
        "$acl.SetOwner($idUser); "
        "$ruleUser = New-Object System.Security.AccessControl.FileSystemAccessRule("
        "$idUser,'FullControl','None','None','Allow'); "
        "$ruleSys = New-Object System.Security.AccessControl.FileSystemAccessRule("
        "$idSys,'FullControl','None','None','Allow'); "
        "$acl.AddAccessRule($ruleUser); $acl.AddAccessRule($ruleSys); "
        "Set-Acl -LiteralPath $p -AclObject $acl"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise TopologyAttestationError("Windows secret ACL apply failed")


def _assert_windows_acl(path: Path) -> None:
    import subprocess

    quoted = str(path)
    script = (
        f"$p = {json.dumps(quoted)}; "
        "$acl = Get-Acl -LiteralPath $p; "
        "if (-not $acl.AreAccessRulesProtected) { Write-Output 'INHERIT'; exit 4 }; "
        "$owner = $acl.Owner; "
        "$user = ([System.Security.Principal.NTAccount]$env:USERNAME).Translate("
        "[type]'System.Security.Principal.SecurityIdentifier').Value; "
        "$sys = ([System.Security.Principal.NTAccount]'NT AUTHORITY\\SYSTEM').Translate("
        "[type]'System.Security.Principal.SecurityIdentifier').Value; "
        "$idents = @(); $rights = @(); $types = @(); "
        "foreach ($ace in $acl.Access) { "
        "$sid = $ace.IdentityReference.Translate([type]'System.Security.Principal.SecurityIdentifier').Value; "
        "$idents += $sid; $rights += [string]$ace.FileSystemRights; $types += [string]$ace.AccessControlType; "
        "if ($ace.IsInherited) { Write-Output 'INHERITED'; exit 5 } }; "
        "if ($idents.Count -ne 2) { Write-Output 'COUNT'; exit 6 }; "
        "$blob = ($idents + $rights + $types + $owner) -join '|'; "
        "Write-Output $blob"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise TopologyAttestationError("Windows secret ACL verify failed")
    blob = (proc.stdout or "").strip().upper()
    if "EVERYONE" in blob or "AUTHENTICATED USERS" in blob or "BUILTIN\\USERS" in blob:
        raise TopologyAttestationError("Windows secret ACL contains a broad ACE")


def env_boolean_is_not_authority(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    if env.get("WORKER_TOPOLOGY_ATTESTED") in {"YES", "true", "1"}:
        raise TopologyAttestationError("WORKER_TOPOLOGY_ATTESTED is not topology authority")


def mint_pass_envelope(identity: dict[str, Any], *, purpose: str, token: str | None) -> dict[str, Any]:
    validate_identity(identity)
    env_boolean_is_not_authority()
    body: dict[str, Any] = {
        "status": "PASS",
        "schema": SCHEMA,
        "topology_attestation_sha256": content_sha256(identity),
        "purpose": purpose,
        "identity": identity,
    }
    if purpose == "execute_probe":
        if token is not None:
            raise TopologyAttestationError("execute_probe must not mint a consume token")
        return body
    if purpose not in TOKEN_PURPOSES or not token:
        raise TopologyAttestationError("token purpose requires a binding token")
    body["topology_binding_token"] = token
    body["token_ttl_seconds"] = TOKEN_TTL_SECONDS
    return body
