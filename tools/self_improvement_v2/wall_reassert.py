"""Wall-phase artifact reassertion helpers (tracked tree, index, worktree list).

Used immediately before Zone B to prove Zone A/P did not mutate the reviewed
repository layout. Workflow normalized fingerprint is layered by the normalizer
module when present.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from tools.self_improvement_v2.git_worker import (
    index_fingerprint,
    source_tree_fingerprint,
    working_tree_content_fingerprint,
    worktree_list_fingerprint,
)
from tools.self_improvement_v2.models import ERROR_CODES, WorkerError
from tools.self_improvement_v2.workflow_normalizer import material_fingerprint

REQUIRED_WALL_KEYS = frozenset(
    {
        "source_tree_fingerprint",
        "index_fingerprint",
        "worktree_list_fingerprint",
        "working_tree_content_fingerprint",
    }
)


class WallReassertError(WorkerError):
    def __init__(self, message: str) -> None:
        super().__init__(ERROR_CODES["WALL_REASSERT_MISMATCH"], message, state="POLICY_REJECTED")


def capture_wall_artifact_snapshot(
    root: Path,
    *,
    workflow_fingerprint: str | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Capture fingerprints for Wall reassertion (includes working-tree bytes)."""
    snap = {
        "source_tree_fingerprint": source_tree_fingerprint(root),
        "index_fingerprint": index_fingerprint(root),
        "worktree_list_fingerprint": worktree_list_fingerprint(root),
        "working_tree_content_fingerprint": working_tree_content_fingerprint(root),
    }
    if workflow is not None:
        snap["workflow_normalized_fingerprint"] = material_fingerprint(workflow)
    elif workflow_fingerprint is not None:
        snap["workflow_normalized_fingerprint"] = workflow_fingerprint
    return snap


def combined_wall_fingerprint(snapshot: dict[str, str]) -> str:
    h = hashlib.sha256()
    for key in sorted(snapshot):
        h.update(key.encode("utf-8"))
        h.update(b"\0")
        h.update(snapshot[key].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def assert_wall_artifacts_unchanged(
    root: Path,
    before: dict[str, str],
    *,
    workflow_fingerprint_fn: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Fail closed when required Wall fingerprints drift.

    Caller-supplied `before` must include all REQUIRED_WALL_KEYS — partial key
    sets cannot vacuously pass by omitting keys that would have mismatched.
    """
    missing = sorted(REQUIRED_WALL_KEYS - set(before))
    if missing:
        raise WallReassertError(
            f"Wall before snapshot missing required keys: {', '.join(missing)}"
        )
    workflow_fp = None
    if "workflow_normalized_fingerprint" in before:
        if workflow_fingerprint_fn is None:
            raise WallReassertError("workflow fingerprint required for Wall reassert but helper missing")
        workflow_fp = workflow_fingerprint_fn()
    after = capture_wall_artifact_snapshot(root, workflow_fingerprint=workflow_fp)
    # Always compare the full required set from a fresh capture — not only keys caller chose.
    compare_keys = set(REQUIRED_WALL_KEYS)
    if "workflow_normalized_fingerprint" in before:
        compare_keys.add("workflow_normalized_fingerprint")
    mismatches = sorted(k for k in compare_keys if before.get(k) != after.get(k))
    if mismatches:
        raise WallReassertError(f"Wall artifact mismatch: {', '.join(mismatches)}")
    return {
        "status": "PASS",
        "before": before,
        "after": after,
        "combined_fingerprint": combined_wall_fingerprint(after),
    }
