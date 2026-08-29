"""SQLite experience store with explicit path and no secret persistence."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from tools.self_improvement.models import ERROR_CODES, WorkerError
from tools.self_improvement.schema_loader import content_sha256

SCHEMA_VERSION = "1.0.0"

def _assert_safe_payload(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True)
    lower = encoded.lower()
    if any(frag in lower for frag in ('"password": "', '"api_key": "', '"secret": "', "bearer ")):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "payload appears to contain secrets")
    if re.search(r"[A-Za-z]:[/\\]", encoded):
        raise WorkerError(
            ERROR_CODES["POLICY_REJECTED"],
            "absolute local paths must not be stored",
        )


class ExperienceStore:
    def __init__(self, db_path: Path) -> None:
        if not db_path:
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "state-db path required")
        self.db_path = Path(db_path)
        if self.db_path.exists() and self.db_path.is_dir():
            raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "state-db must be a file path")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS improvement_candidates (
                  candidate_id TEXT PRIMARY KEY,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS implementation_proposals (
                  proposal_id TEXT PRIMARY KEY,
                  candidate_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS execution_runs (
                  run_id TEXT PRIMARY KEY,
                  proposal_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(proposal_id) REFERENCES implementation_proposals(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS validation_results (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(run_id) REFERENCES execution_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS review_results (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  proposal_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(proposal_id) REFERENCES implementation_proposals(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS learning_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  candidate_id TEXT NOT NULL,
                  proposal_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  state TEXT NOT NULL,
                  error_code TEXT,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id),
                  FOREIGN KEY(proposal_id) REFERENCES implementation_proposals(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS state_transitions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity_type TEXT NOT NULL,
                  entity_id TEXT NOT NULL,
                  from_state TEXT,
                  to_state TEXT NOT NULL,
                  error_code TEXT,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                """
            )

    def _upsert(
        self,
        table: str,
        columns: dict[str, str],
        *,
        conflict_cols: list[str],
        state: str,
        error_code: str | None,
        payload: dict[str, Any],
    ) -> None:
        _assert_safe_payload(payload)
        digest = content_sha256(payload)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        cols = list(columns.keys()) + [
            "schema_version",
            "content_sha256",
            "state",
            "error_code",
            "payload_json",
        ]
        values = list(columns.values()) + [SCHEMA_VERSION, digest, state, error_code, blob]
        placeholders = ", ".join("?" for _ in cols)
        col_sql = ", ".join(cols)
        # Tables with INTEGER PK use INSERT only.
        if table in {"validation_results", "review_results", "learning_records", "state_transitions"}:
            sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
            with self._connect() as conn:
                conn.execute(sql, values)
            return
        updates = ", ".join(
            f"{c}=excluded.{c}"
            for c in cols
            if c not in conflict_cols
        )
        conflict = ", ".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        )
        with self._connect() as conn:
            conn.execute(sql, values)

    def record_candidate(self, candidate: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "improvement_candidates",
            {"candidate_id": candidate["candidate_id"]},
            conflict_cols=["candidate_id"],
            state=state,
            error_code=error_code,
            payload=candidate,
        )

    def record_proposal(self, proposal: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "implementation_proposals",
            {
                "proposal_id": proposal["proposal_id"],
                "candidate_id": proposal["candidate_id"],
            },
            conflict_cols=["proposal_id"],
            state=state,
            error_code=error_code,
            payload=proposal,
        )

    def record_execution(self, run_id: str, result: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "execution_runs",
            {"run_id": run_id, "proposal_id": result["proposal_id"]},
            conflict_cols=["run_id"],
            state=state,
            error_code=error_code,
            payload=result,
        )

    def record_validation(self, run_id: str, payload: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "validation_results",
            {"run_id": run_id},
            conflict_cols=[],
            state=state,
            error_code=error_code,
            payload=payload,
        )

    def record_review(self, review: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "review_results",
            {"proposal_id": review["proposal_id"]},
            conflict_cols=[],
            state=state,
            error_code=error_code,
            payload=review,
        )

    def record_learning(self, learning: dict[str, Any], state: str, error_code: str | None = None) -> None:
        self._upsert(
            "learning_records",
            {
                "candidate_id": learning["candidate_id"],
                "proposal_id": learning["proposal_id"],
            },
            conflict_cols=[],
            state=state,
            error_code=error_code,
            payload=learning,
        )

    def record_transition(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str | None,
        to_state: str,
        error_code: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        body = payload or {"entity_type": entity_type, "entity_id": entity_id}
        digest = content_sha256(body)
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO state_transitions (
                  entity_type, entity_id, from_state, to_state, error_code,
                  schema_version, content_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_type,
                    entity_id,
                    from_state,
                    to_state,
                    error_code,
                    SCHEMA_VERSION,
                    digest,
                    blob,
                ),
            )

    def count_learning_records(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM learning_records").fetchone()
            return int(row[0])

    def latest_learning(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM learning_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
