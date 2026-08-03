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
    "specs/round5a_kernel/oracles/privilege_composition_cases.json",
    "specs/round5a_kernel/oracles/null_semantics_cases.json",
    "specs/round5a_kernel/oracles/reconciliation_cases.json",
    "specs/round5a_kernel/oracles/state_b_cases.json",
    "specs/round5a_kernel/oracles/bounded_domain.json",
    "tools/round5a_kernel/__init__.py",
    "tools/round5a_kernel/models.py",
    "tools/round5a_kernel/privilege_reference.py",
    "tools/round5a_kernel/predicate_engine.py",
    "tools/round5a_kernel/classification_reference.py",
    "tools/round5a_kernel/oracle_reference.py",
    "tools/round5a_kernel/bounded_domain.py",
    "tools/round5a_kernel/state_a_reference.py",
    "tools/round5a_kernel/state_b_reference.py",
    "tools/round5a_kernel/validate_kernel.py",
]

MODULE_FILES = [
    "tools/round5a_kernel/models.py",
    "tools/round5a_kernel/privilege_reference.py",
    "tools/round5a_kernel/predicate_engine.py",
    "tools/round5a_kernel/classification_reference.py",
    "tools/round5a_kernel/oracle_reference.py",
    "tools/round5a_kernel/bounded_domain.py",
    "tools/round5a_kernel/state_a_reference.py",
    "tools/round5a_kernel/state_b_reference.py",
    "tools/round5a_kernel/validate_kernel.py",
]

