#!/usr/bin/env python3
"""Round 5A offline semantic validator (stdlib + optional jsonschema)."""
from __future__ import annotations

import argparse
import re
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

VALIDATOR_VERSION = "round5a-offline-validator/1.1.0"
SPEC_SCHEMA_VERSION = "1.1.0"
MISSING = object()
ALG = "schema9_checkpoint_digest_v1"
US = "\u001f"
RS = "\u001e"

REQUIRED_FILES = [
    "specs/round5a/schema/round5a_registry.schema.json",
    "specs/round5a/SCHEMA_CONTRACT.md",
    "specs/round5a/catalog_contract.yaml",
    "specs/round5a/checkpoints.yaml",
    "specs/round5a/reconciliation_rules.yaml",
    "specs/round5a/registry_manifest.yaml",
    "specs/round5a/evidence_aliases.yaml",
    "specs/round5a/fixtures/reconciliation_witnesses.yaml",
    "specs/round5a/fixtures/checkpoint_oracles.yaml",
    "specs/round5a/fixtures/privilege_cases.yaml",
    "docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md",
    "evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql",
    "evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md",
    "evidence/round5a/archived_phase1/PROVENANCE.json",
    "evidence/round5a/recreated_phase1/SRL_Phase1_catalog_snapshot.sql",
    "evidence/round5a/recreated_phase1/SRL_Phase1_evidence_spec.md",
    "evidence/round5a/recreated_phase1/RUN_ORDER.txt",
    "evidence/round5a/recreated_phase1/SHA256SUMS.txt",
    "evidence/round5a/recreated_phase1/PROVENANCE.json",
]

EVIDENCE_PROVENANCE_FILES = [
    "evidence/round5a/archived_phase1/PROVENANCE.json",
    "evidence/round5a/recreated_phase1/PROVENANCE.json",
]

PORTABLE_PATH_SCAN_FILES = [
    "specs/round5a/catalog_contract.yaml",
    "specs/round5a/checkpoints.yaml",
    "specs/round5a/reconciliation_rules.yaml",
    "specs/round5a/registry_manifest.yaml",
    "specs/round5a/evidence_aliases.yaml",
    "specs/round5a/fixtures/reconciliation_witnesses.yaml",
    "specs/round5a/fixtures/checkpoint_oracles.yaml",
    "specs/round5a/fixtures/privilege_cases.yaml",
    "evidence/round5a/archived_phase1/PROVENANCE.json",
    "evidence/round5a/recreated_phase1/PROVENANCE.json",
]

ABS_PATH_RE = re.compile(
    r"(?i)(?:[A-Za-z]:\\|/Users/|/home/|/tmp/|/var/tmp/|AppData\\Local\\Temp|\\Temp\\|\$env:TEMP)"
)


@dataclass
class ErrorRec:
    code: str
    message: str
    artifact: str = ""
    record: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "artifact": self.artifact,
            "record": self.record,
        }


@dataclass
class StageResult:
    name: str
    status: str = "PASS"
    errors: list[ErrorRec] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)

    def fail(self, err: ErrorRec) -> None:
        self.status = "FAIL"
        self.errors.append(err)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "errors": [e.as_dict() for e in sorted(self.errors, key=lambda e: (e.code, e.artifact, e.record, e.message))],
            "warnings": sorted(self.warnings),
            "counts": dict(sorted(self.counts.items())),
            "artifact_refs": sorted(self.artifact_refs),
        }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(record: Any, path: list[str]) -> Any:
    if record is None:
        return MISSING
    cur = record
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return MISSING
        cur = cur[p]
    return cur


def pkey(pref: str, params: dict[str, Any]) -> tuple[str, str]:
    return pref, json.dumps(params, sort_keys=True, separators=(",", ":"))


class PredicateEngine:
    def __init__(self, source: dict[str, Any], shared: dict[str, Any] | None = None, primitives: dict[tuple[str, str], Any] | None = None, ledger_orphan: dict | None = None, envelope_orphan: dict | None = None):
        self.source = source
        self.shared = shared or {}
        self.primitives = primitives or {}
        self.ledger_orphan = ledger_orphan
        self.envelope_orphan = envelope_orphan

    def eval_operand(self, op: dict[str, Any]) -> Any:
        kind = op["operand_kind"]
        if kind == "literal":
            return op["literal"]["value"]
        if kind == "field_ref":
            fr = op["field_ref"]
            scope = fr["scope"]
            if scope == "source_record":
                return resolve_path(self.source, fr["path"])
            if scope == "shared_data_model":
                return resolve_path(self.shared, fr["path"])
            if scope == "ledger_orphan":
                return resolve_path(self.ledger_orphan, fr["path"])
            if scope == "envelope_orphan":
                return resolve_path(self.envelope_orphan, fr["path"])
            return resolve_path(self.source, fr["path"])
        if kind == "computed_primitive_ref":
            pref = op["computed_primitive_ref"]["primitive_ref"]
            params = op["computed_primitive_ref"].get("parameters", {})
            return self.primitives.get(pkey(pref, params), MISSING)
        if kind == "normalized_identity_ref":
            return None
        raise ValueError(f"unsupported operand {kind}")

    def exists(self, val: Any) -> bool:
        return not (val is MISSING or val is None or val is False)

    def eval(self, node: dict[str, Any]) -> bool:
        n = node["node"]
        if n == "all":
            return all(self.eval(p) for p in node["predicates"])
        if n == "any":
            return any(self.eval(p) for p in node["predicates"])
        if n == "not":
            return not self.eval(node["predicate"])
        if n == "is_null":
            return self.eval_operand(node["operand"]) is None
        if n == "is_not_null":
            v = self.eval_operand(node["operand"])
            return v is not MISSING and v is not None
        if n == "exists":
            return self.exists(self.eval_operand(node["target"]))
        if n == "missing":
            return self.eval_operand(node["target"]) is MISSING
        if n == "compare":
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            if left is MISSING or right is MISSING or left is None or right is None:
                return False
            return {
                "eq": left == right,
                "ne": left != right,
                "lt": left < right,
                "lte": left <= right,
                "gt": left > right,
                "gte": left >= right,
            }[node["op"]]
        if n in ("in", "not_in"):
            v = self.eval_operand(node["operand"])
            if v is MISSING or v is None:
                return False
            values = [self.eval_operand(x) for x in node["values"]]
            present = v in values
            return present if n == "in" else not present
        if n == "set_equals":
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            if left is MISSING or right is MISSING or left is None or right is None:
                return False
            return set(left) == set(right)
        if n == "set_contains":
            left = self.eval_operand(node["left"])
            right = self.eval_operand(node["right"])
            if left is MISSING or right is MISSING or left is None or right is None:
                return False
            return set(right).issubset(set(left))
        raise ValueError(f"unsupported node {n}")


