"""Immutable insert-only SQLite experience store for Self-Improvement Loop V2."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from tools.self_improvement_v2.canonical import content_sha256
from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError


def _assert_safe_payload(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True)
    lower = encoded.lower()
    if any(frag in lower for frag in ('"password": "', '"api_key": "', '"secret": "', "bearer ")):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "payload appears to contain secrets")
    if re.search(r"[A-Za-z]:[/\\]", encoded):
        raise WorkerError(ERROR_CODES["POLICY_REJECTED"], "absolute local paths must not be stored")


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
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                  candidate_id TEXT PRIMARY KEY,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposal_snapshots (
                  proposal_id TEXT PRIMARY KEY,
                  candidate_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL UNIQUE,
                  baseline_sha TEXT NOT NULL,
                  policy_sha256 TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS execution_bundles (
                  execution_id TEXT PRIMARY KEY,
                  proposal_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL UNIQUE,
                  proposal_sha256 TEXT NOT NULL,
                  worktree_path TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(proposal_id) REFERENCES proposal_snapshots(proposal_id)
                );
                CREATE TABLE IF NOT EXISTS review_snapshots (
                  review_id TEXT PRIMARY KEY,
                  execution_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL UNIQUE,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(execution_id) REFERENCES execution_bundles(execution_id)
                );
                CREATE TABLE IF NOT EXISTS finalization_results (
                  execution_id TEXT PRIMARY KEY,
                  review_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(execution_id) REFERENCES execution_bundles(execution_id),
                  FOREIGN KEY(review_id) REFERENCES review_snapshots(review_id)
                );
                CREATE TABLE IF NOT EXISTS learning_records (
                  learning_id TEXT PRIMARY KEY,
                  candidate_id TEXT NOT NULL,
                  proposal_id TEXT NOT NULL,
                  execution_id TEXT NOT NULL,
                  schema_version TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL UNIQUE,
                  payload_json TEXT NOT NULL,
                  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id),
                  FOREIGN KEY(proposal_id) REFERENCES proposal_snapshots(proposal_id),
                  FOREIGN KEY(execution_id) REFERENCES execution_bundles(execution_id)
                );
                CREATE TABLE IF NOT EXISTS state_events (
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
            # Defense-in-depth: block UPDATE/DELETE on immutable content tables.
            # Application API remains insert-only / idempotent-duplicate.
            self._ensure_immutability_triggers()

    def _ensure_immutability_triggers(self) -> None:
        tables = (
            "proposal_snapshots",
            "execution_bundles",
            "review_snapshots",
            "finalization_results",
        )
        with self._connect() as conn:
            for table in tables:
                for op in ("UPDATE", "DELETE"):
                    name = f"si2_deny_{op.lower()}_{table}"
                    conn.execute(f"DROP TRIGGER IF EXISTS {name}")
                    conn.execute(
                        f"""
                        CREATE TRIGGER {name}
                        BEFORE {op} ON {table}
                        BEGIN
                          SELECT RAISE(ABORT, 'SI2-STORE-DATABASE-IMMUTABILITY');
                        END;
                        """
                    )

    def _insert_immutable(
        self,
        table: str,
        id_col: str,
        id_value: str,
        columns: dict[str, Any],
        payload: dict[str, Any],
        *,
        extra_unique_hash: bool = True,
    ) -> str:
        _assert_safe_payload(payload)
        digest = content_sha256(payload)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                f"SELECT content_sha256, payload_json FROM {table} WHERE {id_col} = ?",
                (id_value,),
            ).fetchone()
            if existing:
                if existing[0] == digest:
                    return digest
                raise WorkerError(
                    ERROR_CODES["SI2-STORE-IMMUTABILITY"],
                    f"{table} content change for {id_value}",
                    state="IMMUTABILITY_VIOLATION",
                )
            cols = [id_col, *columns.keys(), "schema_version", "content_sha256", "payload_json"]
            values = [id_value, *columns.values(), SCHEMA_VERSION, digest, blob]
            placeholders = ", ".join("?" for _ in cols)
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
            try:
                conn.execute(sql, values)
            except sqlite3.IntegrityError as exc:
                raise WorkerError(
                    ERROR_CODES["SI2-STORE-IMMUTABILITY"],
                    f"{table} uniqueness violation: {exc}",
                    state="IMMUTABILITY_VIOLATION",
                ) from exc
        return digest

    def insert_candidate(self, candidate: dict[str, Any]) -> str:
        return self._insert_immutable(
            "candidates",
            "candidate_id",
            candidate["candidate_id"],
            {},
            candidate,
        )

    def insert_proposal(
        self,
        proposal: dict[str, Any],
        *,
        policy_sha256: str,
    ) -> str:
        return self._insert_immutable(
            "proposal_snapshots",
            "proposal_id",
            proposal["proposal_id"],
            {
                "candidate_id": proposal["candidate_id"],
                "baseline_sha": proposal["baseline_sha"],
                "policy_sha256": policy_sha256,
            },
            proposal,
        )

    def insert_execution_bundle(
        self,
        bundle: dict[str, Any],
        *,
        worktree_path: str,
    ) -> str:
        # Persist absolute worktree paths outside SQLite (redacted runtime token in DB).
        token = self._store_runtime_worktree(bundle["execution_id"], worktree_path)
        return self._insert_immutable(
            "execution_bundles",
            "execution_id",
            bundle["execution_id"],
            {
                "proposal_id": bundle["proposal_id"],
                "proposal_sha256": bundle["proposal_sha256"],
                "worktree_path": token,
            },
            bundle,
        )

    def insert_review(self, review: dict[str, Any]) -> str:
        # Zone P synthetic reviews must never land in the durable ledger basename.
        if review.get("synthetic_control") is True:
            if self.db_path.name == "self-improvement-v2.sqlite":
                raise WorkerError(
                    ERROR_CODES["ZONE_P_HARNESS"],
                    "synthetic_control review refused on durable ledger basename",
                    state="POLICY_REJECTED",
                )
            if not review.get("probe_id"):
                raise WorkerError(
                    ERROR_CODES["ZONE_P_HARNESS"],
                    "synthetic_control review requires probe_id",
                    state="POLICY_REJECTED",
                )
        return self._insert_immutable(
            "review_snapshots",
            "review_id",
            review["review_id"],
            {"execution_id": review["execution_id"]},
            review,
        )

    def insert_finalization(self, result: dict[str, Any]) -> str:
        digest = content_sha256(result)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT review_id, content_sha256, payload_json FROM finalization_results WHERE execution_id = ?",
                (result["execution_id"],),
            ).fetchone()
            if existing:
                if existing[0] != result["review_id"]:
                    raise WorkerError(
                        ERROR_CODES["SI2-REVIEW-CONFLICT"],
                        "conflicting second review finalization",
                        state="REVIEW_FAILED",
                    )
                return existing[1]
            blob = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO finalization_results (
                  execution_id, review_id, schema_version, content_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result["execution_id"],
                    result["review_id"],
                    SCHEMA_VERSION,
                    digest,
                    blob,
                ),
            )
        return digest

    def insert_learning(self, learning: dict[str, Any]) -> str:
        return self._insert_immutable(
            "learning_records",
            "learning_id",
            learning["learning_id"],
            {
                "candidate_id": learning["candidate_id"],
                "proposal_id": learning["proposal_id"],
                "execution_id": learning["execution_id"],
            },
            learning,
        )

    def append_state_event(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str | None,
        to_state: str,
        error_code: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        body = payload or {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "from_state": from_state,
            "to_state": to_state,
        }
        digest = content_sha256(body)
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO state_events (
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

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        payload, _digest = self.get_proposal_snapshot(proposal_id)
        return payload

    def get_proposal_snapshot(self, proposal_id: str) -> tuple[dict[str, Any], str]:
        """Return (payload, stored content_sha256) from the immutable proposal snapshot row."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, content_sha256 FROM proposal_snapshots WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if not row:
            raise WorkerError(ERROR_CODES["SI2-REVIEW-MISSING"], "proposal missing", state="REVIEW_FAILED")
        return json.loads(row[0]), str(row[1])

    def _runtime_map_path(self) -> Path:
        return Path(str(self.db_path) + ".runtime.json")

    def _store_runtime_worktree(self, execution_id: str, abs_path: str) -> str:
        """Persist absolute worktree only in a sidecar map; DB gets a redacted runtime token."""
        token = f"runtime:{execution_id}"
        path = self._runtime_map_path()
        data: dict[str, str] = {}
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
        data[execution_id] = abs_path
        path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        return token

    def _resolve_runtime_worktree(self, ref: str, execution_id: str) -> str:
        if ref.startswith("runtime:"):
            path = self._runtime_map_path()
            if not path.is_file():
                raise WorkerError(
                    ERROR_CODES["CONTENT_BINDING_MISMATCH"],
                    "runtime worktree map missing",
                    state="CONTENT_BINDING_MISMATCH",
                )
            data = json.loads(path.read_text(encoding="utf-8"))
            resolved = data.get(execution_id)
            if not resolved:
                raise WorkerError(
                    ERROR_CODES["CONTENT_BINDING_MISMATCH"],
                    "runtime worktree token unresolved",
                    state="CONTENT_BINDING_MISMATCH",
                )
            return resolved
        return ref

    def get_execution(self, execution_id: str) -> tuple[dict[str, Any], str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, worktree_path FROM execution_bundles WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if not row:
            raise WorkerError(ERROR_CODES["SI2-REVIEW-MISSING"], "execution missing", state="REVIEW_FAILED")
        ref = str(row[1])
        return json.loads(row[0]), self._resolve_runtime_worktree(ref, execution_id)

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM review_snapshots WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if not row:
            raise WorkerError(ERROR_CODES["SI2-REVIEW-MISSING"], "review missing", state="REVIEW_FAILED")
        return json.loads(row[0])

    def get_finalization(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM finalization_results WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def list_reviews_for_execution(self, execution_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM review_snapshots WHERE execution_id = ?",
                (execution_id,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count_learning_records(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM learning_records").fetchone()
            return int(row[0])