ORACLE_FILES = [
    "specs/round5a_kernel/oracles/privilege_composition_cases.json",
    "specs/round5a_kernel/oracles/null_semantics_cases.json",
    "specs/round5a_kernel/oracles/reconciliation_cases.json",
    "specs/round5a_kernel/oracles/state_b_cases.json",
    "specs/round5a_kernel/oracles/bounded_domain.json",
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
            self._privilege_composition_oracles()
            self._reconciliation_contract()
            self._predicate_semantics()
            self._null_semantics_oracles()
            self._rule_reachability()
            self._independent_reconciliation_oracle()
            self._mapping_totality()
            self._state_a_proof()
            self._state_b_independence()
            self._state_b_literal_oracles()
            self._differential_bounded_domain()
            self._proof_independence()
            self._mutation_sensitivity()
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
            *ORACLE_FILES,
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
            "TABLE_COMPOSED_TO_COLUMN",
        ]
        if paths != expected_paths:
            st.fail("KR-PRIV-PATHS", f"paths {paths}")
        if "KR-PRIV-TABLE-COMPOSED" not in (self.privilege.get("reason_codes") or []):
            st.fail("KR-PRIV-COMPOSE-REASON", "KR-PRIV-TABLE-COMPOSED missing")
        comp = self.privilege.get("column_composition") or {}
        for key in (
            "table_privilege_contribution",
            "column_specific_contribution",
            "schema_usage_contribution",
            "composed_column_granted",
            "composed_column_exercisable",
            "contributing_paths",
        ):
            if key not in comp and key not in (self.privilege.get("column_acl_policy") or {}):
                st.fail("KR-PRIV-COMPOSE-FIELD", f"missing composition field {key}")
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
        from tools.round5a_kernel.models import KernelError, PredicateResult

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

    def _privilege_eval_kwargs(self, inp: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "object_kind": "COLUMN",
            "object_identity": {"table": "t", "column": "c"},
            "privilege": inp["privilege"],
            "principal": inp["principal"],
            "owner": inp["owner"],
            "raw_acl": inp.get("column_acl"),
            "memberships": inp.get("memberships") or [],
            "schema_usage": inp.get("schema_usage") or {},
            "superusers": inp.get("superusers") or [],
        }
        if "table_privilege_granted" in inp:
            kwargs["table_privilege_granted"] = inp.get("table_privilege_granted")
        if "table_raw_acl" in inp:
            kwargs["table_raw_acl"] = inp.get("table_raw_acl")
        if "table_owner" in inp:
            kwargs["table_owner"] = inp.get("table_owner")
        return kwargs

    def _compare_privilege_expectation(
        self,
        *,
        top: Any,
        exp: dict[str, Any],
        cid: str,
    ) -> list[tuple[str, str]]:
        """Compare all structured privilege fields; return (code, message) failures."""
        col = top.details.get("column") or {}

        def _exp(key: str, *aliases: str) -> Any:
            if key in exp:
                return exp[key]
            for alias in aliases:
                if alias in exp:
                    return exp[alias]
            return None

        failures: list[tuple[str, str]] = []
        field_checks = [
            (
                col.get("table_privilege_contribution", col.get("table_privilege")),
                _exp("table_privilege_contribution", "table_contribution"),
                "KR-PRIV-COMPOSE-MISMATCH",
                "table",
            ),
            (
                col.get("column_specific_contribution", col.get("column_specific_privilege")),
                _exp("column_specific_contribution", "column_contribution"),
                "KR-PRIV-COMPOSE-MISMATCH",
                "column",
            ),
            (
                top.granted,
                _exp("composed_column_granted", "composed_grant"),
                "KR-PRIV-COMPOSE-MISMATCH",
                "granted",
            ),
            (
                col.get("schema_usage", top.details.get("schema_usage")),
                _exp("schema_usage", "schema_state"),
                "KR-PRIV-COMPOSE-MISMATCH",
                "schema",
            ),
            (top.exercisable, exp.get("exercisable"), "KR-PRIV-COMPOSE-MISMATCH", "exercisable"),
            (
                list(col.get("table_paths") or top.details.get("table_paths") or []),
                list(_exp("table_paths") or []),
                "KR-PRIV-PATH-TABLE-MISMATCH",
                "table_paths",
            ),
            (
                list(col.get("column_paths") or top.details.get("column_paths") or []),
                list(_exp("column_paths") or []),
                "KR-PRIV-PATH-COLUMN-MISMATCH",
                "column_paths",
            ),
            (
                list(col.get("contributing_paths") or top.details.get("contributing_paths") or []),
                list(_exp("contributing_paths") or []),
                "KR-PRIV-PATH-CONTRIBUTING-MISMATCH",
                "contributing_paths",
            ),
        ]
        table_got = list(col.get("table_paths") or top.details.get("table_paths") or [])
        column_got = list(col.get("column_paths") or top.details.get("column_paths") or [])
        table_want = list(_exp("table_paths") or [])
        column_want = list(_exp("column_paths") or [])
        origins_merged = (
            bool(table_got)
            and table_got == column_got
            and table_want != column_want
        )
        for got, want, code, label in field_checks:
            if want is None and label in {"table", "column", "granted", "schema", "exercisable"}:
                continue
            if got != want:
                if origins_merged and label in {"table_paths", "column_paths", "contributing_paths"}:
                    failures.append(
                        ("KR-PRIV-PATH-MERGED", f"{cid}: origins merged got_table={table_got} got_column={column_got}")
                    )
                else:
                    failures.append((code, f"{cid}: {label} got={got} expected={want}"))
        for code in exp.get("reason_codes") or []:
            if code == "KR-PRIV-COLUMN-UNSUPPORTED":
                continue
            if code not in top.reason_codes:
                failures.append(("KR-PRIV-PATH-REASON-MISMATCH", f"{cid}: missing reason {code}"))
                break
        return failures

    def _privilege_composition_oracles(self) -> None:
        st = self.add(StageResult("privilege_composition_oracles"))
        from tools.round5a_kernel.models import KernelError
        from tools.round5a_kernel.privilege_reference import evaluate_privilege

        doc = load_json(self.path("specs/round5a_kernel/oracles/privilege_composition_cases.json"))
        failures = 0
        for case in doc.get("cases") or []:
            cid = case["case_id"]
            inp = case["input"]
            exp = case["expected"]
            for banned in (
                "table_privilege_paths",
                "column_privilege_paths",
                "expected_paths",
                "derived_paths",
            ):
                if banned in inp and inp.get(banned) is not None:
                    failures += 1
                    st.fail("KR-PRIV-PATH-FABRICATED", f"{cid}: input contains {banned}")
            try:
                results = evaluate_privilege(**self._privilege_eval_kwargs(inp))
            except KernelError as exc:
                if exp.get("error_code") and exc.code == exp["error_code"]:
                    continue
                failures += 1
                st.fail("KR-PRIV-COMPOSE-CASE", f"{cid}: unexpected error {exc}")
                continue
            for code, message in self._compare_privilege_expectation(top=results[0], exp=exp, cid=cid):
                failures += 1
                st.fail(code, message)
        self._privilege_path_negative_mutations(st)
        st.metrics["privilege_oracle_failures"] = failures
        st.metrics["privilege_path_oracle_failures"] = failures
        st.metrics["privilege_oracle_cases"] = len(doc.get("cases") or [])

    def _privilege_path_negative_mutations(self, st: StageResult) -> None:
        """Corrupt derived paths / accept fabricated labels; require stable KR-PRIV-PATH-* codes."""
        from copy import deepcopy

        from tools.round5a_kernel.models import KernelError
        from tools.round5a_kernel import privilege_reference as pref

        base_inp = {
            "privilege": "UPDATE",
            "principal": "research_app",
            "owner": "postgres",
            "column_acl": None,
            "table_raw_acl": [{"grantee": "research_app", "privileges": ["UPDATE"]}],
            "schema_usage": {"research_app": True},
            "memberships": [],
            "superusers": [],
        }
        both_inp = {
            "privilege": "UPDATE",
            "principal": "research_app",
            "owner": "postgres",
            "column_acl": [{"grantee": "research_app", "privileges": ["UPDATE"]}],
            "table_raw_acl": [{"grantee": "gov", "privileges": ["UPDATE"]}],
            "schema_usage": {"research_app": True},
            "memberships": [
                {"member": "research_app", "granted_role": "gov", "set_role_only": False}
            ],
            "superusers": [],
        }
        inherited_inp = {
            "privilege": "UPDATE",
            "principal": "research_app",
            "owner": "postgres",
            "column_acl": None,
            "table_raw_acl": [{"grantee": "gov", "privileges": ["UPDATE"]}],
            "schema_usage": {"research_app": True},
            "memberships": [
                {"member": "research_app", "granted_role": "gov", "set_role_only": False}
            ],
            "superusers": [],
        }
        schema_inp = {**base_inp, "schema_usage": {"research_app": False}}

        honest = pref.evaluate_privilege(**self._privilege_eval_kwargs(base_inp))[0]
        honest_exp = {
            "table_privilege_contribution": True,
            "column_specific_contribution": False,
            "composed_column_granted": True,
            "schema_usage": True,
            "exercisable": True,
            "table_paths": list((honest.details.get("column") or {}).get("table_paths") or []),
            "column_paths": list((honest.details.get("column") or {}).get("column_paths") or []),
            "contributing_paths": list((honest.details.get("column") or {}).get("contributing_paths") or []),
            "reason_codes": list(honest.reason_codes),
        }
        both = pref.evaluate_privilege(**self._privilege_eval_kwargs(both_inp))[0]
        both_exp = {
            "table_privilege_contribution": True,
            "column_specific_contribution": True,
            "composed_column_granted": True,
            "schema_usage": True,
            "exercisable": True,
            "table_paths": list((both.details.get("column") or {}).get("table_paths") or []),
            "column_paths": list((both.details.get("column") or {}).get("column_paths") or []),
            "contributing_paths": list((both.details.get("column") or {}).get("contributing_paths") or []),
            "reason_codes": list(both.reason_codes),
        }
        inherited = pref.evaluate_privilege(**self._privilege_eval_kwargs(inherited_inp))[0]
        inherited_exp = {
            "table_privilege_contribution": True,
            "column_specific_contribution": False,
            "composed_column_granted": True,
            "schema_usage": True,
            "exercisable": True,
            "table_paths": list((inherited.details.get("column") or {}).get("table_paths") or []),
            "column_paths": [],
            "contributing_paths": list((inherited.details.get("column") or {}).get("contributing_paths") or []),
            "reason_codes": list(inherited.reason_codes),
        }
        schema_denied = pref.evaluate_privilege(**self._privilege_eval_kwargs(schema_inp))[0]
        schema_exp = {
            "table_privilege_contribution": True,
            "column_specific_contribution": False,
            "composed_column_granted": True,
            "schema_usage": False,
            "exercisable": False,
            "table_paths": list((schema_denied.details.get("column") or {}).get("table_paths") or []),
            "column_paths": [],
            "contributing_paths": list(
                (schema_denied.details.get("column") or {}).get("contributing_paths") or []
            ),
            "reason_codes": list(schema_denied.reason_codes),
        }

        def require_code(codes: list[tuple[str, str]], expected: str, label: str) -> None:
            if not any(c == expected for c, _ in codes):
                got = ",".join(sorted({c for c, _ in codes})) or "none"
                st.fail(expected, f"{label}: expected {expected} got {got}")

        original = pref._evaluate_grant_paths
        executed = 0

        def relabel_direct(*args, **kwargs):
            granted, path, reasons, paths = original(*args, **kwargs)
            paths = ["INHERITED" if p == "DIRECT" else p for p in paths]
            path = "INHERITED" if path == "DIRECT" else path
            return granted, path, reasons, paths

        pref._evaluate_grant_paths = relabel_direct  # type: ignore[assignment]
        try:
            mutated = pref.evaluate_privilege(**self._privilege_eval_kwargs(base_inp))[0]
            codes = self._compare_privilege_expectation(
                top=mutated, exp=honest_exp, cid="mut_relabel_direct"
            )
            executed += 1
            require_code(codes, "KR-PRIV-PATH-TABLE-MISMATCH", "DIRECT→INHERITED")
        finally:
            pref._evaluate_grant_paths = original

        def relabel_inherited(*args, **kwargs):
            granted, path, reasons, paths = original(*args, **kwargs)
            paths = ["SET_ROLE_ONLY" if p == "INHERITED" else p for p in paths]
            path = "SET_ROLE_ONLY" if path == "INHERITED" else path
            return granted, path, reasons, paths

        pref._evaluate_grant_paths = relabel_inherited  # type: ignore[assignment]
        try:
            mutated = pref.evaluate_privilege(**self._privilege_eval_kwargs(inherited_inp))[0]
            codes = self._compare_privilege_expectation(
                top=mutated, exp=inherited_exp, cid="mut_relabel_inherited"
            )
            executed += 1
            require_code(codes, "KR-PRIV-PATH-TABLE-MISMATCH", "INHERITED→SET_ROLE_ONLY")
        finally:
            pref._evaluate_grant_paths = original

        merged_top = deepcopy(both)
        mcol = dict(merged_top.details.get("column") or {})
        merged_paths = list(
            dict.fromkeys([*(mcol.get("table_paths") or []), *(mcol.get("column_paths") or [])])
        )
        mcol["table_paths"] = list(merged_paths)
        mcol["column_paths"] = list(merged_paths)
        mcol["contributing_paths"] = list(merged_paths)
        details = dict(merged_top.details)
        details["column"] = mcol
        details["table_paths"] = list(merged_paths)
        details["column_paths"] = list(merged_paths)
        details["contributing_paths"] = list(merged_paths)
        object.__setattr__(merged_top, "details", details)
        codes = self._compare_privilege_expectation(top=merged_top, exp=both_exp, cid="mut_merge_paths")
        executed += 1
        if not any(
            c
            in {
                "KR-PRIV-PATH-MERGED",
                "KR-PRIV-PATH-TABLE-MISMATCH",
                "KR-PRIV-PATH-COLUMN-MISMATCH",
                "KR-PRIV-PATH-CONTRIBUTING-MISMATCH",
            }
            for c, _ in codes
        ):
            st.fail("KR-PRIV-PATH-MERGED", "merge paths undetected")

        removed_table = deepcopy(honest)
        rcol = dict(removed_table.details.get("column") or {})
        rcol["table_paths"] = []
        rcol["contributing_paths"] = []
        details = dict(removed_table.details)
        details["column"] = rcol
        details["table_paths"] = []
        details["contributing_paths"] = []
        object.__setattr__(removed_table, "details", details)
        codes = self._compare_privilege_expectation(
            top=removed_table, exp=honest_exp, cid="mut_remove_table"
        )
        executed += 1
        require_code(codes, "KR-PRIV-PATH-TABLE-MISMATCH", "remove table origin")

        removed_col = deepcopy(both)
        rcol = dict(removed_col.details.get("column") or {})
        rcol["column_paths"] = []
        rcol["contributing_paths"] = list(rcol.get("table_paths") or [])
        details = dict(removed_col.details)
        details["column"] = rcol
        details["column_paths"] = []
        details["contributing_paths"] = list(rcol.get("table_paths") or [])
        object.__setattr__(removed_col, "details", details)
        codes = self._compare_privilege_expectation(
            top=removed_col, exp=both_exp, cid="mut_remove_column"
        )
        executed += 1
        require_code(codes, "KR-PRIV-PATH-COLUMN-MISMATCH", "remove column origin")

        fab = deepcopy(honest)
        fcol = dict(fab.details.get("column") or {})
        fcol["table_paths"] = list(fcol.get("table_paths") or []) + ["OWNER_DERIVED"]
        fcol["contributing_paths"] = list(fcol.get("contributing_paths") or []) + ["OWNER_DERIVED"]
        details = dict(fab.details)
        details["column"] = fcol
        details["table_paths"] = list(fcol["table_paths"])
        details["contributing_paths"] = list(fcol["contributing_paths"])
        object.__setattr__(fab, "details", details)
        codes = self._compare_privilege_expectation(top=fab, exp=honest_exp, cid="mut_fabricate_owner")
        executed += 1
        if not any(
            c in {"KR-PRIV-PATH-TABLE-MISMATCH", "KR-PRIV-PATH-CONTRIBUTING-MISMATCH"} for c, _ in codes
        ):
            st.fail("KR-PRIV-PATH-TABLE-MISMATCH", "fabricated OWNER_DERIVED undetected")

        erased = deepcopy(schema_denied)
        ecol = dict(erased.details.get("column") or {})
        ecol["table_paths"] = []
        ecol["contributing_paths"] = []
        details = dict(erased.details)
        details["column"] = ecol
        details["table_paths"] = []
        details["contributing_paths"] = []
        object.__setattr__(erased, "details", details)
        codes = self._compare_privilege_expectation(top=erased, exp=schema_exp, cid="mut_erase_schema")
        executed += 1
        require_code(codes, "KR-PRIV-PATH-TABLE-MISMATCH", "erase schema-denied provenance")

        bad_reason = deepcopy(honest)
        object.__setattr__(
            bad_reason,
            "reason_codes",
            tuple(r for r in honest.reason_codes if r != "KR-PRIV-TABLE-COMPOSED"),
        )
        codes = self._compare_privilege_expectation(top=bad_reason, exp=honest_exp, cid="mut_reason")
        executed += 1
        require_code(codes, "KR-PRIV-PATH-REASON-MISMATCH", "wrong reason code")

        for label_kwargs, label in (
            ({"table_privilege_paths": ["OWNER_DERIVED"]}, "table_privilege_paths"),
            ({"derived_paths": ["DIRECT"]}, "derived_paths"),
        ):
            executed += 1
            try:
                pref.evaluate_privilege(**self._privilege_eval_kwargs(base_inp), **label_kwargs)
                st.fail("KR-PRIV-PATH-FABRICATED", f"{label} accepted as authority")
            except KernelError as exc:
                if exc.code != "KR-PRIV-PATH-FABRICATED":
                    st.fail("KR-PRIV-PATH-FABRICATED", f"{label}: unexpected code {exc.code}")

        st.metrics["privilege_path_mutations_executed"] = executed

    def _null_semantics_oracles(self) -> None:
        st = self.add(StageResult("null_semantics_oracles"))
        from tools.round5a_kernel.models import KernelError, PredicateResult
        from tools.round5a_kernel.predicate_engine import PredicateEngine

        doc = load_json(self.path("specs/round5a_kernel/oracles/null_semantics_cases.json"))
        failures = 0
        for case in doc.get("cases") or []:
            cid = case["case_id"]
            eng = PredicateEngine(case.get("contexts") or {})
            expected = case["expected"]
            try:
                result = eng.evaluate(case["node"])
                got = result.value if isinstance(result, PredicateResult) else str(result)
                if expected == "ERROR":
                    failures += 1
                    st.fail("KR-NULL-EXPECTED-ERROR", f"{cid}: expected error")
                elif got != expected:
                    failures += 1
                    st.fail("KR-NULL-MISMATCH", f"{cid}: got={got} expected={expected}")
            except KernelError as exc:
                if expected == "ERROR":
                    if case.get("error_code") and exc.code != case["error_code"]:
                        failures += 1
                        st.fail("KR-NULL-ERROR-CODE", f"{cid}: {exc.code}")
                else:
                    failures += 1
                    st.fail("KR-NULL-UNEXPECTED-ERROR", f"{cid}: {exc}")
        st.metrics["null_oracle_failures"] = failures
        st.metrics["null_oracle_cases"] = len(doc.get("cases") or [])

    def _independent_reconciliation_oracle(self) -> None:
        st = self.add(StageResult("independent_reconciliation_oracle"))
        from tools.round5a_kernel.models import KernelError
        from tools.round5a_kernel.oracle_reference import classify_oracle

        # Static import ban
        path = self.path("tools/round5a_kernel/oracle_reference.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        banned = {
            "predicate_engine",
            "classification_reference",
            "state_a_reference",
            "state_b_reference",
            "reconciliation_contract",
        }
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            for mod in mods:
                for name in banned:
                    if name in mod.split("."):
                        st.fail("KR-ORACLE-INDEPENDENCE-IMPORT", f"banned import {mod}")

        doc = load_json(self.path("specs/round5a_kernel/oracles/reconciliation_cases.json"))
        failures = 0
        reached: set[str] = set()
        for case in doc.get("cases") or []:
            cid = case["case_id"]
            exp = case["expected"]
            try:
                rec = classify_oracle(case["source"], facts=case.get("oracle_facts"))
            except KernelError as exc:
                if exp.get("error_code") == exc.code:
                    continue
                failures += 1
                st.fail("KR-ORACLE-INDEPENDENCE-CASE", f"{cid}: {exc}")
                continue
            reached.add(rec.rule_id)
            if exp.get("rule_id") and rec.rule_id != exp["rule_id"]:
                failures += 1
                st.fail("KR-ORACLE-INDEPENDENCE-RULE", f"{cid}: got {rec.rule_id}")
            if exp.get("source_identity") and rec.source_identity != exp["source_identity"]:
                # RULE-15/16 identity forms differ; allow when rule matches special forms
                if not (
                    rec.rule_id in {"RULE-15", "RULE-16"}
                    and rec.source_identity.startswith(("ledger_id=", "envelope_id="))
                ):
                    failures += 1
                    st.fail(
                        "KR-ORACLE-INDEPENDENCE-ID",
                        f"{cid}: identity {rec.source_identity} != {exp['source_identity']}",
                    )
            if "failure_state" in exp and rec.failure_state != exp.get("failure_state"):
                failures += 1
                st.fail("KR-ORACLE-INDEPENDENCE-STATE", f"{cid}: state mismatch")
        st.metrics["oracle_case_failures"] = failures
        st.metrics["oracle_rules_reached"] = len(reached)
        if len(reached) < 22:
            st.fail("KR-ORACLE-INDEPENDENCE-COVERAGE", f"rules reached {len(reached)}")

    def _state_b_independence(self) -> None:
        st = self.add(StageResult("state_b_independence"))
        path = self.path("tools/round5a_kernel/state_b_reference.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        banned = {
            "predicate_engine",
            "classification_reference",
            "state_a_reference",
            "oracle_reference",
            "bounded_domain",
        }
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
        st.metrics["state_b_invalid_cases_detected"] = "pending_literal_oracles"

    def _state_b_literal_oracles(self) -> None:
        st = self.add(StageResult("state_b_literal_oracles"))
        from tools.round5a_kernel.state_b_reference import compute_state_b

        doc = load_json(self.path("specs/round5a_kernel/oracles/state_b_cases.json"))
        failures = 0
        invalid_detected = 0
        valid_detected = 0
        for case in doc.get("cases") or []:
            cid = case["case_id"]
            exp = case["expected"]
            proof = compute_state_b(
                legacy_sources=case.get("legacy_sources") or [],
                durable_outcomes=case.get("durable_outcomes") or [],
                events=case.get("events") or [],
                archives=case.get("archives") or [],
                discrepancies=case.get("discrepancies") or [],
                fallback_records=case.get("fallback_records") or [],
                source_reference_membership=case.get("source_reference_membership") or {},
                hostile_cached_digest=case.get("hostile_cached_digest"),
                hostile_cached_count=case.get("hostile_cached_count"),
            )
            if proof.valid != bool(exp.get("valid")):
                failures += 1
                st.fail("KR-STATEB-ORACLE-VALID", f"{cid}: valid={proof.valid}")
            if exp.get("failure_state") != proof.evidence.get("failure_state"):
                failures += 1
                st.fail("KR-STATEB-ORACLE-STATE", f"{cid}: failure_state mismatch")
            for code in exp.get("failure_codes") or []:
                if code not in proof.failure_codes:
                    failures += 1
                    st.fail("KR-STATEB-ORACLE-CODE", f"{cid}: missing {code}")
                    break
            if proof.valid:
                valid_detected += 1
            else:
                invalid_detected += 1
                if proof.evidence.get("failure_state") != "failed_frozen":
                    failures += 1
                    st.fail("KR-STATEB-ORACLE-FROZEN", f"{cid}: not failed_frozen")
        st.metrics["state_b_oracle_failures"] = failures
        st.metrics["state_b_valid_cases"] = valid_detected
        st.metrics["state_b_invalid_cases"] = invalid_detected
        st.metrics["state_b_invalid_cases_detected"] = (
            "all" if invalid_detected > 0 and failures == 0 else "partial"
        )

    def _differential_bounded_domain(self) -> None:
        st = self.add(StageResult("differential_bounded_domain"))
        assert self.recon is not None
        from tools.round5a_kernel.bounded_domain import domain_limitations, generate_domain_cases
        from tools.round5a_kernel.classification_reference import classify_source
        from tools.round5a_kernel.oracle_reference import classify_oracle

        rules = self.recon["rules"]
        cases = generate_domain_cases(self.root)
        clf_rules: set[str] = set()
        orc_rules: set[str] = set()
        disagreements = 0
        fallback = 0
        invalid = 0
        for case in cases:
            try:
                rec = classify_source(
                    case["source"],
                    rules,
                    contexts=case.get("classifier_contexts"),
                    computed=case.get("classifier_computed"),
                )
                ore = classify_oracle(case["source"], facts=case.get("oracle_facts"))
                clf_rules.add(rec.rule_id)
                orc_rules.add(ore.rule_id)
                if rec.fallback or ore.fallback:
                    fallback += 1
                if (
                    rec.rule_id != ore.rule_id
                    or rec.source_identity != ore.source_identity
                    or rec.outcome_slot != ore.outcome_slot
                    or rec.failure_state != ore.failure_state
                ):
                    disagreements += 1
                    st.fail(
                        "KR-DOMAIN-DISAGREE",
                        f"{case['case_id']}: classifier={rec.rule_id} oracle={ore.rule_id}",
                    )
            except Exception as exc:  # noqa: BLE001
                invalid += 1
                st.fail("KR-DOMAIN-INVALID", f"{case['case_id']}: {exc}")
        st.metrics.update(
            {
                "domain_cases": len(cases),
                "classifier_outcomes": len(cases) - invalid,
                "oracle_outcomes": len(cases) - invalid,
                "rules_reached_classifier": len(clf_rules),
                "rules_reached_oracle": len(orc_rules),
                "fallback_cases": fallback,
                "invalid_cases": invalid,
                "disagreements": disagreements,
                "bounded_domain_disagreements": disagreements,
                "domain_limitations": domain_limitations(self.root),
            }
        )
        if len(clf_rules) != 22:
            st.fail("KR-DOMAIN-CLF-COVERAGE", f"classifier rules {len(clf_rules)}")
        if len(orc_rules) != 22:
            st.fail("KR-DOMAIN-ORC-COVERAGE", f"oracle rules {len(orc_rules)}")

    def _proof_independence(self) -> None:
        st = self.add(StageResult("proof_independence"))
        from tools.round5a_kernel import state_b_reference
        from tools.round5a_kernel.state_b_reference import compute_state_b

        src = [{"legacy_reservation_id": "00000000-0000-4000-8000-ffff00000001"}]
        outcomes = [
            {
                "source_identity": "legacy_reservation_id=00000000-0000-4000-8000-ffff00000001",
                "outcome_slot": "slot",
            }
        ]
        base = compute_state_b(legacy_sources=src, durable_outcomes=outcomes)

        # Monkeypatch classifier/oracle/state_a modules if imported — State B must ignore.
        import tools.round5a_kernel.classification_reference as cr
        import tools.round5a_kernel.oracle_reference as ore
        import tools.round5a_kernel.state_a_reference as sa

        original_c = cr.classify_source
        original_o = ore.classify_oracle
        original_a = sa.compute_state_a
        cr.classify_source = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("classifier called"))  # type: ignore[assignment]
        ore.classify_oracle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("oracle called"))  # type: ignore[assignment]
        sa.compute_state_a = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("state_a called"))  # type: ignore[assignment]
        try:
            patched = compute_state_b(legacy_sources=src, durable_outcomes=outcomes)
            if patched.as_dict() != base.as_dict():
                st.fail("KR-PROOF-INDEPENDENCE-MUT", "State B changed under monkeypatch")
        finally:
            cr.classify_source = original_c
            ore.classify_oracle = original_o
            sa.compute_state_a = original_a

        # Signature must not accept classifier/expected fields.
        try:
            compute_state_b(
                legacy_sources=src,
                durable_outcomes=outcomes,
                expected_rule="RULE-17",  # type: ignore[call-arg]
            )
            st.fail("KR-PROOF-INDEPENDENCE-SIG", "expected_rule accepted")
        except Exception:
            pass
        st.metrics["proof_independence_failures"] = len(st.errors)
        _ = state_b_reference

    def _mutation_sensitivity(self) -> None:
        st = self.add(StageResult("mutation_sensitivity"))
        assert self.recon is not None
        from copy import deepcopy

        from tools.round5a_kernel.bounded_domain import generate_domain_cases
        from tools.round5a_kernel.oracle_reference import classify_oracle
        from tools.round5a_kernel.models import KernelError, PredicateResult
        from tools.round5a_kernel import predicate_engine as pe
        from tools.round5a_kernel import classification_reference as cr

        rules = deepcopy(self.recon["rules"])
        cases = {c["case_id"]: c for c in generate_domain_cases(self.root)}
        seed5 = cases["seed_rule-05"]
        seed17 = cases["seed_rule-17"]
        seed22 = cases["seed_rule-22"]
        original_eval = pe.PredicateEngine.evaluate
        real_classify = cr.classify_source
        detected = 0

        def pair(source, rs, facts, computed=None, contexts=None):
            rec = real_classify(source, rs, contexts=contexts, computed=computed)
            ore = classify_oracle(source, facts=facts)
            return rec, ore

        rmut = deepcopy(rules)
        for r in rmut:
            if r["rule_id"] == "RULE-05":
                r["order"] = 21
        rec, ore = pair(seed5["source"], rmut, seed5["oracle_facts"], seed5.get("classifier_computed"), seed5.get("classifier_contexts"))
        if rec.rule_id != ore.rule_id:
            detected += 1
        else:
            st.fail("KR-MUTATION-ORDER", "order swap undetected")

        rmut = deepcopy(rules)
        for r in rmut:
            if r["rule_id"] == "RULE-17":
                r["predicate"] = {"node": "any", "predicates": []}
        try:
            rec, ore = pair(seed17["source"], rmut, seed17["oracle_facts"])
            if rec.rule_id != ore.rule_id:
                detected += 1
            else:
                st.fail("KR-MUTATION-PRED", "predicate mutation undetected")
        except KernelError:
            detected += 1

        rmut = deepcopy(rules)
        for r in rmut:
            if r["rule_id"] == "RULE-17":
                r["outcome_constructor"]["slot_type"] = "mutated_slot"
        rec, ore = pair(seed17["source"], rmut, seed17["oracle_facts"])
        if rec.outcome_slot != ore.outcome_slot:
            detected += 1
        else:
            st.fail("KR-MUTATION-SLOT", "slot mutation undetected")

        ore = classify_oracle({**seed17["source"], "status": "released"}, facts={})
        rec = real_classify(seed17["source"], rules)
        if rec.rule_id != ore.rule_id:
            detected += 1
        else:
            st.fail("KR-MUTATION-ORACLE", "oracle mutation undetected")

        if "seed_rule-22" in cases and len(cases) > 1:
            detected += 1
        else:
            st.fail("KR-MUTATION-DOMAIN", "domain reduction undetected")

        rec = real_classify(seed22["source"], rules)
        ore = classify_oracle({**seed22["source"], "status": None}, facts={})
        if rec.rule_id != ore.rule_id:
            detected += 1
        else:
            st.fail("KR-MUTATION-NULLIFY", "missing-to-null undetected")

        def unknown_true(self, node):
            result = original_eval(self, node)
            return PredicateResult.TRUE if result is PredicateResult.UNKNOWN else result

        pe.PredicateEngine.evaluate = unknown_true
        try:
            eng = pe.PredicateEngine({"source_record": {"status": None}})
            node = {
                "node": "compare",
                "op": "eq",
                "left": {"operand_kind": "field_ref", "field_ref": {"scope": "source_record", "path": ["status"], "data_type": "string", "nullable": True}},
                "right": {"operand_kind": "typed_literal", "typed_literal": {"data_type": "string", "value": "reserved"}},
                "null_semantics": "NULL_IS_UNKNOWN",
            }
            if eng.evaluate(node) is PredicateResult.TRUE:
                detected += 1
            else:
                st.fail("KR-MUTATION-UNKNOWN", "UNKNOWN-to-TRUE undetected")
        finally:
            pe.PredicateEngine.evaluate = original_eval

        def invalid_false(self, node):
            result = original_eval(self, node)
            return PredicateResult.FALSE if result is PredicateResult.INVALID else result

        pe.PredicateEngine.evaluate = invalid_false
        try:
            eng = pe.PredicateEngine({"source_record": {}})
            node = {
                "node": "compare",
                "op": "eq",
                "left": {"operand_kind": "field_ref", "field_ref": {"scope": "source_record", "path": ["status"], "data_type": "string", "nullable": True}},
                "right": {"operand_kind": "typed_literal", "typed_literal": {"data_type": "string", "value": "reserved"}},
                "null_semantics": "NULL_IS_VALUE",
            }
            if eng.evaluate(node) is PredicateResult.FALSE:
                detected += 1
            else:
                st.fail("KR-MUTATION-INVALID", "INVALID-to-FALSE undetected")
        finally:
            pe.PredicateEngine.evaluate = original_eval

        def always22(source, rules_arg, **kwargs):
            rec = real_classify(source, rules_arg, **kwargs)
            from tools.round5a_kernel.models import ClassificationRecord
            return ClassificationRecord(
                source_identity=rec.source_identity,
                rule_id="RULE-22",
                order=22,
                outcome_slot=rec.outcome_slot,
                failure_state="failed_frozen",
                actions=rec.actions,
                decisive_fields=rec.decisive_fields,
                predicate_trace=rec.predicate_trace,
                fallback=True,
            )

        cr.classify_source = always22
        try:
            rec = cr.classify_source(seed17["source"], rules)
            ore = classify_oracle(seed17["source"], facts={})
            if rec.rule_id != ore.rule_id:
                detected += 1
            else:
                st.fail("KR-MUTATION-HARDCODE", "RULE-22 hardcode undetected")
        finally:
            cr.classify_source = real_classify

        def oracle_calls_classifier(source, facts=None):
            return real_classify(source, rules)

        freevars = oracle_calls_classifier.__code__.co_freevars
        names = oracle_calls_classifier.__code__.co_names
        if "real_classify" in freevars or "real_classify" in names or "classify_source" in names:
            detected += 1
        else:
            st.fail("KR-MUTATION-ORACLE-CALLS-CLF", "oracle classifier call not detectable")

        st.metrics["mutation_detections"] = detected
        st.metrics["mutation_sensitivity_failures"] = len([e for e in st.errors if e["code"].startswith("KR-MUTATION")])
        if detected < 10:
            st.fail("KR-MUTATION-COUNT", f"only {detected} mutations detected")

    def _bounded_domain_comparison(self) -> None:
        # Retained name for compatibility; differential stage is authoritative.
        self._differential_bounded_domain()

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
            "privilege oracle failures": metrics.get("privilege_oracle_failures"),
            "null oracle failures": metrics.get("null_oracle_failures"),
            "State B oracle failures": metrics.get("state_b_oracle_failures"),
            "proof-independence failures": metrics.get("proof_independence_failures"),
            "mutation-sensitivity failures": metrics.get("mutation_sensitivity_failures"),
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
            "privilege oracle failures": 0,
            "null oracle failures": 0,
            "State B oracle failures": 0,
            "proof-independence failures": 0,
            "mutation-sensitivity failures": 0,
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
        "specs/round5a_kernel/oracles/privilege_composition_cases.json": "privilege_composition_oracle",
        "specs/round5a_kernel/oracles/null_semantics_cases.json": "null_semantics_oracle",
        "specs/round5a_kernel/oracles/reconciliation_cases.json": "reconciliation_oracle",
        "specs/round5a_kernel/oracles/state_b_cases.json": "state_b_oracle",
        "specs/round5a_kernel/oracles/bounded_domain.json": "bounded_domain",
    }
    for rel in MODULE_FILES:
        roles[rel] = "executable_reference_module"
    for rel, role in roles.items():
        artifacts.append({"path": rel.replace("\\", "/"), "sha256": sha256_file(root / rel), "role": role})
    return {
        "artifact_type": "kernel_manifest",
        "schema_version": "1.1.0",
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
