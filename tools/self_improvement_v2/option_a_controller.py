"""Revision 2.5 monotonic finalization → seal → attestation → copy → verify."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from tools.self_improvement_v2.export_seal import bind_observed_identity, seal_generation, sealed_inventory_sha256
from tools.self_improvement_v2.export_transport import copy_generation
from tools.self_improvement_v2.export_verify import atomic_publish, verify_three_authority
from tools.self_improvement_v2.finalized_attestation import write_finalized_attestation
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.option_a_constants import SCHEMA_FINALIZED_ATTESTATION, SRL_CANDIDATE_REF
from tools.self_improvement_v2.topology_consume import require_independent_live
from tools.self_improvement_v2.topology_identity import copy_generation_identity

ObserveGitFn = Callable[[], tuple[str, str, str]]
BundleHeadsFn = Callable[[], list[str]]


def run_rev25_export(
    *,
    execution_id: str,
    reviewed_head: str,
    authorized_baseline: str,
    staging_generation: str,
    worker_id: str,
    n8n_id: str,
    expected_image_digest: str,
    inspect_worker,
    inspect_n8n,
    list_all_ids,
    observe_git: ObserveGitFn,
    bundle_heads: BundleHeadsFn,
    worker_generation_dir: Path,
    ledger_root: Path,
    durable_root: Path,
    copy_fn,
    recompute_diff,
    clone_bundle=None,
    verify_scratch: Path | None = None,
    sequence_start: int = 1,
    now_ts: int | None = None,
) -> dict[str, Any]:
    state = "FINALIZATION_PENDING"
    live_1a = require_independent_live(
        inspect_worker=inspect_worker,
        inspect_n8n=inspect_n8n,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=expected_image_digest,
        sequence=sequence_start,
    )
    observed_commit, observed_tree, observed_ref = observe_git()
    if observed_commit != observed_ref:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "HEAD != refs/heads/srl-candidate",
            state="FAILED_FROZEN",
        )
    live_1b = require_independent_live(
        inspect_worker=inspect_worker,
        inspect_n8n=inspect_n8n,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=expected_image_digest,
        previous=live_1a,
        sequence=sequence_start + 1,
        prior_pass=live_1a,
    )
    hashes = seal_generation(worker_generation_dir)
    sealed_commit = (worker_generation_dir / "candidate_commit").read_text(encoding="utf-8").strip()
    sealed_tree = (worker_generation_dir / "candidate_tree").read_text(encoding="utf-8").strip()
    fin = json.loads((worker_generation_dir / "finalization_result.json").read_text(encoding="utf-8"))
    bind_observed_identity(
        observed_commit=observed_commit,
        observed_tree=observed_tree,
        sealed_commit_bytes=sealed_commit,
        sealed_tree_bytes=sealed_tree,
        finalization_commit=str(fin.get("candidate_commit") or ""),
        finalization_tree=str(fin.get("candidate_tree") or ""),
        bundle_heads=bundle_heads(),
    )
    fin_sha = hashes["finalization_result.json"]
    record = write_finalized_attestation(
        ledger_root,
        {
            "schema_version": SCHEMA_FINALIZED_ATTESTATION,
            "execution_id": execution_id,
            "reviewed_head": reviewed_head,
            "authorized_baseline": authorized_baseline,
            "candidate_commit": observed_commit,
            "candidate_tree": observed_tree,
            "srl_candidate_ref": SRL_CANDIDATE_REF,
            "finalization_result_sha256": fin_sha,
            "sealed_inventory_sha256": sealed_inventory_sha256(hashes),
            "sealed_artifact_hashes": hashes,
            "staging_generation": staging_generation,
            "worker_container_id": live_1b["worker_container_id"],
            "worker_started_at": live_1b["worker_started_at"],
            "worker_image_digest": live_1b["worker_image_digest"],
            "worker_netns_identity": live_1b["worker_netns_identity"],
            "n8n_container_id": live_1b["n8n_container_id"],
            "topology_attestation_identity": live_1b["topology_attestation_sha256"],
            "topology_attestation_sequence": int(live_1b["topology_attestation_sequence"]),
            "launcher_observation_sequence": sequence_start + 2,
            "observed_unix_ts": int(now_ts if now_ts is not None else time.time()),
        },
    )
    state = "FINALIZED"
    live_2 = require_independent_live(
        inspect_worker=inspect_worker,
        inspect_n8n=inspect_n8n,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=expected_image_digest,
        previous=copy_generation_identity(record),
        sequence=sequence_start + 3,
        prior_pass=live_1b,
    )
    attempt = copy_generation(
        durable_root=durable_root,
        execution_id=execution_id,
        generation=staging_generation,
        worker_id=live_2["worker_container_id"],
        attested=record,
        sealed_hashes=hashes,
        live_inspect=lambda: require_independent_live(
            inspect_worker=inspect_worker,
            inspect_n8n=inspect_n8n,
            list_all_ids=list_all_ids,
            worker_id=worker_id,
            n8n_id=n8n_id,
            expected_image_digest=expected_image_digest,
            previous=copy_generation_identity(record),
            sequence=sequence_start + 4,
        ),
        copy_fn=copy_fn,
        pre_copy_reassert_done=True,
    )
    verify_three_authority(
        attestation=record,
        attempt_dir=attempt,
        reviewed_head=reviewed_head,
        recompute_diff=recompute_diff,
        clone_bundle=clone_bundle,
        verify_scratch=verify_scratch,
    )
    published = atomic_publish(attempt, durable_root / "verified" / execution_id)
    return {"state": state, "attestation": record, "verified": str(published)}
