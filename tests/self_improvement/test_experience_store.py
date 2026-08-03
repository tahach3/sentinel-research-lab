"""Experience store tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement.helpers import load_fixture
from tools.self_improvement.experience_store import ExperienceStore
from tools.self_improvement.models import WorkerError


def test_store_tables_fk_and_learning(tmp_path: Path) -> None:
    db = tmp_path / "exp.sqlite"
    store = ExperienceStore(db)
    candidate = load_fixture("candidate.json")
    proposal = load_fixture("proposal.json")
    store.record_candidate(candidate, "RESEARCH_VALIDATED")
    store.record_proposal(proposal, "PROPOSAL_VALIDATED")
    learning = {
        "schema_version": "1.0.0",
        "candidate_id": candidate["candidate_id"],
        "proposal_id": proposal["proposal_id"],
        "problem": "p",
        "research_summary": "r",
        "implementation_summary": "i",
        "validation_summary": "v",
        "review_findings": [],
        "repair_attempts": 0,
        "final_outcome": "READY_FOR_HUMAN_PROMOTION",
        "reusable_patterns": [],
        "failure_patterns": [],
        "confidence": 0.5,
        "promotion_status": "READY_FOR_HUMAN_PROMOTION",
    }
    store.record_learning(learning, "LEARNING_RECORDED")
    assert store.count_learning_records() == 1
    assert store.latest_learning()["proposal_id"] == proposal["proposal_id"]


def test_rejects_secrets_and_absolute_paths(tmp_path: Path) -> None:
    db = tmp_path / "exp.sqlite"
    store = ExperienceStore(db)
    candidate = load_fixture("candidate.json")
    bad = dict(candidate)
    bad["password"] = "supersecretvalue"
    with pytest.raises(WorkerError):
        store.record_candidate(bad, "X")

    bad2 = dict(candidate)
    bad2["problem"] = "see C:/Users/tahai/secret"
    with pytest.raises(WorkerError):
        store.record_candidate(bad2, "X")
