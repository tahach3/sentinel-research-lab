import sqlite3
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


def test_sqlite_triggers_block_update_delete(tmp_path: Path):
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
    prop = build_proposal("a" * 40)
    prop["candidate_id"] = "c1"
    store.insert_proposal(prop, policy_sha256="b" * 64)
    conn = sqlite3.connect(str(db))
    try:
        with pytest.raises(sqlite3.IntegrityError) as ei:
            conn.execute(
                "UPDATE proposal_snapshots SET content_sha256 = ? WHERE proposal_id = ?",
                ("f" * 64, prop["proposal_id"]),
            )
        assert "SI2-STORE-DATABASE-IMMUTABILITY" in str(ei.value)
        with pytest.raises(sqlite3.IntegrityError) as ei2:
            conn.execute(
                "DELETE FROM proposal_snapshots WHERE proposal_id = ?",
                (prop["proposal_id"],),
            )
        assert "SI2-STORE-DATABASE-IMMUTABILITY" in str(ei2.value)
    finally:
        conn.close()
