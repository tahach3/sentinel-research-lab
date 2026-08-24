"""Worker-side topology-binding consume client.

HTTP only. Does not perform Docker proof and must not import topology_attest.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.topology_identity import ATTESTOR_ORIGIN, TOKEN_PURPOSES

CONSUME_PATH = "/v2/topology-consume"


class TopologyConsumeError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(
            ERROR_CODES["TOPOLOGY_ATTESTATION_MISMATCH"],
            message,
            state="POLICY_REJECTED",
        )


def consume_topology_binding_token(
    *,
    purpose: str,
    token: str,
    origin: str,
    credential: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    if purpose not in TOKEN_PURPOSES:
        raise TopologyConsumeError("topology consume purpose refused")
    if not isinstance(token, str) or not token.strip():
        raise TopologyConsumeError("topology_binding_token required")
    if not isinstance(credential, str) or not credential.strip():
        raise TopologyConsumeError("topology consume credential required")
    base = (origin or ATTESTOR_ORIGIN).rstrip("/")
    if base != ATTESTOR_ORIGIN:
        raise TopologyConsumeError("topology attestor origin is not the pinned host-gateway URL")
    body = json.dumps(
        {"topology_binding_token": token, "purpose": purpose},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{CONSUME_PATH}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credential}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise TopologyConsumeError(detail or "topology consume refused") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TopologyConsumeError("topology consume unreachable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TopologyConsumeError("topology consume returned non-JSON") from exc
    if status != 200 or not isinstance(payload, dict) or payload.get("status") != "PASS":
        raise TopologyConsumeError("topology consume did not PASS")
    return payload