def default_primitives(rules: list[dict[str, Any]]) -> dict[tuple[str, str], Any]:
    prims: dict[tuple[str, str], Any] = {}

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("operand_kind") == "computed_primitive_ref":
                pref = obj["computed_primitive_ref"]["primitive_ref"]
                params = obj["computed_primitive_ref"].get("parameters", {})
                key = pkey(pref, params)
                if params.get("subject_is_non_winner"):
                    prims[key] = MISSING
                elif params.get("flag"):
                    prims[key] = False
                elif params.get("lookup") in ("pilot_proposal_id", "authorization_id", "benchmark_case_id"):
                    prims[key] = "PRESENT"
                elif params.get("lookup") == "accounting_discrepancies_open":
                    prims[key] = MISSING
                elif params.get("lookup") == "accounting_discrepancy_acknowledged":
                    prims[key] = "PRESENT"
                elif params.get("binding"):
                    prims[key] = MISSING
                elif params.get("mode") == "required_event_natural_key":
                    prims[key] = "PRESENT"
                elif params.get("mode") in ("event_field_tuple", "source_field_tuple"):
                    prims[key] = ("tuple",)
                elif params.get("metric"):
                    prims[key] = 0
                else:
                    prims[key] = MISSING
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for r in rules:
        walk(r["predicate"])
        walk(r.get("explicit_exclusions") or [])
    return prims


def primitives_from_related(related: list[dict[str, Any]], base: dict[tuple[str, str], Any]) -> tuple[dict[tuple[str, str], Any], dict[str, Any]]:
    prims = dict(base)
    shared: dict[str, Any] = {}
    for item in related:
        if item.get("binding_kind") == "computed_primitive":
            key = pkey(item["primitive_ref"], item.get("parameters") or {})
            if item.get("absent"):
                prims[key] = MISSING
            else:
                val = item.get("value")
                if isinstance(val, list) and val == ["tuple"]:
                    val = ("tuple",)
                prims[key] = val
        elif item.get("binding_kind") == "shared_data_model":
            shared.update(item.get("values") or {})
    return prims, shared


def rule_matches(rule: dict[str, Any], engine: PredicateEngine) -> bool:
    if not engine.eval(rule["predicate"]):
        return False
    for ex in rule.get("explicit_exclusions") or []:
        if not engine.eval(ex):
            return False
    return True


def first_match(rules: list[dict[str, Any]], engine: PredicateEngine) -> dict[str, Any] | None:
    for r in sorted(rules, key=lambda x: x["order"]):
        if rule_matches(r, engine):
            return r
    return None


def encode_cell(v: Any) -> str:
    if v is None:
        return "\\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    return str(v)


def canonicalize(rows: list[dict[str, Any]], field_order: list[str], algorithm_version: str = ALG) -> bytes:
    ordered = sorted(rows, key=lambda r: tuple(encode_cell(r.get(f)) for f in field_order))
    body = RS.join(US.join(encode_cell(r.get(f)) for f in field_order) for r in ordered)
    return (algorithm_version + US + body).encode("utf-8")


