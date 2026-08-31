"""Closed typed schema for srl.worker_topology_attestation.v1.

Host attestor and launcher mint share this validator. The worker HTTP bridge
must not import this module as a self-attestation substitute.
"""

from __future__ import annotations

from typing import Any

from tools.self_improvement_v2.canonical import content_sha256

SCHEMA = "srl.worker_topology_attestation.v1"

IDENTITY_KEYS: tuple[str, ...] = (
    "schema",
    "reviewed_head",
    "n8n_container_id",
    "n8n_created",
    "n8n_started_at",
    "worker_container_id",
    "worker_created",
    "worker_started_at",
    "worker_image_id_L",
    "worker_image_digest_D",
    "worker_network_mode",
    "bind",
    "listen_inode",
    "listen_owner",
    "n8n_netns_inode",
    "netns_container_set",
    "published_worker_ports",
    "expected_origin",
    "docker_endpoint",
    "docker_daemon_id",
    "docker_os_type",
)

BIND_KEYS: tuple[str, ...] = ("host", "port", "protocol")
LISTEN_OWNER_KEYS: tuple[str, ...] = ("container_id", "pid_in_worker_pidns", "cmdline_suffix")

EXPECTED_ORIGIN = "http://127.0.0.1:8765"
ATTESTOR_ORIGIN = "http://host.docker.internal:8764"
ATTESTOR_BIND_HOST = "127.0.0.1"
ATTESTOR_BIND_PORT = 8764
WORKER_BIND_HOST = "127.0.0.1"
WORKER_BIND_PORT = 8765
WORKER_BIND_PROTOCOL = "tcp"
LISTEN_CMDLINE_SUFFIX = "tools.self_improvement_v2.runtime_bridge"
DOCKER_OS_TYPE = "linux"
TOKEN_TTL_SECONDS = 5
TOKEN_PURPOSES = frozenset(
    {"provider_implementer", "provider_reviewer", "worker_authorize"}
)
ALL_PURPOSES = frozenset({*TOKEN_PURPOSES, "execute_probe"})

_HEAD_RE = r"^[0-9a-f]{40}$"
_ID_RE = r"^[0-9a-f]{64}$"
_SHA_RE = r"^sha256:[0-9a-f]{64}$"
_ENDPOINT_RE = r"^(npipe|unix)://.+"


