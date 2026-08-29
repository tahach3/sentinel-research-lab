"""Revision 2.5 monotonic finalization → seal → attestation → copy → verify."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.export_seal import bind_observed_identity, seal_generation, sealed_inventory_sha256
from tools.self_improvement_v2.export_transport import copy_generation
from tools.self_improvement_v2.export_verify import (
    atomic_publish,
    reconstruct_authority_c,
    verify_three_authority,
)
from tools.self_improvement_v2.finalized_attestation import write_finalized_attestation
from tools.self_improvement_v2.git_worker import (
    create_local_commit,
    remove_worktree,
    resolve_repo_root,
    run_git,
    source_tree_fingerprint,
    worktree_head,
)
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError
from tools.self_improvement_v2.option_a_constants import (
    SCHEMA_FINALIZED_ATTESTATION,
    SRL_CANDIDATE_REF,
    WORKER_EXPORT_ALLOWLIST,
)
from tools.self_improvement_v2.patch_validator import (
    actual_diff_sha256,
    changed_paths_sha256,
    changed_paths_since,
    staged_tree_sha,
)
from tools.self_improvement_v2.path_policy import load_policy, policy_sha256
from tools.self_improvement_v2.review_gate import assert_review_bound
from tools.self_improvement_v2.risk_authority import assert_finalize_risk_bindings
from tools.self_improvement_v2.schema_loader import validate_instance
from tools.self_improvement_v2.srl_git_exec import REPO_ROLE_DISPOSABLE
from tools.self_improvement_v2.topology_consume import require_independent_live
from tools.self_improvement_v2.topology_identity import copy_generation_identity

ObserveGitFn = Callable[[], tuple[str, str, str]]
BundleHeadsFn = Callable[[], list[object]]
CopyFn = Callable[[list[str]], None]
CloneBundleFn = Callable[[Path, Path], None]


@dataclass(frozen=True)
class Rev25RuntimeDeps:
    """Injected live topology / copy providers. Never inferred from runtime mode."""

    inspect_worker: Callable[[str], dict[str, Any]]
    inspect_n8n: Callable[[str], dict[str, Any]]
    list_all_ids: Callable[[], list[str]]
    worker_id: str
    n8n_id: str
    expected_image_digest: str
    copy_fn: CopyFn | None = None
    clone_bundle: CloneBundleFn | None = None
    staging_generation: str | None = None
    now_ts: int | None = None


class _MonotonicSequence:
    def __init__(self, start: int) -> None:
        self._next = start

    def next(self) -> int:
        value = self._next
        self._next += 1
        return value


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
    if authorized_baseline != reviewed_head:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "authorized_baseline must equal reviewed_head",
            state="FAILED_FROZEN",
        )
    if clone_bundle is None:
        clone_bundle = reconstruct_authority_c
    if verify_scratch is None:
        verify_scratch = durable_root / "verify-scratch"
    state = "FINALIZATION_PENDING"
    seq = _MonotonicSequence(sequence_start)
    live_1a = require_independent_live(
        inspect_worker=inspect_worker,
        inspect_n8n=inspect_n8n,
        list_all_ids=list_all_ids,
        worker_id=worker_id,
        n8n_id=n8n_id,
        expected_image_digest=expected_image_digest,
        sequence=seq.next(),
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
        sequence=seq.next(),
        prior_pass=live_1a,
    )
    hashes = seal_generation(worker_generation_dir)
    sealed_commit = (worker_generation_dir / "candidate_commit").read_text(encoding="utf-8").strip()
    sealed_tree = (worker_generation_dir / "candidate_tree").read_text(encoding="utf-8").strip()
    fin = json.loads((worker_generation_dir / "finalization_result.json").read_text(encoding="utf-8"))
    bundle_sha = hashes["candidate.bundle"]
    sidecar = (worker_generation_dir / "candidate.bundle.sha256").read_text(encoding="utf-8").strip()
    if sidecar != bundle_sha:
        raise WorkerError(
            ERROR_CODES["SEAL_BIND_MISMATCH"],
            "candidate.bundle.sha256 sidecar != sealed bundle bytes",
            state="FAILED_FROZEN",
        )
    bind_observed_identity(
        observed_commit=observed_commit,
        observed_tree=observed_tree,
        sealed_commit_bytes=sealed_commit,
        sealed_tree_bytes=sealed_tree,
        finalization_commit=str(fin.get("candidate_commit") or ""),
        finalization_tree=str(fin.get("candidate_tree") or ""),
        bundle_heads=bundle_heads(),
        sealed_bundle_sha256=bundle_sha,
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
            "candidate_bundle_sha256": bundle_sha,
            "staging_generation": staging_generation,
            "worker_container_id": live_1b["worker_container_id"],
            "worker_started_at": live_1b["worker_started_at"],
            "worker_image_digest": live_1b["worker_image_digest"],
            "worker_netns_identity": live_1b["worker_netns_identity"],
            "n8n_container_id": live_1b["n8n_container_id"],
            "topology_attestation_identity": live_1b["topology_attestation_sha256"],
            "topology_attestation_sequence": int(live_1b["topology_attestation_sequence"]),
            "launcher_observation_sequence": seq.next(),
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
        sequence=seq.next(),
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
            sequence=seq.next(),
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


def _write_generation_allowlist(
    generation_dir: Path,
    *,
    execution_id: str,
    reviewed_head: str,
    candidate_commit: str,
    candidate_tree: str,
    actual_diff: bytes,
    bundle_bytes: bytes,
) -> None:
    generation_dir.mkdir(parents=True, exist_ok=True)
    fin = json.dumps(
        {"candidate_commit": candidate_commit, "candidate_tree": candidate_tree},
        sort_keys=True,
    ).encode()
    payloads: dict[str, bytes] = {name: f"{name}\n".encode() for name in WORKER_EXPORT_ALLOWLIST}
    payloads["candidate_commit"] = f"{candidate_commit}\n".encode()
    payloads["candidate_tree"] = f"{candidate_tree}\n".encode()
    payloads["execution_id"] = f"{execution_id}\n".encode()
    payloads["reviewed_head"] = f"{reviewed_head}\n".encode()
    payloads["authorized_baseline"] = f"{reviewed_head}\n".encode()
    payloads["finalization_result.json"] = fin
    payloads["actual.diff"] = actual_diff
    payloads["actual.diff.sha256"] = f"{hashlib.sha256(actual_diff).hexdigest()}\n".encode()
    payloads["finalization_result.sha256"] = f"{hashlib.sha256(fin).hexdigest()}\n".encode()
    payloads["candidate.bundle"] = bundle_bytes
    payloads["candidate.bundle.sha256"] = f"{hashlib.sha256(bundle_bytes).hexdigest()}\n".encode()
    for name, data in payloads.items():
        (generation_dir / name).write_bytes(data)


def _copy_from_generation(generation_dir: Path) -> CopyFn:
    def copy_fn(argv: list[str]) -> None:
        dest = Path(argv[-1])
        dest.write_bytes((generation_dir / dest.name).read_bytes())

    return copy_fn


def run_rev25_production_finalize(
    *,
    execution_id: str,
    review_id: str,
    state_db: Path,
    repository_root: Path,
    deps: Rev25RuntimeDeps | None = None,
) -> dict[str, Any]:
    """Single production authority path: bind → disposable candidate → Rev 2.5 export."""
    if deps is None:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "Revision 2.5 topology/export providers are required",
            state="FAILED_FROZEN",
        )
    reviewed_head = os.environ.get("SRL_REVIEWED_HEAD", "").strip().lower()
    if len(reviewed_head) != 40:
        raise WorkerError(
            ERROR_CODES["FAILED_FROZEN"],
            "SRL_REVIEWED_HEAD is required for Revision 2.5 finalize",
            state="FAILED_FROZEN",
        )
    authorized_baseline = reviewed_head
    store = ExperienceStore(state_db)
    existing = store.get_finalization(execution_id)
    if existing is not None:
        if existing.get("review_id") != review_id:
            raise WorkerError(
                ERROR_CODES["SI2-REVIEW-CONFLICT"],
                "conflicting second review",
                state="REVIEW_FAILED",
            )
        return existing

    bundle, worktree_path = store.get_execution(execution_id)
    review = store.get_review(review_id)
    proposal, stored_proposal_hash = store.get_proposal_snapshot(bundle["proposal_id"])
    recomputed_proposal_hash = content_sha256(proposal)
    if (
        recomputed_proposal_hash != stored_proposal_hash
        or recomputed_proposal_hash != bundle.get("proposal_sha256")
        or recomputed_proposal_hash != review.get("proposal_sha256")
        or stored_proposal_hash != bundle.get("proposal_sha256")
        or stored_proposal_hash != review.get("proposal_sha256")
    ):
        raise WorkerError(
            ERROR_CODES["SI2-FINALIZE-PROPOSAL-HASH"],
            "canonical proposal hash mismatch at finalization",
            state="FAILED_FROZEN",
        )
    assert_review_bound(review, proposal=proposal, bundle=bundle, root=repository_root)
    current_policy = load_policy(repository_root)
    current_pol_sha = policy_sha256(repository_root)
    assert_finalize_risk_bindings(
        bundle,
        proposal=proposal,
        current_policy=current_policy,
        current_policy_sha256=current_pol_sha,
    )
    store.append_state_event("execution", execution_id, "REVIEW_PENDING", "REVIEW_BOUND")

    repo = resolve_repo_root(repository_root)
    before_fp = source_tree_fingerprint(repo)
    worktree = Path(worktree_path)
    if not worktree.is_dir():
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "frozen worktree missing",
            state="CONTENT_BINDING_MISMATCH",
        )
    abbrev = run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=worktree,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    ).stdout.decode().strip()
    if abbrev != "HEAD":
        raise WorkerError(
            ERROR_CODES["BRANCH_BEFORE_REVIEW"],
            "branch present before finalization commit",
            state="FAILED_FROZEN",
        )
    head = worktree_head(worktree)
    if head != bundle["baseline_sha"]:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "worktree HEAD left baseline before commit",
            state="CONTENT_BINDING_MISMATCH",
        )
    try:
        tree = staged_tree_sha(worktree)
        diff_hash = actual_diff_sha256(worktree, bundle["baseline_sha"])
        paths = changed_paths_since(worktree, bundle["baseline_sha"])
        paths_hash = changed_paths_sha256(paths)
        val_hash = content_sha256(bundle.get("validation_results") or [])
    except WorkerError as exc:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            f"recompute failed: {exc.message}",
            state="CONTENT_BINDING_MISMATCH",
        ) from exc
    if (
        tree != bundle["worktree_tree_sha"]
        or diff_hash != bundle["actual_diff_sha256"]
        or paths_hash != bundle["changed_paths_sha256"]
        or sorted(paths) != sorted(bundle.get("changed_paths") or [])
        or val_hash != bundle["validation_results_sha256"]
        or tree != review["worktree_tree_sha"]
        or diff_hash != review["actual_diff_sha256"]
        or val_hash != review["validation_results_sha256"]
    ):
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "binding recomputation mismatch",
            state="CONTENT_BINDING_MISMATCH",
        )
    store.append_state_event("execution", execution_id, "REVIEW_BOUND", "FINALIZATION_REVALIDATED")

    commit = create_local_commit(worktree, proposal["objective"])
    committed_tree = run_git(
        ["rev-parse", "HEAD^{tree}"],
        cwd=worktree,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    ).stdout.decode().strip()
    if committed_tree != bundle["worktree_tree_sha"]:
        raise WorkerError(
            ERROR_CODES["CONTENT_BINDING_MISMATCH"],
            "committed tree != reviewed tree",
            state="CONTENT_BINDING_MISMATCH",
        )
    export_root = Path(tempfile.mkdtemp(prefix="srl-r25-"))
    generation_dir = export_root / "generation"
    generation_dir.mkdir(parents=True, exist_ok=True)
    disposable = export_root / "disposable-repo"
    run_git(
        ["clone", "--no-hardlinks", "--no-local", str(worktree.resolve()), str(disposable.resolve())],
        cwd=export_root,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    )
    run_git(
        ["update-ref", SRL_CANDIDATE_REF, commit],
        cwd=disposable,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    )
    bundle_path = generation_dir / "candidate.bundle"
    run_git(
        ["bundle", "create", str(bundle_path), "HEAD", "srl-candidate"],
        cwd=disposable,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    )
    actual_diff = run_git(
        ["diff", "--binary", reviewed_head, commit],
        cwd=disposable,
        check=True,
        repository_role=REPO_ROLE_DISPOSABLE,
    ).stdout
    _write_generation_allowlist(
        generation_dir,
        execution_id=execution_id,
        reviewed_head=reviewed_head,
        candidate_commit=commit,
        candidate_tree=committed_tree,
        actual_diff=actual_diff,
        bundle_bytes=bundle_path.read_bytes(),
    )
    staging_generation = deps.staging_generation or secrets.token_hex(4)
    copy_fn = deps.copy_fn or _copy_from_generation(generation_dir)
    clone_bundle = deps.clone_bundle or reconstruct_authority_c
    ledger_root = export_root / "ledger"
    durable_root = export_root / "durable"

    def observe_git() -> tuple[str, str, str]:
        ref = run_git(
            ["rev-parse", SRL_CANDIDATE_REF],
            cwd=disposable,
            check=True,
            repository_role=REPO_ROLE_DISPOSABLE,
        ).stdout.decode().strip()
        return commit, committed_tree, ref

    def bundle_heads() -> list[object]:
        return [(commit, SRL_CANDIDATE_REF)]

    run_rev25_export(
        execution_id=execution_id,
        reviewed_head=reviewed_head,
        authorized_baseline=authorized_baseline,
        staging_generation=staging_generation,
        worker_id=deps.worker_id,
        n8n_id=deps.n8n_id,
        expected_image_digest=deps.expected_image_digest,
        inspect_worker=deps.inspect_worker,
        inspect_n8n=deps.inspect_n8n,
        list_all_ids=deps.list_all_ids,
        observe_git=observe_git,
        bundle_heads=bundle_heads,
        worker_generation_dir=generation_dir,
        ledger_root=ledger_root,
        durable_root=durable_root,
        copy_fn=copy_fn,
        recompute_diff=lambda *_: actual_diff,
        clone_bundle=clone_bundle,
        verify_scratch=durable_root / "verify-scratch",
        now_ts=deps.now_ts,
    )
    store.append_state_event("execution", execution_id, "FINALIZATION_REVALIDATED", "CANDIDATE_COMMITTED")

    learning = {
        "schema_version": SCHEMA_VERSION,
        "learning_id": f"learn-{execution_id[:16]}",
        "candidate_id": proposal["candidate_id"],
        "proposal_id": proposal["proposal_id"],
        "execution_id": execution_id,
        "proposal_sha256": bundle["proposal_sha256"],
        "execution_result_sha256": bundle["execution_result_sha256"],
        "problem": proposal["objective"],
        "research_summary": "Offline V2 research validation completed",
        "implementation_summary": f"Frozen execution {execution_id} committed",
        "validation_summary": f"Profile {bundle['validation_profile']} bound",
        "review_findings": [],
        "repair_attempts": int(proposal.get("repair_attempt") or 0),
        "final_outcome": "READY_FOR_HUMAN_PROMOTION",
        "reusable_patterns": ["content-bound-finalize"],
        "failure_patterns": [],
        "confidence": 0.8,
        "promotion_status": "READY_FOR_HUMAN_PROMOTION",
    }
    validate_instance("learning_record", learning, root=repository_root)
    store.insert_learning(learning)
    store.append_state_event("execution", execution_id, "CANDIDATE_COMMITTED", "LEARNING_RECORDED")

    result = {
        "schema_version": SCHEMA_VERSION,
        "execution_id": execution_id,
        "review_id": review_id,
        "binding_verified": True,
        "candidate_commit": commit,
        "candidate_branch": SRL_CANDIDATE_REF,
        "committed_tree_sha": committed_tree,
        "committed_diff_sha256": bundle["actual_diff_sha256"],
        "final_state": "READY_FOR_HUMAN_PROMOTION",
        "error_codes": [],
        "learning_record_id": learning["learning_id"],
    }
    validate_instance("finalization_result", result, root=repository_root)
    store.insert_finalization(result)
    store.append_state_event(
        "execution",
        execution_id,
        "LEARNING_RECORDED",
        "READY_FOR_HUMAN_PROMOTION",
    )
    remove_worktree(repo, worktree)
    after_fp = source_tree_fingerprint(repo)
    if after_fp != before_fp:
        raise WorkerError(
            ERROR_CODES["SOURCE_REPO_CHANGED"],
            "tracked source repository changed during finalization",
            state="FAILED_FROZEN",
        )
    return result
