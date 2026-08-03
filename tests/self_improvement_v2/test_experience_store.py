from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import SCHEMA_VERSION, build_proposal
from tools.self_improvement_v2.experience_store import ExperienceStore
from tools.self_improvement_v2.models import WorkerError


def test_insert_only_and_immutability(tmp_path: Path):
    db = tmp_path / "s.sqlite"
    store = ExperienceStore(db)
    cand = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": "c1",
        "repository_id": "sentinel-research-lab",
        "problem": "p",
        "evidence": ["e"],
        "expected_benefit": "b",
        "success_metrics": ["m"],
        "risk_indicators": [],
        "source_agent": "a",
        "created_from_run": "r",
    }
    store.insert_candidate(cand)
    store.insert_candidate(cand)
    prop = build_proposal("a" * 40)
    prop["candidate_id"] = "c1"
    store.insert_proposal(prop, policy_sha256="b" * 64)
    altered = dict(prop)
    altered["objective"] = "changed"
    with pytest.raises(WorkerError) as ei:
        store.insert_proposal(altered, policy_sha256="b" * 64)
    assert ei.value.code == "SI2-STORE-IMMUTABILITY"