class TopologyIdentityError(ValueError):
    """Closed identity refused before hashing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "TOPOLOGY_ATTESTATION_MISMATCH"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_str(value: Any, name: str, *, pattern: str | None = None, exact: str | None = None) -> str:
    if not isinstance(value, str) or value == "":
        raise TopologyIdentityError(f"{name} must be a non-empty string")
    if exact is not None and value != exact:
        raise TopologyIdentityError(f"{name} must be exactly {exact}")
    if pattern is not None:
        import re

        if re.fullmatch(pattern, value) is None:
            raise TopologyIdentityError(f"{name} failed pattern {pattern}")
    return value


def _require_int(value: Any, name: str, *, min_v: int = 1, max_v: int = 2**63 - 1) -> int:
    if not _is_int(value):
        raise TopologyIdentityError(f"{name} must be a JSON integer (bool/float/null refused)")
    if value < min_v or value > max_v:
        raise TopologyIdentityError(f"{name} out of range")
    return value


def validate_identity(identity: Any) -> dict[str, Any]:
    """Refuse missing/extra/wrong-type fields before hashing."""
    if not isinstance(identity, dict):
        raise TopologyIdentityError("identity must be an object")
    keys = tuple(identity.keys())
    extra = sorted(set(keys) - set(IDENTITY_KEYS))
    missing = [k for k in IDENTITY_KEYS if k not in identity]
    if extra:
        raise TopologyIdentityError(f"identity has extra keys: {extra}")
    if missing:
        raise TopologyIdentityError(f"identity missing keys: {missing}")

    _require_str(identity["schema"], "schema", exact=SCHEMA)
    _require_str(identity["reviewed_head"], "reviewed_head", pattern=_HEAD_RE)
    n8n_id = _require_str(identity["n8n_container_id"], "n8n_container_id", pattern=_ID_RE)
    worker_id = _require_str(identity["worker_container_id"], "worker_container_id", pattern=_ID_RE)
    _require_str(identity["n8n_created"], "n8n_created")
    _require_str(identity["n8n_started_at"], "n8n_started_at")
    _require_str(identity["worker_created"], "worker_created")
    _require_str(identity["worker_started_at"], "worker_started_at")
    _require_str(identity["worker_image_id_L"], "worker_image_id_L", pattern=_SHA_RE)
    _require_str(identity["worker_image_digest_D"], "worker_image_digest_D", pattern=_SHA_RE)
    expected_mode = f"container:{n8n_id}"
    _require_str(identity["worker_network_mode"], "worker_network_mode", exact=expected_mode)
    _require_int(identity["n8n_netns_inode"], "n8n_netns_inode")
    _require_int(identity["listen_inode"], "listen_inode")
    _require_str(identity["expected_origin"], "expected_origin", exact=EXPECTED_ORIGIN)
    _require_str(identity["docker_endpoint"], "docker_endpoint", pattern=_ENDPOINT_RE)
    _require_str(identity["docker_daemon_id"], "docker_daemon_id")
    _require_str(identity["docker_os_type"], "docker_os_type", exact=DOCKER_OS_TYPE)

    bind = identity["bind"]
    if not isinstance(bind, dict):
        raise TopologyIdentityError("bind must be an object")
    if tuple(sorted(bind.keys())) != tuple(sorted(BIND_KEYS)) or set(bind.keys()) != set(BIND_KEYS):
        extra_b = sorted(set(bind) - set(BIND_KEYS))
        missing_b = [k for k in BIND_KEYS if k not in bind]
        if extra_b or missing_b:
            raise TopologyIdentityError(f"bind keys must be exactly {list(BIND_KEYS)}")
    _require_str(bind["host"], "bind.host", exact=WORKER_BIND_HOST)
    _require_int(bind["port"], "bind.port", min_v=WORKER_BIND_PORT, max_v=WORKER_BIND_PORT)
    _require_str(bind["protocol"], "bind.protocol", exact=WORKER_BIND_PROTOCOL)

    owner = identity["listen_owner"]
    if not isinstance(owner, dict) or set(owner.keys()) != set(LISTEN_OWNER_KEYS):
        raise TopologyIdentityError(f"listen_owner keys must be exactly {list(LISTEN_OWNER_KEYS)}")
    _require_str(owner["container_id"], "listen_owner.container_id", exact=worker_id)
    _require_int(owner["pid_in_worker_pidns"], "listen_owner.pid_in_worker_pidns")
    _require_str(
        owner["cmdline_suffix"],
        "listen_owner.cmdline_suffix",
        exact=LISTEN_CMDLINE_SUFFIX,
    )

    published = identity["published_worker_ports"]
    if published != []:
        raise TopologyIdentityError("published_worker_ports must be exactly []")

    netset = identity["netns_container_set"]
    if not isinstance(netset, list):
        raise TopologyIdentityError("netns_container_set must be an array")
    if len(netset) != 2:
        raise TopologyIdentityError("netns_container_set must contain exactly two members")
    for i, member in enumerate(netset):
        _require_str(member, f"netns_container_set[{i}]", pattern=_ID_RE)
    if netset[0] == netset[1]:
        raise TopologyIdentityError("netns_container_set members must be unique")
    expected_set = sorted({n8n_id, worker_id})
    if netset != expected_set:
        raise TopologyIdentityError("netns_container_set must be the two full IDs, lexicographically sorted")
    return identity


def identity_sha256(identity: dict[str, Any]) -> str:
    validate_identity(identity)
    return content_sha256(identity)
