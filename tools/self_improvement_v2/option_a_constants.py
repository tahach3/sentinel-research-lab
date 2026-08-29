"""Revision 2.5 locked constants. Do not loosen execution-id grammar."""

from __future__ import annotations

import re
from typing import Final

SCHEMA_FINALIZED_ATTESTATION = "srl.finalized_attestation.v2_5"
RO_REVIEWED_ROOT = "/srl/sentinel-research-lab"
EXECUTION_ROOT_PREFIX = "/tmp/srl-exec"
ZONE_P_ROOT = "/tmp/srl-zone-p"
WORKER_ORIGIN = "http://127.0.0.1:8765"
SRL_CANDIDATE_REF = "refs/heads/srl-candidate"

EXECUTION_ID_RE: Final = re.compile(r"^[a-f0-9]{32}$")
STAGING_GENERATION_RE: Final = re.compile(r"^[a-f0-9]{8}$")
ATTEMPT_ID_RE: Final = re.compile(r"^[a-f0-9]{8}$")
COMMIT_SHA_RE: Final = re.compile(r"^[a-f0-9]{40}$")
CONTAINER_ID_RE: Final = re.compile(r"^[a-f0-9]{64}$")
HEX64_RE: Final = re.compile(r"^[a-f0-9]{64}$")

WORKER_EXPORT_ALLOWLIST: Final = frozenset(
    {
        "schema.json",
        "execution_id",
        "reviewed_head",
        "authorized_baseline",
        "candidate_commit",
        "candidate_tree",
        "actual.diff",
        "actual.diff.sha256",
        "candidate.bundle",
        "candidate.bundle.sha256",
        "export_manifest.json",
        "export_manifest.sha256",
        "finalization_result.json",
        "finalization_result.sha256",
        "proposal_identity.json",
        "provenance.json",
        "runtime_identity.json",
    }
)

HOST_LAUNCHER_ONLY_NAMES: Final = frozenset({"finalized_attestation.json", "ACK.json"})

DURABLE_EVIDENCE_REL = "durable-evidence"
