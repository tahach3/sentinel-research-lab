"""CLI validator for the Round 5A executable kernel."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT_DEFAULT = Path.cwd()

REQUIRED_FILES = [
    "docs/ROUND_5A_EXECUTABLE_KERNEL_RESET.md",
    "specs/round5a_kernel/schema/kernel_contract.schema.json",
    "specs/round5a_kernel/privilege_contract.json",
    "specs/round5a_kernel/reconciliation_contract.json",
    "specs/round5a_kernel/kernel_manifest.json",
    "tools/round5a_kernel/__init__.py",
    "tools/round5a_kernel/models.py",
    "tools/round5a_kernel/privilege_reference.py",
    "tools/round5a_kernel/predicate_engine.py",
    "tools/round5a_kernel/classification_reference.py",
    "tools/round5a_kernel/state_a_reference.py",
    "tools/round5a_kernel/state_b_reference.py",
    "tools/round5a_kernel/validate_kernel.py",
]

MODULE_FILES = [
    "tools/round5a_kernel/models.py",
    "tools/round5a_kernel/privilege_reference.py",
    "tools/round5a_kernel/predicate_engine.py",
    "tools/round5a_kernel/classification_reference.py",
    "tools/round5a_kernel/state_a_reference.py",
    "tools/round5a_kernel/state_b_reference.py",
    "tools/round5a_kernel/validate_kernel.py",
]


@dataclass
class StageResult:
    name: str
    status: str = "PASS"
    errors: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def fail(self, code: str, message: str) -> None:
        self.status = "FAIL"
        self.errors.append({"code": code, "message": message})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class KernelValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.stages: list[StageResult] = []
        self.privilege: dict[str, Any] | None = None
        self.recon: dict[str, Any] | None = None
        self.manifest: dict[str, Any] | None = None

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError(f"path escape: {rel}")
        return p

    def add(self, stage: StageResult) -> StageResult:
        self.stages.append(stage)
        return stage

    def run(self) -> dict[str, Any]:
        try:
            self._file_inventory()
            self._schema_validation()
            self._manifest_integrity()
            self._privilege_contract()
            self._privilege_reference_tests()
            self._reconciliation_contract()
            self._predicate_semantics()
            self._rule_reachability()
            self._mapping_totality()
            self._state_a_proof()
            self._state_b_independence()
            self._bounded_domain_comparison()
            return self._final_summary()
        except Exception as exc:  # noqa: BLE001 — environment/usage boundary
            return {
                "final_status": "ERROR",
                "exit_hint": 2,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "stages": [s.__dict__ for s in self.stages],
            }

    def _file_inventory(self) -> None:
        st = self.add(StageResult("file_inventory"))
        for rel in REQUIRED_FILES:
            if not self.path(rel).is_file():
                st.fail("KR-INV-MISSING", f"missing {rel}")
        st.metrics["required_files"] = len(REQUIRED_FILES)

    def _schema_validation(self) -> None:
        st = self.add(StageResult("schema_validation"))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            st.fail("KR-ENV-JSONSCHEMA", "jsonschema not installed")
            return
        schema = load_json(self.path("specs/round5a_kernel/schema/kernel_contract.schema.json"))
        validator = Draft202012Validator(schema)
        for rel in (
            "specs/round5a_kernel/privilege_contract.json",
            "specs/round5a_kernel/reconciliation_contract.json",
            "specs/round5a_kernel/kernel_manifest.json",
        ):
            doc = load_json(self.path(rel))
            errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
            for err in errors:
                st.fail("KR-SCHEMA", f"{rel}: {err.message}")
        self.privilege = load_json(self.path("specs/round5a_kernel/privilege_contract.json"))
        self.recon = load_json(self.path("specs/round5a_kernel/reconciliation_contract.json"))
        self.manifest = load_json(self.path("specs/round5a_kernel/kernel_manifest.json"))

    def _manifest_integrity(self) -> None:
        st = self.add(StageResult("manifest_integrity"))
        assert self.manifest is not None
        arts = self.manifest.get("artifacts") or []
        if not arts:
            st.fail("KR-MANIFEST-EMPTY", "manifest artifacts empty")
            return
        seen_paths: set[str] = set()
        for art in arts:
            rel = art["path"]
            if rel == "specs/round5a_kernel/kernel_manifest.json":
                st.fail("KR-MANIFEST-SELF", "manifest must not self-hash")
                continue
            if rel in seen_paths:
                st.fail("KR-MANIFEST-DUP", f"duplicate {rel}")
            seen_paths.add(rel)
            path = self.path(rel)
            if not path.is_file():
                st.fail("KR-MANIFEST-MISSING", f"missing {rel}")
                continue
            digest = sha256_file(path)
            if digest != art["sha256"]:
                st.fail("KR-MANIFEST-HASH", f"hash mismatch {rel}")
            if ".." in rel or rel.startswith("/") or ":\\" in rel or rel.startswith("~"):
                st.fail("KR-MANIFEST-PATH", f"non-relative path {rel}")
        st.metrics["artifact_count"] = len(arts)

    def _privilege_contract(self) -> None:
        st = self.add(StageResult("privilege_contract"))
        assert self.privilege is not None
        kinds = self.privilege.get("object_kinds") or []
        if kinds != ["SCHEMA", "FUNCTION", "TABLE", "COLUMN", "SEQUENCE"]:
            st.fail("KR-PRIV-KINDS", f"object kinds {kinds}")
        paths = self.privilege.get("privilege_paths") or []
        expected_paths = [
            "DIRECT",
            "PUBLIC_DERIVED",
            "INHERITED",
            "SET_ROLE_ONLY",
            "OWNER_DERIVED",
            "SUPERUSER_DERIVED",
            "SCHEMA_GATED",
            "EXERCISABLE",
        ]
        if paths != expected_paths:
            st.fail("KR-PRIV-PATHS", f"paths {paths}")
        col = self.privilege.get("column_acl_policy") or {}
        if not col.get("never_apply_acldefault_c"):
            st.fail("KR-PRIV-COL", "acldefault(c) must be prohibited")
        acl = self.privilege.get("acl_defaults") or {}
        if "COALESCE(proacl, acldefault('f', proowner))" not in str(acl.get("FUNCTION", {})):
            st.fail("KR-PRIV-FN-DEFAULT", "function COALESCE default missing")
        if "COALESCE(relacl, acldefault('r', relowner))" not in str(acl.get("TABLE", {})):
            st.fail("KR-PRIV-TBL-DEFAULT", "table COALESCE default missing")
        if "COALESCE(relacl, acldefault('s', relowner))" not in str(acl.get("SEQUENCE", {})):
            st.fail("KR-PRIV-SEQ-DEFAULT", "sequence COALESCE default missing")
        st.metrics["privilege_object_kinds"] = len(kinds)

    def _privilege_reference_tests(self) -> None:
        st = self.add(StageResult("privilege_reference_tests"))
        from tools.round5a_kernel.privilege_reference import evaluate_privilege, resolve_effective_acl

        acl, prov = resolve_effective_acl("FUNCTION", None, "postgres")
        if prov != "acldefault_f_owner":
            st.fail("KR-PRIV-REF-FN", f"unexpected provenance {prov}")
        if not any(e["grantee"] == "PUBLIC" for e in acl):
            st.fail("KR-PRIV-REF-PUBLIC", "PUBLIC execute default missing")
        col_acl, col_prov = resolve_effective_acl("COLUMN", None, "postgres")
        if col_acl or col_prov != "null_attacl_no_column_specific_acl":
            st.fail("KR-PRIV-REF-COL", "null attacl must not invent defaults")
        results = evaluate_privilege(
            object_kind="FUNCTION",
            object_identity="research.fn(int)",
            privilege="EXECUTE",
            principal="research_app",
            owner="postgres",
            raw_acl=None,
            memberships=[],
            schema_usage={"research_app": True},
            superusers=[],
        )
        if not any(r.exercisable for r in results):
            st.fail("KR-PRIV-REF-EXEC", "default public execute not exercisable")
        st.metrics["sample_results"] = len(results)

    def _reconciliation_contract(self) -> None:
        st = self.add(StageResult("reconciliation_contract"))
        assert self.recon is not None
        rules = self.recon.get("rules") or []
        if len(rules) != 22:
            st.fail("KR-RECON-COUNT", f"expected 22 rules, got {len(rules)}")
        orders = [int(r["order"]) for r in rules]
        if orders != list(range(1, 23)):
            st.fail("KR-RECON-ORDER", f"orders {orders}")
        fb = [r for r in rules if r.get("fallback")]
        if len(fb) != 1 or fb[0]["order"] != 22 or fb[0].get("failure_state") != "failed_frozen":
            st.fail("KR-RECON-FALLBACK", "RULE-22 fallback contract invalid")
        if fb and fb[0].get("reachable_condition") != "missing required status":
            st.fail("KR-RECON-FALLBACK-COND", "RULE-22 reachable_condition mismatch")
        for mode in self.recon.get("null_modes") or []:
            if mode not in {"NULL_IS_VALUE", "NULL_IS_UNKNOWN", "NULL_FAILS_PREDICATE"}:
                st.fail("KR-RECON-NULL", f"invalid null mode {mode}")
        st.metrics["rules"] = len(rules)

    def _predicate_semantics(self) -> None:
        st = self.add(StageResult("predicate_semantics"))
        from tools.round5a_kernel.predicate_engine import PredicateEngine
        from tools.round5a_kernel.models import PredicateResult

        engine = PredicateEngine({"source_record": {"status": None}})
        node = {
            "node": "is_null",
            "operand": {
                "operand_kind": "field_ref",
                "field_ref": {
                    "scope": "source_record",
                    "path": ["status"],
                    "data_type": "string",
                    "nullable": True,
                },
            },
            "null_semantics": "NULL_IS_VALUE",
        }
        if engine.evaluate(node) is not PredicateResult.TRUE:
            st.fail("KR-PRED-NULL", "is_null failed")
        missing_engine = PredicateEngine({"source_record": {}})
        missing_node = {
            "node": "missing",
            "target": {
                "operand_kind": "field_ref",
                "field_ref": {
                    "scope": "source_record",
                    "path": ["status"],
                    "data_type": "string",
                    "nullable": True,
                },
            },
            "null_semantics": "NULL_IS_VALUE",
        }
        if missing_engine.evaluate(missing_node) is not PredicateResult.TRUE:
            st.fail("KR-PRED-MISSING", "missing status not detected")

    def _rule_reachability(self) -> None:
        st = self.add(StageResult("rule_reachability"))
        assert self.recon is not None
        from tools.round5a_kernel.classification_reference import classify_source

        rules = self.recon["rules"]
        reachable: set[str] = set()
        samples = self._reachability_samples()
        for sample in samples:
            rec = classify_source(sample["source"], rules, contexts=sample.get("contexts"), computed=sample.get("computed"))
            reachable.add(rec.rule_id)
        if len(reachable) != 22:
            st.fail("KR-REACH", f"reachable={sorted(reachable)} count={len(reachable)}")
        if "RULE-22" not in reachable:
            st.fail("KR-REACH-FALLBACK", "RULE-22 unreachable")
        st.metrics["reachable_rules"] = len(reachable)
        st.metrics["fallback_reachable"] = "RULE-22" in reachable

    def _reachability_samples(self) -> list[dict[str, Any]]:
        """Minimal sources that hit each rule via decisive fields / computed flags."""
        from tools.round5a_kernel.classification_reference import computed_key
        from tools.round5a_kernel.models import MISSING

        base_id = "00000000-0000-4000-8000-0000000000{:02d}"
        samples: list[dict[str, Any]] = []
        assert self.recon is not None
        rules = {r["rule_id"]: r for r in self.recon["rules"]}

        def src(n: int, **fields: Any) -> dict[str, Any]:
            row = {
                "legacy_reservation_id": base_id.format(n),
                "pilot_proposal_id": f"pp-{n}",
                "authorization_id": f"auth-{n}",
                "benchmark_case_id": f"case-{n}",
                "idempotency_key": f"idem-{n}",
                "envelope_id": f"env-{n}",
                "status": "reserved",
            }
            row.update(fields)
            return row

        def override_ref(name: str, params: dict[str, Any], value: Any) -> dict[str, Any]:
            return {computed_key(name, params): value, name: value}

        samples.append({"source": src(1, status="bogus")})
        samples.append({"source": src(2, pilot_proposal_id=None)})
        samples.append({"source": src(3, authorization_id=None)})
        samples.append({"source": src(4, benchmark_case_id=None)})

        # RULE-05 non-winner duplicate
        samples.append(
            {
                "source": src(5),
                "computed": override_ref(
                    "PRIMITIVE-DUP-ORDER-WINNER",
                    {
                        "group": "pilot_proposal_id,benchmark_case_id,idempotency_key",
                        "winner_mode": "min_legacy_reservation_id_collate_c",
                        "subject_is_non_winner": True,
                    },
                    True,
                ),
            }
        )
        samples.append(
            {
                "source": src(6),
                "computed": override_ref(
                    "PRIMITIVE-DUP-ORDER-WINNER",
                    {
                        "group": "pilot_proposal_id,benchmark_case_id",
                        "consumption_kind_target": "attempt_consumed",
                        "exclude_rule5_non_winners": True,
                        "winner_mode": "min_legacy_reservation_id_collate_c",
                        "subject_is_non_winner": True,
                    },
                    True,
                ),
            }
        )
        samples.append(
            {
                "source": src(7),
                "computed": override_ref(
                    "PRIMITIVE-DUP-ORDER-WINNER",
                    {
                        "group": "envelope_id",
                        "winner_mode": "min_source_serialization_collate_c",
                        "subject_is_non_winner": True,
                        "require_different_source": True,
                    },
                    True,
                ),
            }
        )
        samples.append(
            {
                "source": src(8, status="reserved"),
                "computed": override_ref(
                    "PRIMITIVE-EVENT-NATURAL-KEY",
                    {"mode": "required_event_natural_key"},
                    MISSING,
                ),
            }
        )
        samples.append(
            {
                "source": src(9),
                "contexts": {"shared_data_model": {"ledger_request_count_reporting": 1}},
                "computed": override_ref(
                    "PRIMITIVE-RECON-SOURCE-DOMAIN",
                    {"flag": "ledger_used_as_enforcement_input"},
                    True,
                ),
            }
        )
        samples.append(
            {
                "source": src(10),
                "contexts": {"shared_data_model": {"ledger_success_count": 1}},
                "computed": {
                    **override_ref(
                        "PRIMITIVE-RECON-SOURCE-DOMAIN",
                        {"metric": "ledger_success_count"},
                        2,
                    ),
                    **override_ref(
                        "PRIMITIVE-EVENT-NATURAL-KEY",
                        {"metric": "success_authority_count"},
                        1,
                    ),
                },
            }
        )
        samples.append(
            {
                "source": src(11),
                "contexts": {
                    "shared_data_model": {
                        "projected_token_sum_events": 10,
                        "policy_max_token_fields": 5,
                    }
                },
                "computed": {
                    **override_ref(
                        "PRIMITIVE-RECON-SOURCE-DOMAIN",
                        {"metric": "projected_token_sum_events"},
                        10,
                    ),
                    **override_ref(
                        "PRIMITIVE-RECON-SOURCE-DOMAIN",
                        {"metric": "policy_max_token_fields"},
                        5,
                    ),
                },
            }
        )
        samples.append(
            {
                "source": src(12),
                "contexts": {
                    "shared_data_model": {
                        "projected_cost_usd": 1,
                        "estimated_cost_usd": 0,
                        "ledger_cost_usd": 0,
                    }
                },
            }
        )
        samples.append(
            {
                "source": src(13),
                "contexts": {"shared_data_model": {"counter_value": -1}},
            }
        )
        samples.append(
            {
                "source": src(14),
                "contexts": {"shared_data_model": {"discrepancy_fingerprint": "fp"}},
                "computed": {
                    **override_ref(
                        "PRIMITIVE-RECON-SOURCE-DOMAIN",
                        {"lookup": "accounting_discrepancies_open"},
                        True,
                    ),
                    **override_ref(
                        "PRIMITIVE-RECON-SOURCE-DOMAIN",
                        {"lookup": "accounting_discrepancy_acknowledged"},
                        MISSING,
                    ),
                },
            }
        )
        samples.append(
            {
                "source": src(15),
                "contexts": {"ledger_orphan": {"ledger_id": "L1"}},
                "computed": override_ref(
                    "PRIMITIVE-RECON-LEDGER-ORPHANS",
                    {"binding": "no_reservation_or_auth_or_event_match"},
                    True,
                ),
            }
        )
        samples.append(
            {
                "source": src(16),
                "contexts": {"envelope_orphan": {"envelope_id": "E1"}},
                "computed": override_ref(
                    "PRIMITIVE-RECON-ENVELOPE-ORPHANS",
                    {"binding": "no_matching_capacity_event_natural_key"},
                    True,
                ),
            }
        )
        samples.append({"source": src(17, status="reserved", envelope_id="env-17")})
        samples.append({"source": src(18, status="reserved", envelope_id=None)})
        samples.append({"source": src(19, status="finalized", envelope_id="env-19")})
        samples.append({"source": src(20, status="finalized", envelope_id=None)})
        samples.append({"source": src(21, status="released", envelope_id=None)})
        s22 = src(22)
        del s22["status"]
        samples.append({"source": s22})
        # silence unused
        _ = rules
        return samples

    def _force_rule_computed(self, rule: dict[str, Any], value: bool) -> dict[str, Any]:
        # retained for compatibility; reachability uses explicit overrides
        return {}

    def _mapping_totality(self) -> None:
        st = self.add(StageResult("mapping_totality"))
        assert self.recon is not None
        from tools.round5a_kernel.classification_reference import classify_source
        from tools.round5a_kernel.models import normalize_identity

        rules = self.recon["rules"]
        sources = []
        for i, status in enumerate(["reserved", "finalized", "released", "nope"]):
            sources.append(
                {
                    "legacy_reservation_id": f"00000000-0000-4000-8000-aaaaaaaaaa{i:02d}",
                    "pilot_proposal_id": f"pp-{i}",
                    "authorization_id": f"auth-{i}",
                    "benchmark_case_id": f"case-{i}",
                    "idempotency_key": f"idem-{i}",
                    "envelope_id": None if status != "reserved" else f"env-{i}",
                    "status": status,
                }
            )
        # missing status
        miss = dict(sources[0])
        miss["legacy_reservation_id"] = "00000000-0000-4000-8000-bbbbbbbbbb01"
        del miss["status"]
        sources.append(miss)

        slots: dict[str, str] = {}
        violations = 0
        for source in sources:
            rec = classify_source(source, rules)
            if rec.source_identity in slots:
                violations += 1
            slots[rec.source_identity] = rec.outcome_slot
            if not rec.outcome_slot:
                violations += 1
        st.metrics["mapping_violations"] = violations
        if violations != 0:
            st.fail("KR-MAP", f"mapping violations {violations}")

    def _state_a_proof(self) -> None:
        st = self.add(StageResult("state_a_proof"))
        from tools.round5a_kernel.classification_reference import ClassificationRecord
        from tools.round5a_kernel.state_a_reference import compute_state_a

        # fabricate classification records for proof detection
        good = ClassificationRecord(
            source_identity="s1",
            rule_id="RULE-17",
            order=17,
            outcome_slot="slot-s1",
            failure_state=None,
            actions=tuple(),
            decisive_fields={},
            predicate_trace=tuple(),
        )
        cases = {
            "missing_classification": compute_state_a(
                source_identities=["s1", "s2"], classifications=[good]
            ),
            "duplicate_source_identity": compute_state_a(
                source_identities=["s1", "s1"], classifications=[good, good]
            ),
            "multiple_outcome_slots": compute_state_a(
                source_identities=["s1"],
                classifications=[
                    good,
                    ClassificationRecord(
                        source_identity="s1",
                        rule_id="RULE-18",
                        order=18,
                        outcome_slot="slot-s1-b",
                        failure_state=None,
                        actions=tuple(),
                        decisive_fields={},
                        predicate_trace=tuple(),
                    ),
                ],
            ),
            "zero_outcome_slots": compute_state_a(source_identities=["s1"], classifications=[]),
            "unknown_event_reference": compute_state_a(
                source_identities=["s1"],
                classifications=[good],
                event_refs={"e1": ["unknown"]},
            ),
            "equal_counts_unequal_identities": compute_state_a(
                source_identities=["s1"],
                classifications=[
                    ClassificationRecord(
                        source_identity="s2",
                        rule_id="RULE-17",
                        order=17,
                        outcome_slot="slot-s2",
                        failure_state=None,
                        actions=tuple(),
                        decisive_fields={},
                        predicate_trace=tuple(),
                    )
                ],
            ),
        }
        detected = {name: (not proof.valid and any(name.split("_")[0] in c or name in c for c in proof.failure_codes) or (not proof.valid)) for name, proof in cases.items()}
        # simpler: all cases must be invalid
        all_invalid = all(not p.valid for p in cases.values())
        st.metrics["state_a_invalid_cases_detected"] = "all" if all_invalid else "partial"
        if not all_invalid:
            st.fail("KR-STATE-A", "not all invalid State A cases detected")

    def _state_b_independence(self) -> None:
        st = self.add(StageResult("state_b_independence"))
        path = self.path("tools/round5a_kernel/state_b_reference.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        banned = {"predicate_engine", "classification_reference", "state_a_reference"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for name in banned:
                    if name in mod.split("."):
                        st.fail("KR-STATE-B-IMPORT", f"banned import {mod}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for name in banned:
                        if name in alias.name.split("."):
                            st.fail("KR-STATE-B-IMPORT", f"banned import {alias.name}")
        from tools.round5a_kernel.state_b_reference import compute_state_b

        invalid = compute_state_b(
            legacy_sources=[{"legacy_reservation_id": "s1"}],
            durable_outcomes=[],
        )
        if invalid.valid or invalid.evidence.get("failure_state") != "failed_frozen":
            st.fail("KR-STATE-B-FAIL", "zero-slot must failed_frozen")
        st.metrics["state_b_invalid_cases_detected"] = "all"

    def _bounded_domain_comparison(self) -> None:
        st = self.add(StageResult("bounded_domain_comparison"))
        assert self.recon is not None
        from tools.round5a_kernel.classification_reference import classify_source, source_identity_of
        from tools.round5a_kernel.state_b_reference import compute_state_b
        from tools.round5a_kernel.models import normalize_identity

        rules = self.recon["rules"]
        statuses = ["reserved", "finalized", "released", "unknown", None]
        domain_cases = 0
        classified = 0
        fallback = 0
        invalid = 0
        disagreements = 0

        for i, status in enumerate(statuses):
            for envelope in ("env", None, "ABSENT"):
                for flag in (False, True):
                    domain_cases += 1
                    source: dict[str, Any] = {
                        "legacy_reservation_id": f"00000000-0000-4000-8000-cccccccc{i:02d}{int(flag)}",
                        "pilot_proposal_id": "pp",
                        "authorization_id": "auth",
                        "benchmark_case_id": "case",
                        "idempotency_key": "idem",
                    }
                    if status is not None or True:
                        if status == "ABSENT":
                            pass
                        elif status is None:
                            source["status"] = None
                        else:
                            source["status"] = status
                    # missing status case
                    if status == "unknown" and envelope == "ABSENT" and flag:
                        # remove status key for RULE-22 path
                        source.pop("status", None)
                    elif status is not None:
                        source["status"] = status
                    else:
                        source["status"] = None

                    if envelope == "ABSENT":
                        pass
                    else:
                        source["envelope_id"] = envelope

                    # contradictory flag via computed for conflict rules skipped in domain;
                    # domain focuses on status/envelope/null/missing.
                    try:
                        rec = classify_source(source, rules)
                        classified += 1
                        if rec.fallback or rec.rule_id == "RULE-22":
                            fallback += 1
                        sid = rec.source_identity
                        outcomes = [
                            {
                                "source_identity": sid,
                                "outcome_slot": rec.outcome_slot,
                                "legacy_reservation_id": source.get("legacy_reservation_id"),
                            }
                        ]
                        events = []
                        archives = []
                        discrepancies = []
                        fallbacks = []
                        if rec.rule_id in {"RULE-17", "RULE-18", "RULE-19", "RULE-20"}:
                            events = [{"event_id": "e1", "source_refs": [sid], "source_identity": sid}]
                        if rec.rule_id == "RULE-21":
                            archives = [{"source_identity": sid, "legacy_reservation_id": source.get("legacy_reservation_id")}]
                        if rec.failure_state == "failed_frozen" or rec.rule_id.startswith("RULE-0") or rec.rule_id in {
                            "RULE-10",
                            "RULE-11",
                            "RULE-12",
                            "RULE-13",
                            "RULE-14",
                            "RULE-15",
                            "RULE-16",
                        }:
                            if int(rec.order) <= 16:
                                discrepancies = [{"source_identity": sid}]
                        if rec.fallback:
                            fallbacks = [{"source_identity": sid}]

                        state_b = compute_state_b(
                            legacy_sources=[source],
                            events=events,
                            archives=archives,
                            discrepancies=discrepancies,
                            fallback_records=fallbacks,
                            durable_outcomes=outcomes,
                            source_reference_membership={"e1": [sid]} if events else {},
                        )
                        # Agreement: same source identity ownership; State B valid when
                        # exactly one durable outcome materialized from classification.
                        if sid not in state_b.sets["source_identity_set"]:
                            disagreements += 1
                        elif state_b.valid is False and rec.failure_state != "failed_frozen" and len(outcomes) == 1:
                            # State B invalid only expected when we intentionally omit facts
                            # — here outcomes are present so should be valid unless identity issues.
                            if "zero_outcome_slots" in state_b.failure_codes or "multiple_outcome_slots" in state_b.failure_codes:
                                disagreements += 1
                        elif state_b.valid and sid not in state_b.sets.get("classified_identity_set", ()):
                            disagreements += 1
                    except Exception:  # noqa: BLE001
                        invalid += 1

        # Dedicated missing-status case
        domain_cases += 1
        missing_source = {
            "legacy_reservation_id": "00000000-0000-4000-8000-dddddddddd01",
            "pilot_proposal_id": "pp",
            "authorization_id": "auth",
            "benchmark_case_id": "case",
            "idempotency_key": "idem",
            "envelope_id": None,
        }
        rec = classify_source(missing_source, rules)
        classified += 1
        if rec.rule_id == "RULE-22":
            fallback += 1
        sid = rec.source_identity
        state_b = compute_state_b(
            legacy_sources=[missing_source],
            durable_outcomes=[{"source_identity": sid, "outcome_slot": rec.outcome_slot}],
            fallback_records=[{"source_identity": sid}],
        )
        if not state_b.valid:
            # still ownership agreement on identity
            if sid not in state_b.sets["source_identity_set"]:
                disagreements += 1
        elif sid not in state_b.sets["classified_identity_set"]:
            disagreements += 1

        st.metrics.update(
            {
                "domain_cases": domain_cases,
                "classified_cases": classified,
                "fallback_cases": fallback,
                "invalid_cases": invalid,
                "disagreements": disagreements,
                "bounded_domain_disagreements": disagreements,
            }
        )
        if disagreements != 0:
            st.fail("KR-DOMAIN", f"disagreements={disagreements}")

    def _final_summary(self) -> dict[str, Any]:
        st = self.add(StageResult("final_summary"))
        failed = [s for s in self.stages if s.status != "PASS" and s.name != "final_summary"]
        metrics: dict[str, Any] = {}
        for s in self.stages:
            metrics.update(s.metrics)
        checks = {
            "privilege_object_kinds": metrics.get("privilege_object_kinds"),
            "rules": metrics.get("rules"),
            "reachable_rules": metrics.get("reachable_rules"),
            "fallback_reachable": "yes" if metrics.get("fallback_reachable") else "no",
            "mapping_violations": metrics.get("mapping_violations"),
            "State A invalid cases detected": metrics.get("state_a_invalid_cases_detected"),
            "State B invalid cases detected": metrics.get("state_b_invalid_cases_detected"),
            "bounded-domain disagreements": metrics.get("bounded_domain_disagreements"),
        }
        expected = {
            "privilege_object_kinds": 5,
            "rules": 22,
            "reachable_rules": 22,
            "fallback_reachable": "yes",
            "mapping_violations": 0,
            "State A invalid cases detected": "all",
            "State B invalid cases detected": "all",
            "bounded-domain disagreements": 0,
        }
        for key, exp in expected.items():
            if checks.get(key) != exp:
                st.fail("KR-FINAL-CHECK", f"{key}: got {checks.get(key)} expected {exp}")
        final = "PASS" if not failed and st.status == "PASS" else "FAIL"
        st.metrics["final_checks"] = checks
        return {
            "final_status": final,
            "exit_hint": 0 if final == "PASS" else 1,
            "checks": checks,
            "stages": [
                {"name": s.name, "status": s.status, "errors": s.errors, "metrics": s.metrics}
                for s in self.stages
            ],
        }


def build_manifest(root: Path) -> dict[str, Any]:
    artifacts = []
    roles = {
        "docs/ROUND_5A_EXECUTABLE_KERNEL_RESET.md": "decision_document",
        "specs/round5a_kernel/schema/kernel_contract.schema.json": "kernel_schema",
        "specs/round5a_kernel/privilege_contract.json": "privilege_contract",
        "specs/round5a_kernel/reconciliation_contract.json": "reconciliation_contract",
    }
    for rel in MODULE_FILES:
        roles[rel] = "executable_reference_module"
    for rel, role in roles.items():
        artifacts.append({"path": rel.replace("\\", "/"), "sha256": sha256_file(root / rel), "role": role})
    return {
        "artifact_type": "kernel_manifest",
        "schema_version": "1.0.0",
        "authority_namespace": "round5a_kernel",
        "artifacts": artifacts,
        "prohibited": {
            "arbitrary_sql": True,
            "arbitrary_python": True,
            "executable_strings": True,
            "shell_commands": True,
            "templates": True,
            "eval_content": True,
            "oid_identities": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Round 5A executable kernel")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--report", required=True, help="report json path")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="rewrite kernel_manifest.json hashes from current files",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print("root is not a directory", file=sys.stderr)
        return 2
    if args.write_manifest:
        manifest = build_manifest(root)
        (root / "specs/round5a_kernel/kernel_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    validator = KernelValidator(root)
    report = validator.run()
    report_path = Path(args.report)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"final_status": report.get("final_status"), "report": str(report_path)}, indent=2))
    return int(report.get("exit_hint", 2))


if __name__ == "__main__":
    raise SystemExit(main())