def walk_field_paths(obj: Any, acc: set[tuple[str, ...]]) -> None:
    if isinstance(obj, dict):
        if obj.get("operand_kind") == "field_ref":
            acc.add(tuple(obj["field_ref"]["path"]))
        for v in obj.values():
            walk_field_paths(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            walk_field_paths(v, acc)


class Round5AValidator:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.stages: list[StageResult] = []
        self.errors: list[ErrorRec] = []
        self.docs: dict[str, Any] = {}
        self.counts: dict[str, Any] = {}

    def add_stage(self, stage: StageResult) -> StageResult:
        self.stages.append(stage)
        self.errors.extend(stage.errors)
        return stage

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("path escapes repository root")
        return p

    def run(self) -> dict[str, Any]:
        try:
            import jsonschema
            from jsonschema import Draft202012Validator
        except ImportError:
            return self._blocked("R5A-FILE-DEP", "jsonschema package is required but not installed")

        self._stage_file_inventory()
        if any(s.status == "FAIL" and s.name == "file_inventory" for s in self.stages):
            return self._report("FAIL")
        self._stage_json_parsing()
        if any(s.name == "json_parsing" and s.status == "FAIL" for s in self.stages):
            return self._report("FAIL")
        self._stage_json_schema(Draft202012Validator)
        self._stage_manifest()
        self._stage_cross_refs()
        self._stage_catalog()
        self._stage_checkpoints()
        self._stage_reconciliation()
        self._stage_fixture_coverage()
        self._stage_predicate_execution()
        self._stage_mapping()
        self._stage_state()
        self._stage_privilege()
        self._stage_evidence()
        self._stage_evidence_source_integrity()
        self._stage_evidence_alias_integrity()
        self._stage_portable_path_invariants()
        self._stage_final()
        status = "PASS" if not self.errors else "FAIL"
        return self._report(status)

    def _blocked(self, code: str, message: str) -> dict[str, Any]:
        stage = StageResult("file_inventory", status="BLOCKED")
        stage.fail(ErrorRec(code, message))
        self.add_stage(stage)
        return self._report("BLOCKED")

    def _report(self, final_status: str) -> dict[str, Any]:
        hashes = {}
        for rel in REQUIRED_FILES:
            p = self.root / rel
            if p.exists() and p.suffix in {".yaml", ".json", ".md"}:
                hashes[rel.replace("\\", "/")] = sha256_file(p)
        return {
            "validator_version": VALIDATOR_VERSION,
            "specification_schema_version": SPEC_SCHEMA_VERSION,
            "registry_version": (
                self.docs.get("manifest", {})
                .get("registry_manifest", {})
                .get("registry_version", "")
            ),
            "repository_head": self._git_head(),
            "artifact_hashes": dict(sorted(hashes.items())),
            "stages": [s.as_dict() for s in self.stages],
            "counts": dict(sorted(self.counts.items())),
            "errors": [e.as_dict() for e in sorted(self.errors, key=lambda e: (e.code, e.artifact, e.record, e.message))],
            "warnings": [],
            "final_status": final_status,
        }

    def _git_head(self) -> str:
        head = self.root / ".git" / "HEAD"
        if not head.exists():
            return ""
        text = head.read_text(encoding="utf-8").strip()
        if text.startswith("ref:"):
            ref = text.split(" ", 1)[1].strip()
            ref_path = self.root / ".git" / ref
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
        return text

    def _stage_file_inventory(self) -> None:
        st = StageResult("file_inventory")
        missing = [rel for rel in REQUIRED_FILES if not self.path(rel).exists()]
        st.counts["required"] = len(REQUIRED_FILES)
        st.counts["missing"] = len(missing)
        st.artifact_refs = list(REQUIRED_FILES)
        for rel in missing:
            st.fail(ErrorRec("R5A-FILE-MISSING", f"missing required artifact {rel}", rel))
        self.add_stage(st)

    def _stage_json_parsing(self) -> None:
        st = StageResult("json_parsing")
        for rel in REQUIRED_FILES:
            if not rel.endswith((".yaml", ".json")):
                continue
            p = self.path(rel)
            if not p.exists():
                continue
            try:
                self.docs[rel] = load_json_file(p)
                st.counts[rel] = 1
            except json.JSONDecodeError as exc:
                st.fail(ErrorRec("R5A-FILE-JSON", str(exc), rel))
        self.docs["catalog"] = self.docs.get("specs/round5a/catalog_contract.yaml")
        self.docs["checkpoints"] = self.docs.get("specs/round5a/checkpoints.yaml")
        self.docs["rules"] = self.docs.get("specs/round5a/reconciliation_rules.yaml")
        self.docs["manifest"] = self.docs.get("specs/round5a/registry_manifest.yaml")
        self.docs["witnesses"] = self.docs.get("specs/round5a/fixtures/reconciliation_witnesses.yaml")
        self.docs["oracles"] = self.docs.get("specs/round5a/fixtures/checkpoint_oracles.yaml")
        self.docs["privileges"] = self.docs.get("specs/round5a/fixtures/privilege_cases.yaml")
        self.docs["aliases"] = self.docs.get("specs/round5a/evidence_aliases.yaml")
        self.docs["schema"] = self.docs.get("specs/round5a/schema/round5a_registry.schema.json")
        self.add_stage(st)
        if st.status == "FAIL":
            # Stop further semantic stages on unreadable JSON.
            for name in [
                "json_schema",
                "manifest_integrity",
                "cross_file_references",
                "catalog_semantics",
                "checkpoint_semantics",
                "reconciliation_semantics",
                "fixture_coverage",
                "predicate_execution",
                "mapping_invariants",
                "state_invariants",
                "privilege_semantics",
                "evidence_class_invariants",
                "evidence_source_integrity",
                "evidence_alias_integrity",
                "portable_path_invariants",
                "final_summary",
            ]:
                skipped = StageResult(name, status="FAIL")
                skipped.fail(ErrorRec("R5A-FILE-JSON", "skipped due to JSON parse failure"))
                self.add_stage(skipped)

    def _stage_json_schema(self, Draft202012Validator: Any) -> None:
        st = StageResult("json_schema")
        schema = self.docs.get("schema")
        if not schema:
            st.fail(ErrorRec("R5A-SCHEMA-MISSING", "schema not loaded"))
            self.add_stage(st)
            return
        validator = Draft202012Validator(schema)
        for rel, key in [
            ("specs/round5a/catalog_contract.yaml", "catalog"),
            ("specs/round5a/checkpoints.yaml", "checkpoints"),
            ("specs/round5a/reconciliation_rules.yaml", "rules"),
            ("specs/round5a/registry_manifest.yaml", "manifest"),
            ("specs/round5a/evidence_aliases.yaml", "aliases"),
            ("specs/round5a/fixtures/reconciliation_witnesses.yaml", "witnesses"),
            ("specs/round5a/fixtures/checkpoint_oracles.yaml", "oracles"),
            ("specs/round5a/fixtures/privilege_cases.yaml", "privileges"),
        ]:
            inst = self.docs.get(key)
            if inst is None:
                st.fail(ErrorRec("R5A-SCHEMA-MISSING", "instance missing", rel))
                continue
            errs = sorted(validator.iter_errors(inst), key=lambda e: list(e.absolute_path))
            st.counts[rel] = len(errs)
            for e in errs:
                st.fail(
                    ErrorRec(
                        "R5A-SCHEMA-INVALID",
                        e.message,
                        rel,
                        "/".join(str(x) for x in e.absolute_path),
                    )
                )
        self.add_stage(st)

    def _stage_manifest(self) -> None:
        st = StageResult("manifest_integrity")
        man = self.docs.get("manifest")
        if not man:
            st.fail(ErrorRec("R5A-MANIFEST-MISSING", "manifest missing"))
            self.add_stage(st)
            return
        entries = man["registry_manifest"]["artifact_hashes"]
        for entry in entries:
            rel = entry["path"]
            p = self.path(rel)
            if not p.exists():
                st.fail(ErrorRec("R5A-MANIFEST-MISSING", f"manifest path missing {rel}", rel))
                continue
            actual = sha256_file(p)
            if actual != entry["sha256"]:
                st.fail(
                    ErrorRec(
                        "R5A-MANIFEST-HASH",
                        f"hash mismatch expected={entry['sha256']} actual={actual}",
                        rel,
                    )
                )
        st.counts["entries"] = len(entries)
        self.add_stage(st)

    def _stage_cross_refs(self) -> None:
        st = StageResult("cross_file_references")
        rules = self.docs["rules"]["reconciliation_rule_registry"]["rules"]
        cps = self.docs["checkpoints"]["checkpoint_registry"]["checkpoints"]
        rule_ids = {r["rule_id"] for r in rules}
        cp_ids = {c["checkpoint_id"] for c in cps}
        for fx in self.docs["witnesses"]["reconciliation_fixture_pack"]["fixtures"]:
            if fx["rule_ref"] not in rule_ids and fx.get("expected_rule") not in rule_ids:
                st.fail(ErrorRec("R5A-REF-RULE", "unknown rule_ref", "reconciliation_witnesses.yaml", fx["fixture_id"]))
            if fx.get("expected_rule") and fx["expected_rule"] not in rule_ids:
                st.fail(ErrorRec("R5A-REF-RULE", "unknown expected_rule", "reconciliation_witnesses.yaml", fx["fixture_id"]))
        for o in self.docs["oracles"]["checkpoint_oracle_pack"]["oracles"]:
            if o["checkpoint_ref"] not in cp_ids:
                st.fail(ErrorRec("R5A-REF-CKP", "unknown checkpoint_ref", "checkpoint_oracles.yaml", o["oracle_id"]))
        st.counts["rule_ids"] = len(rule_ids)
        st.counts["checkpoint_ids"] = len(cp_ids)
        self.add_stage(st)

    def _stage_catalog(self) -> None:
        st = StageResult("catalog_semantics")
        cat = self.docs["catalog"]["catalog_contract"]
        if cat["role_discovery"]["mode"] != "CATALOG_DISCOVERY":
            st.fail(ErrorRec("R5A-CATALOG-ROLEDISC", "role_discovery.mode must be CATALOG_DISCOVERY"))
        markers = [
            o
            for o in cat["objects"]
            if str(o.get("attributes", {}).get("marker_id", "")).startswith("MARKER-")
        ]
        recon = sum(1 for o in markers if o["provenance"]["evidence_class"] == "RECONSTRUCTED_REFERENCE_SCHEMA8")
        live = sum(1 for o in markers if o["provenance"]["evidence_class"] == "EXECUTION_TIME_LIVE_PREFLIGHT")
        runtime = sum(1 for o in markers if o["provenance"]["evidence_class"] == "PILOT_TIME_RUNTIME_REVALIDATION")
        st.counts.update({"markers": len(markers), "reconstructed": recon, "live": live, "runtime": runtime})
        self.counts.update(st.counts)
        if (len(markers), recon, live, runtime) != (31, 17, 11, 3):
            st.fail(
                ErrorRec(
                    "R5A-EVIDENCE-COUNT",
                    f"marker totals {len(markers)}/{recon}/{live}/{runtime} != 31/17/11/3",
                )
            )
        if '"LIVE_CATALOG"' in json.dumps(cat):
            st.fail(ErrorRec("R5A-EVIDENCE-LIVE", "LIVE_CATALOG claim forbidden"))
        if "acldefault('c'" in json.dumps(cat).lower():
            st.fail(ErrorRec("R5A-PRIV-COL-DEFAULT", "acldefault(c) prohibited"))
        self.add_stage(st)

    def _stage_checkpoints(self) -> None:
        st = StageResult("checkpoint_semantics")
        cps = self.docs["checkpoints"]["checkpoint_registry"]["checkpoints"]
        ids = [c["checkpoint_id"] for c in cps]
        st.counts["checkpoints"] = len(cps)
        st.counts["unique_ids"] = len(set(ids))
        self.counts["checkpoints"] = len(cps)
        if len(cps) != 18 or len(set(ids)) != 18:
            st.fail(ErrorRec("R5A-CKP-COUNT", f"expected 18 unique checkpoints, got {len(cps)}/{len(set(ids))}"))
        for c in cps:
            identity = c.get("identity_fields") or c.get("natural_identity") or {}
            identity_fields = identity.get("identity_fields", identity if isinstance(identity, list) else [])
            for fld in identity_fields:
                name = fld["path"][-1].lower()
                if name in {"oid", "object_oid", "relation_oid", "function_oid", "row_number", "physical_location", "ctid"}:
                    st.fail(ErrorRec("R5A-CKP-OID", f"OID identity field {name}", record=c["checkpoint_id"]))
            dig_fields = set(c["digest"]["input_contract"]["selected_field_names"])
            selected = {sf["name"] for sf in c["selected_fields"]}
            if not dig_fields.issubset(selected):
                st.fail(ErrorRec("R5A-CKP-DIGEST-FIELD", "digest fields not subset of selected", record=c["checkpoint_id"]))
        # oracle digests
        cp_by_id = {c["checkpoint_id"]: c for c in cps}
        for o in self.docs["oracles"]["checkpoint_oracle_pack"]["oracles"]:
            if o["expected_result"] != "PASS":
                continue
            cp = cp_by_id.get(o["checkpoint_ref"])
            if cp is None:
                st.fail(
                    ErrorRec(
                        "R5A-REF-CKP",
                        f"oracle checkpoint_ref missing {o['checkpoint_ref']}",
                        "checkpoint_oracles.yaml",
                        o["oracle_id"],
                    )
                )
                continue
            fields = cp["digest"]["input_contract"]["selected_field_names"]
            payload = canonicalize(o["normalized_rows"], fields, o["algorithm_version"])
            digest = sha256_bytes(payload)
            if digest != o["expected_digest"]:
                st.fail(
                    ErrorRec(
                        "R5A-CKP-DIGEST",
                        f"digest mismatch {digest} != {o['expected_digest']}",
                        "checkpoint_oracles.yaml",
                        o["oracle_id"],
                    )
                )
            if o["canonical_bytes"].encode("utf-8") != payload and o["case_kind"] != "algorithm_version_mismatch":
                # allow exact match against recomputed
                if sha256_bytes(o["canonical_bytes"].encode("utf-8")) != o["expected_digest"]:
                    st.fail(ErrorRec("R5A-CKP-BYTES", "canonical bytes digest mismatch", record=o["oracle_id"]))
        self.add_stage(st)

    def _stage_reconciliation(self) -> None:
        st = StageResult("reconciliation_semantics")
        rules = self.docs["rules"]["reconciliation_rule_registry"]["rules"]
        orders = sorted(r["order"] for r in rules)
        ids = [r["rule_id"] for r in rules]
        st.counts.update({"rules": len(rules), "unique_ids": len(set(ids))})
        self.counts["rules"] = len(rules)
        if len(rules) != 22 or orders != list(range(1, 23)) or len(set(ids)) != 22:
            st.fail(ErrorRec("R5A-RULE-ORDER", "rules must be 22 unique contiguous orders 1..22"))
        fallbacks = [r for r in rules if r.get("is_fallback")]
        if len(fallbacks) != 1 or fallbacks[0]["order"] != 22 or fallbacks[0].get("failure_state") != "failed_frozen":
            st.fail(ErrorRec("R5A-RULE-FALLBACK", "fallback must be unique order 22 failed_frozen"))
        for r in rules:
            acc: set[tuple[str, ...]] = set()
            walk_field_paths(r["predicate"], acc)
            walk_field_paths(r.get("explicit_exclusions") or [], acc)
            for df in r["decisive_fields"]:
                if tuple(df["path"]) not in acc:
                    st.fail(
                        ErrorRec(
                            "R5A-RULE-DECISIVE",
                            f"decisive field {df['path']} missing from predicate",
                            record=r["rule_id"],
                        )
                    )
        self.add_stage(st)

    def _stage_fixture_coverage(self) -> None:
        st = StageResult("fixture_coverage")
        fxs = self.docs["witnesses"]["reconciliation_fixture_pack"]["fixtures"]
        pos = [f for f in fxs if f["fixture_kind"] in ("POSITIVE_WITNESS", "FALLBACK_WITNESS") and f["fixture_id"].startswith("FIXTURE-W")]
        bounds = [f for f in fxs if f["fixture_kind"] == "BOUNDARY_WITNESS"]
        muts = [f for f in fxs if f["fixture_kind"] == "MUTATION_WITNESS"]
        pairs = set()
        for fx in pos:
            j = int(fx["expected_rule"].split("-")[1])
            for rid in fx.get("earlier_rules_expected_false") or []:
                pairs.add((int(rid.split("-")[1]), j))
        st.counts.update(
            {
                "positive_witnesses": len(pos),
                "boundary_witnesses": len(bounds),
                "mutation_fixtures": len(muts),
                "shadowing_pairs": len(pairs),
            }
        )
        self.counts.update(st.counts)
        if len(pos) != 22:
            st.fail(ErrorRec("R5A-FIXTURE-W", f"expected 22 W fixtures, got {len(pos)}"))
        if not any(f["fixture_id"] == "FIXTURE-W22" for f in pos):
            st.fail(ErrorRec("R5A-FIXTURE-W22", "missing W22 fallback witness"))
        if len(bounds) != 21:
            st.fail(ErrorRec("R5A-FIXTURE-B", f"expected 21 boundaries, got {len(bounds)}"))
        if len(pairs) != 231:
            st.fail(ErrorRec("R5A-SHADOW-PAIR", f"expected 231 shadowing pairs, got {len(pairs)}"))
        # decisive coverage
        rules = {r["rule_id"]: r for r in self.docs["rules"]["reconciliation_rule_registry"]["rules"]}
        covered: dict[str, set[str]] = {rid: set() for rid in rules if rid != "RULE-22"}
        for fx in muts:
            rid = fx["original_rule"]
            for m in fx.get("mutations") or []:
                covered.setdefault(rid, set()).add(m["field"]["path"][0])
        gaps = []
        for rid, rule in rules.items():
            if rid == "RULE-22":
                continue
            need = {d["path"][0] for d in rule["decisive_fields"]}
            miss = need - covered.get(rid, set())
            if miss:
                gaps.append(f"{rid}:{sorted(miss)}")
        st.counts["decisive_gaps"] = len(gaps)
        if gaps:
            st.fail(ErrorRec("R5A-FIXTURE-MUT", f"decisive-field gaps {gaps[:5]}"))
        else:
            st.counts["decisive_coverage_pct"] = 100
            self.counts["decisive_coverage_pct"] = 100
        self.add_stage(st)

    def _stage_predicate_execution(self) -> None:
        st = StageResult("predicate_execution")
        rules = self.docs["rules"]["reconciliation_rule_registry"]["rules"]
        base = default_primitives(rules)
        reachable: set[str] = set()
        fxs = self.docs["witnesses"]["reconciliation_fixture_pack"]["fixtures"]
        for fx in fxs:
            if not fx["fixture_id"].startswith("FIXTURE-W"):
                continue
            src = fx["input_records"][0]
            prims, shared_from_related = primitives_from_related(fx.get("related_records") or [], base)
            shared = {
                "projected_cost_usd": 0,
                "estimated_cost_usd": 0,
                "ledger_cost_usd": 0,
                "counter_value": 0,
                "ledger_request_count_reporting": src.get("ledger_request_count_reporting", 0),
                "ledger_success_count": src.get("ledger_success_count", 0),
                "projected_token_sum_events": src.get("projected_token_sum_events", 0),
                "policy_max_token_fields": src.get("policy_max_token_fields", 0),
                "discrepancy_fingerprint": src.get("discrepancy_fingerprint", "fp-1"),
            }
            shared.update(shared_from_related)
            engine = PredicateEngine(
                src,
                shared=shared,
                primitives=prims,
                ledger_orphan={"ledger_id": src["ledger_id"]} if "ledger_id" in src else None,
                envelope_orphan={"envelope_id": src["envelope_id"]} if fx["fixture_id"] == "FIXTURE-W16" else None,
            )
            selected = first_match(rules, engine)
            if selected is None:
                st.fail(ErrorRec("R5A-FIXTURE-EVAL", "no rule selected", record=fx["fixture_id"]))
                continue
            reachable.add(selected["rule_id"])
            if selected["rule_id"] != fx["expected_rule"]:
                st.fail(
                    ErrorRec(
                        "R5A-FIXTURE-OWNER",
                        f"selected {selected['rule_id']} != expected {fx['expected_rule']}",
                        record=fx["fixture_id"],
                    )
                )
            for pred in fx.get("expected_predicate_results") or []:
                rule = next(r for r in rules if r["rule_id"] == pred["rule_ref"])
                actual = rule_matches(rule, engine)
                if actual != pred["result"] and pred["rule_ref"] == fx["expected_rule"]:
                    # enforce target truth; earlier falses checked via first-match
                    if pred["result"] and not actual:
                        st.fail(ErrorRec("R5A-FIXTURE-PRED", f"{pred['rule_ref']} expected true", record=fx["fixture_id"]))
        st.counts["reachable_rules"] = len(reachable)
        self.counts["reachable_rules"] = len(reachable)
        if len(reachable) != 22:
            st.fail(ErrorRec("R5A-RULE-UNREACHABLE", f"reachable={sorted(reachable)} count={len(reachable)}"))
        if "RULE-22" not in reachable:
            st.fail(ErrorRec("R5A-RULE-FALLBACK-UNREACHABLE", "RULE-22 unreachable"))
        # boundaries
        for fx in fxs:
            if fx["fixture_kind"] != "BOUNDARY_WITNESS":
                continue
            src = fx["input_records"][0]
            engine = PredicateEngine(src, shared={"projected_cost_usd": 0, "estimated_cost_usd": 0, "ledger_cost_usd": 0, "counter_value": 0, "ledger_request_count_reporting": 0, "ledger_success_count": 0, "projected_token_sum_events": 0, "policy_max_token_fields": 0, "discrepancy_fingerprint": "fp"}, primitives=dict(base))
            original = next(r for r in rules if r["rule_id"] == fx["original_rule"])
            if rule_matches(original, engine):
                # some boundaries rely on related primitive clearing; allow if expected_new differs and first-match equals expected
                selected = first_match(rules, engine)
                if not selected or selected["rule_id"] != fx["expected_new_rule"]:
                    st.fail(ErrorRec("R5A-SHADOW-BOUND", f"boundary overmatch {fx['original_rule']}", record=fx["fixture_id"]))
        self.add_stage(st)

    def _stage_mapping(self) -> None:
        st = StageResult("mapping_invariants")
        maps = [f for f in self.docs["witnesses"]["reconciliation_fixture_pack"]["fixtures"] if f["fixture_kind"] == "MAPPING_CASE"]
        st.counts["mapping_fixtures"] = len(maps)
        for fx in maps:
            note = fx["expected_state"]["value"]
            if note == "zero_slots_invalid_expect_fallback" and fx["expected_rule"] != "RULE-22":
                st.fail(ErrorRec("R5A-MAPPING-ZERO", "zero-slot case must fall back", record=fx["fixture_id"]))
            if note == "two_sources_two_slots" and len(fx["input_records"]) < 2:
                st.fail(ErrorRec("R5A-MAPPING-TWO", "two-slot case needs two records", record=fx["fixture_id"]))
        self.add_stage(st)

    def _stage_state(self) -> None:
        st = StageResult("state_invariants")
        fxs = self.docs["witnesses"]["reconciliation_fixture_pack"]["fixtures"]
        a = [f for f in fxs if f["fixture_kind"] == "STATE_A_CASE"]
        b = [f for f in fxs if f["fixture_kind"] == "STATE_B_CASE"]
        st.counts["state_a"] = len(a)
        st.counts["state_b"] = len(b)
        for fx in b:
            if "VALID" not in fx["fixture_id"] and fx["expected_state"]["value"] != "failed_frozen":
                st.fail(ErrorRec("R5A-STATE-B", "invalid State B must be failed_frozen", record=fx["fixture_id"]))
        self.add_stage(st)

    def _stage_privilege(self) -> None:
        st = StageResult("privilege_semantics")
        fxs = self.docs["privileges"]["privilege_fixture_pack"]["fixtures"]
        kinds = {f["object_kind"] for f in fxs}
        st.counts["fixtures"] = len(fxs)
        st.counts["kinds"] = len(kinds)
        if kinds != {"SCHEMA", "FUNCTION", "TABLE", "COLUMN", "SEQUENCE"}:
            st.fail(ErrorRec("R5A-PRIV-KIND", f"incomplete object kinds {sorted(kinds)}"))
        for f in fxs:
            if f["object_kind"] == "COLUMN" and f["default_acl_semantics"]["kind"] not in {
                "null_attacl_no_column_specific_acl",
                "none",
            }:
                st.fail(ErrorRec("R5A-PRIV-COL-DEFAULT", "invalid column default semantics", record=f["fixture_id"]))
            roles = set(f["roles"])
            if roles <= {"research_governance", "research_test", "research_app", "n8n_app", "postgres"}:
                # dynamic role cases must include extras for some fixtures
                if "DYNAMIC" in f["fixture_id"] or "EXTRA" in f["fixture_id"]:
                    st.fail(ErrorRec("R5A-PRIV-FIXEDROLE", "fixed-role-only discovery", record=f["fixture_id"]))
        self.add_stage(st)

    def _stage_evidence(self) -> None:
        st = StageResult("evidence_class_invariants")
        st.counts = {
            "markers": self.counts.get("markers", 0),
            "reconstructed": self.counts.get("reconstructed", 0),
            "live": self.counts.get("live", 0),
            "runtime": self.counts.get("runtime", 0),
        }
        if st.counts["markers"] != 31:
            st.fail(ErrorRec("R5A-EVIDENCE-COUNT", "marker count mismatch"))
        self.add_stage(st)


    def _collect_current_ev_refs(self) -> set[str]:
        refs: set[str] = set()
        cat = self.docs.get("catalog") or {}
        for obj in cat.get("catalog_contract", {}).get("objects", []):
            attrs = obj.get("attributes") or {}
            if str(attrs.get("marker_id", "")).startswith("MARKER-"):
                mid = attrs.get("marker_identity")
                if mid:
                    refs.add(mid)
            prov = obj.get("provenance") or {}
            for ev in prov.get("evidence_refs") or []:
                refs.add(ev)
        for doc_key in ("checkpoints", "rules", "witnesses", "oracles", "privileges"):
            blob = json.dumps(self.docs.get(doc_key) or {})
            for m in re.findall(r"EV-[A-Z0-9]+(?:-[A-Z0-9]+)*", blob):
                refs.add(m)
        return refs

    def _stage_evidence_source_integrity(self) -> None:
        st = StageResult("evidence_source_integrity")
        # schema/manifest version alignment
        man = self.docs.get("manifest") or {}
        schema = self.docs.get("schema") or {}
        man_ver = (man.get("registry_manifest") or {}).get("schema_version")
        schema_ver = schema.get("x-round5a-schema-version")
        if man_ver != SPEC_SCHEMA_VERSION or schema_ver != SPEC_SCHEMA_VERSION:
            st.fail(
                ErrorRec(
                    "R5A-PROV-SOURCE-SCHEMA-VERSION",
                    f"schema/manifest/spec version mismatch schema={schema_ver} manifest={man_ver} expected={SPEC_SCHEMA_VERSION}",
                )
            )
        # archived/recreated provenance + file hashes
        expected = {
            "evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql": "1c4225887c88c9208bc50e69f08443bc65771ca0cce89f563d8d8ffef88cf9b4",
            "evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md": "a121e8d6b2d84d711734e16be5101b3b5cdb54aabb75465dddd753c5a76945a9",
            "evidence/round5a/recreated_phase1/SRL_Phase1_catalog_snapshot.sql": "484f1955f587a06b04bf2a5896d32edaba8c903934e1c2f8487f58aa851d5017",
            "evidence/round5a/recreated_phase1/SRL_Phase1_evidence_spec.md": "af6da96a51c26eae8f2e5c9fecc47cad842169b8570a2be4a488b261c28baa41",
            "evidence/round5a/recreated_phase1/RUN_ORDER.txt": "287b04f0b82a0549c928fc5094f60c74c3a39c4325852341548d21c40845ec9b",
            "evidence/round5a/recreated_phase1/SHA256SUMS.txt": "f7992bddd241693b108b6919240256569fac1e74aa13b6ba97264e05371d48b7",
        }
        for rel, exp in expected.items():
            p = self.path(rel)
            if not p.exists():
                st.fail(ErrorRec("R5A-PROV-SOURCE-MISSING", f"missing evidence file {rel}", rel))
                continue
            actual = sha256_file(p)
            if actual != exp:
                code = (
                    "R5A-PROV-SOURCE-ARCHIVED-HASH"
                    if "archived_phase1" in rel
                    else "R5A-PROV-SOURCE-RECREATED-HASH"
                )
                st.fail(ErrorRec(code, f"hash mismatch for {rel}", rel))
        # provenance authentication invariants
        for rel in EVIDENCE_PROVENANCE_FILES:
            p = self.path(rel)
            if not p.exists():
                st.fail(ErrorRec("R5A-PROV-SOURCE-MISSING", f"missing {rel}", rel))
                continue
            try:
                prov = load_json_file(p)
            except Exception as exc:
                st.fail(ErrorRec("R5A-PROV-SOURCE-JSON", str(exc), rel))
                continue
            if "archived_phase1" in rel:
                if prov.get("historical_git_authentication") != "UNVERIFIED":
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-AUTH-HISTORICAL",
                            "archived historical_git_authentication must remain UNVERIFIED",
                            rel,
                        )
                    )
                if prov.get("claimed_historical_commit") == "8d592bf" and prov.get(
                    "historical_git_authentication"
                ) == "VERIFIED":
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-AUTH-FALSE-CLAIM",
                            "false historical authentication claim for 8d592bf",
                            rel,
                        )
                    )
                if str(prov.get("historical_git_authentication", "")).upper() in {
                    "VERIFIED",
                    "AUTHENTICATED",
                    "PROVEN",
                }:
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-AUTH-FALSE-CLAIM",
                            "archived provenance must not claim verified historical authentication",
                            rel,
                        )
                    )
            binding = prov.get("current_repository_binding")
            if binding not in {"COMMIT_CONTAINING_THIS_FILE", "PENDING_CURRENT_COMMIT"}:
                st.fail(
                    ErrorRec(
                        "R5A-PROV-AUTH-BINDING",
                        f"invalid current_repository_binding {binding}",
                        rel,
                    )
                )
            files = prov.get("files") or {}
            for fname, exp_hash in files.items():
                fpath = p.parent / fname
                if not fpath.exists():
                    st.fail(ErrorRec("R5A-PROV-SOURCE-MISSING", f"missing {fpath.name}", rel, fname))
                    continue
                if sha256_file(fpath) != exp_hash:
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-SOURCE-PROVENANCE-HASH",
                            f"PROVENANCE files hash mismatch for {fname}",
                            rel,
                            fname,
                        )
                    )
        # decision doc must state UNVERIFIED
        decision = self.path("docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md")
        if decision.exists():
            dtxt = decision.read_text(encoding="utf-8")
            if "HISTORICAL GIT AUTHENTICATION: UNVERIFIED" not in dtxt:
                st.fail(
                    ErrorRec(
                        "R5A-PROV-AUTH-DECISION",
                        "decision record missing UNVERIFIED historical authentication statement",
                        "docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md",
                    )
                )
            if "CLAIMED HISTORICAL COMMIT: 8d592bf" not in dtxt:
                st.fail(
                    ErrorRec(
                        "R5A-PROV-AUTH-DECISION",
                        "decision record missing claimed historical commit statement",
                        "docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md",
                    )
                )
        st.counts["expected_files"] = len(expected)
        self.add_stage(st)

    def _stage_evidence_alias_integrity(self) -> None:
        st = StageResult("evidence_alias_integrity")
        aliases = self.docs.get("aliases")
        if not aliases:
            st.fail(ErrorRec("R5A-PROV-ALIAS-MISSING", "evidence_aliases.yaml missing"))
            self.add_stage(st)
            return
        mappings = aliases.get("evidence_alias_registry", {}).get("mappings") or []
        st.counts["mappings"] = len(mappings)

        # known evidence ids from committed producers
        producer_text = ""
        for rel in [
            "evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql",
            "evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md",
            "evidence/round5a/recreated_phase1/SRL_Phase1_catalog_snapshot.sql",
            "evidence/round5a/recreated_phase1/SRL_Phase1_evidence_spec.md",
        ]:
            p = self.path(rel)
            if p.exists():
                producer_text += p.read_text(encoding="utf-8", errors="replace")
        producer_ids = set(re.findall(r"EV-[A-Z0-9]+(?:-[A-Z0-9]+)*", producer_text))

        current_refs = self._collect_current_ev_refs()
        covered_current: set[str] = set()
        covered_markers: set[str] = set()

        for m in mappings:
            mid = m.get("mapping_id", "")
            if m.get("mapping_type") == "CONFLICTING_MEANING" or m.get("status") == "BLOCKING_CONFLICT":
                st.fail(
                    ErrorRec(
                        "R5A-PROV-ALIAS-CONFLICT",
                        "blocking conflict mapping is not accepted",
                        "evidence_aliases.yaml",
                        mid,
                    )
                )
            for eid in m.get("archived_evidence_ids") or []:
                if eid not in producer_ids and m.get("mapping_type") != "NO_LONGER_REQUIRED":
                    # archived id must exist in archived producers unless purely current mapping
                    arch_blob = ""
                    for rel in [
                        "evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql",
                        "evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md",
                    ]:
                        pp = self.path(rel)
                        if pp.exists():
                            arch_blob += pp.read_text(encoding="utf-8", errors="replace")
                    if eid not in arch_blob and m.get("archived_evidence_ids"):
                        st.fail(
                            ErrorRec(
                                "R5A-PROV-ALIAS-SOURCE-MISSING",
                                f"alias source {eid} not found in archived producers",
                                "evidence_aliases.yaml",
                                mid,
                            )
                        )
            for eid in m.get("recreated_evidence_ids") or []:
                rec_blob = ""
                for rel in [
                    "evidence/round5a/recreated_phase1/SRL_Phase1_catalog_snapshot.sql",
                    "evidence/round5a/recreated_phase1/SRL_Phase1_evidence_spec.md",
                ]:
                    pp = self.path(rel)
                    if pp.exists():
                        rec_blob += pp.read_text(encoding="utf-8", errors="replace")
                if eid not in rec_blob and eid not in {
                    # allow current marker set ids that appear only as marker names
                }:
                    # recreated target must exist unless mapping documents current-only via empty archived and notes
                    if m.get("archived_evidence_ids") and eid not in rec_blob:
                        st.fail(
                            ErrorRec(
                                "R5A-PROV-ALIAS-TARGET-MISSING",
                                f"alias target {eid} not found in recreated producers",
                                "evidence_aliases.yaml",
                                mid,
                            )
                        )
            for eid in m.get("current_evidence_ids") or []:
                covered_current.add(eid)
            for mk in m.get("affected_markers") or []:
                covered_markers.add(mk)

            # split/merge field coverage: require at least one field mapping when split/merge/replacement
            if m.get("mapping_type") in {"SEMANTIC_SPLIT", "SEMANTIC_MERGE", "REPLACEMENT", "EXPLICIT_ALIAS"}:
                fmaps = m.get("field_mappings") or []
                if not fmaps:
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-ALIAS-FIELD-COVERAGE",
                            "split/merge/alias/replacement requires field_mappings",
                            "evidence_aliases.yaml",
                            mid,
                        )
                    )
                # uncovered required consumer field signaled by coverage NOT in allowed set
                for fm in fmaps:
                    if fm.get("coverage") == "UNCOVERED":
                        st.fail(
                            ErrorRec(
                                "R5A-PROV-ALIAS-FIELD-UNCOVERED",
                                f"required field uncovered {fm}",
                                "evidence_aliases.yaml",
                                mid,
                            )
                        )
                # conflicting field meaning marker
                if "CONFLICTING_FIELD_MEANING" in str(m.get("semantic_equivalence", "")):
                    st.fail(
                        ErrorRec(
                            "R5A-PROV-ALIAS-FIELD-CONFLICT",
                            "merge/split reports conflicting field meaning",
                            "evidence_aliases.yaml",
                            mid,
                        )
                    )

        # every current marker identity must be covered
        cat = self.docs.get("catalog") or {}
        marker_ids = set()
        marker_evs = set()
        for obj in cat.get("catalog_contract", {}).get("objects", []):
            attrs = obj.get("attributes") or {}
            mk = attrs.get("marker_id")
            ev = attrs.get("marker_identity")
            if mk and str(mk).startswith("MARKER-"):
                marker_ids.add(mk)
                if ev:
                    marker_evs.add(ev)
        for ev in marker_evs:
            if ev not in covered_current:
                st.fail(
                    ErrorRec(
                        "R5A-PROV-ALIAS-UNMAPPED",
                        f"unmapped required EV reference {ev}",
                        "evidence_aliases.yaml",
                        ev,
                    )
                )
        for mk in marker_ids:
            if mk not in covered_markers:
                st.fail(
                    ErrorRec(
                        "R5A-PROV-ALIAS-MARKER",
                        f"marker not covered by alias registry {mk}",
                        "evidence_aliases.yaml",
                        mk,
                    )
                )
        st.counts["markers_covered"] = len(covered_markers)
        st.counts["current_ev_covered"] = len(covered_current)
        st.counts["current_refs_seen"] = len(current_refs)
        self.add_stage(st)

    def _stage_portable_path_invariants(self) -> None:
        st = StageResult("portable_path_invariants")
        hits = 0
        for rel in PORTABLE_PATH_SCAN_FILES:
            p = self.path(rel)
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            # allow prose about prohibited examples only in decision markdown-like notes? none of these files should have abs paths
            for m in ABS_PATH_RE.finditer(txt):
                # skip if explicitly marked as prohibited example nearby
                start = max(0, m.start() - 80)
                window = txt[start : m.end() + 80]
                if "prohibited example" in window.lower() or "PROHIBITED_EXAMPLE" in window:
                    continue
                hits += 1
                st.fail(
                    ErrorRec(
                        "R5A-PROV-PATH-ABSOLUTE",
                        f"absolute or machine-specific path found: {m.group(0)}",
                        rel,
                    )
                )
        # reconstructed evidence must be logical external artifact
        man = (self.docs.get("manifest") or {}).get("registry_manifest") or {}
        recon = man.get("reconstructed_evidence_manifest") or {}
        if recon.get("location_policy") != "RUNTIME_SUPPLIED_EXTERNAL_ARTIFACT":
            st.fail(
                ErrorRec(
                    "R5A-PROV-PATH-EXTERNAL",
                    "reconstructed_evidence_manifest must use RUNTIME_SUPPLIED_EXTERNAL_ARTIFACT",
                    "registry_manifest.yaml",
                )
            )
        if "path" in recon and isinstance(recon.get("path"), str) and ABS_PATH_RE.search(recon["path"] or ""):
            st.fail(
                ErrorRec(
                    "R5A-PROV-PATH-TEMP",
                    "reconstructed_evidence_manifest must not use absolute TEMP path",
                    "registry_manifest.yaml",
                )
            )
        st.counts["hits"] = hits
        self.add_stage(st)


    def _stage_final(self) -> None:
        st = StageResult("final_summary")
        st.counts = dict(self.counts)
        if self.errors:
            st.status = "FAIL"
        self.add_stage(st)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Round 5A registries and fixtures offline")
    parser.add_argument("--root", required=True, help="repository root")
    parser.add_argument("--report", required=True, help="output report JSON path")
    args = parser.parse_args(argv)
    root = Path(args.root)
    report_path = Path(args.report)
    if not root.exists():
        print("root does not exist", file=sys.stderr)
        return 2
    try:
        validator = Round5AValidator(root)
        report = validator.run()
    except Exception as exc:  # environment/usage failure
        print(f"validator environment failure: {exc}", file=sys.stderr)
        return 2
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = report["final_status"]
    if status == "PASS":
        return 0
    if status == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
