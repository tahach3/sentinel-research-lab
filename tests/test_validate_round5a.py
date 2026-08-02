#!/usr/bin/env python3
"""Focused unittest suite for tools/validate_round5a.py."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
import validate_round5a as v  # noqa: E402


NORMATIVE = [
    "specs/round5a/schema/round5a_registry.schema.json",
    "specs/round5a/SCHEMA_CONTRACT.md",
    "specs/round5a/catalog_contract.yaml",
    "specs/round5a/checkpoints.yaml",
    "specs/round5a/reconciliation_rules.yaml",
    "specs/round5a/registry_manifest.yaml",
    "specs/round5a/fixtures/reconciliation_witnesses.yaml",
    "specs/round5a/fixtures/checkpoint_oracles.yaml",
    "specs/round5a/fixtures/privilege_cases.yaml",
    "docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md",
    "docs/ROUND_5A_REVISION_8_EVIDENCE_POLICY.md",
    "docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md",
    "docs/ROUND_5A_SECURITY_BOUNDARY_TEST_PLAN.md",
]


class ValidateRound5ATests(unittest.TestCase):
    def _clone_repo(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="r5a-val-"))
        for rel in NORMATIVE:
            src = ROOT / rel
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        # minimal git head for report
        (tmp / ".git").mkdir()
        (tmp / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
        (tmp / ".git" / "refs" / "heads").mkdir(parents=True)
        (tmp / ".git" / "refs" / "heads" / "master").write_text("deadbeef" * 5 + "\n", encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return tmp

    def _run(self, root: Path) -> tuple[int, dict]:
        report = root / "report.json"
        code = v.main(["--root", str(root), "--report", str(report)])
        if not report.exists():
            return code, {"final_status": "BLOCKED", "errors": [{"code": "R5A-FILE-JSON", "message": "no report"}]}
        return code, json.loads(report.read_text(encoding="utf-8"))

    def _load(self, root: Path, rel: str) -> dict:
        return json.loads((root / rel).read_text(encoding="utf-8"))

    def _dump(self, root: Path, rel: str, doc: dict) -> None:
        (root / rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def test_01_clean_pass(self):
        root = self._clone_repo()
        code, report = self._run(root)
        self.assertEqual(code, 0)
        self.assertEqual(report["final_status"], "PASS")

    def test_02_missing_file(self):
        root = self._clone_repo()
        (root / "specs/round5a/fixtures/privilege_cases.yaml").unlink()
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-FILE-MISSING" for e in report["errors"]))

    def test_03_invalid_json(self):
        root = self._clone_repo()
        p = root / "specs/round5a/fixtures/privilege_cases.yaml"
        p.write_text("{", encoding="utf-8")
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-FILE-JSON" for e in report["errors"]))

    def test_04_schema_violation(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/privilege_cases.yaml")
        doc["privilege_fixture_pack"]["fixtures"][0].pop("owner")
        self._dump(root, "specs/round5a/fixtures/privilege_cases.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-SCHEMA-INVALID" for e in report["errors"]))

    def test_05_manifest_hash_mismatch(self):
        root = self._clone_repo()
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        man["registry_manifest"]["artifact_hashes"][0]["sha256"] = "0" * 64
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-MANIFEST-HASH" for e in report["errors"]))

    def test_06_duplicate_checkpoint_id(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/checkpoints.yaml")
        doc["checkpoint_registry"]["checkpoints"][1]["checkpoint_id"] = doc["checkpoint_registry"]["checkpoints"][0]["checkpoint_id"]
        self._dump(root, "specs/round5a/checkpoints.yaml", doc)
        # refresh manifest hash for checkpoints so hash stage doesn't dominate
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("checkpoints.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
            if e["path"].endswith("catalog_contract.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-CKP-COUNT" for e in report["errors"]))

    def test_07_checkpoint_oid_identity(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/checkpoints.yaml")
        doc["checkpoint_registry"]["checkpoints"][0]["identity_fields"]["identity_fields"][0]["path"] = ["oid"]
        self._dump(root, "specs/round5a/checkpoints.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("checkpoints.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-CKP-OID" for e in report["errors"]))

    def test_10_duplicate_rule_order(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/reconciliation_rules.yaml")
        doc["reconciliation_rule_registry"]["rules"][1]["order"] = 1
        self._dump(root, "specs/round5a/reconciliation_rules.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-RULE-ORDER" for e in report["errors"]))

    def test_11_fallback_not_last(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/reconciliation_rules.yaml")
        rules = doc["reconciliation_rule_registry"]["rules"]
        # Keep RULE-22 as fallback but move it earlier than last.
        rules[21]["order"] = 21
        rules[20]["order"] = 22
        self._dump(root, "specs/round5a/reconciliation_rules.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(
            any(
                e["code"] in {"R5A-RULE-FALLBACK", "R5A-SCHEMA-INVALID", "R5A-RULE-ORDER", "R5A-RULE-UNREACHABLE", "R5A-FIXTURE-OWNER"}
                for e in report["errors"]
            )
        )

    def test_12_second_fallback(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/reconciliation_rules.yaml")
        doc["reconciliation_rule_registry"]["rules"][0]["is_fallback"] = True
        doc["reconciliation_rule_registry"]["rules"][0]["failure_state"] = "failed_frozen"
        self._dump(root, "specs/round5a/reconciliation_rules.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] in {"R5A-RULE-FALLBACK", "R5A-SCHEMA-INVALID"} for e in report["errors"]))

    def test_13_decisive_missing_from_predicate(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/reconciliation_rules.yaml")
        doc["reconciliation_rule_registry"]["rules"][0]["decisive_fields"].append(
            {"scope": "source_record", "path": ["not_in_predicate"], "data_type": "string", "nullable": True}
        )
        self._dump(root, "specs/round5a/reconciliation_rules.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-RULE-DECISIVE" for e in report["errors"]))

    def test_14_missing_w_witness(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        doc["reconciliation_fixture_pack"]["fixtures"] = [
            f for f in doc["reconciliation_fixture_pack"]["fixtures"] if f["fixture_id"] != "FIXTURE-W1"
        ]
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] in {"R5A-FIXTURE-W", "R5A-SHADOW-PAIR", "R5A-RULE-UNREACHABLE"} for e in report["errors"]))

    def test_15_missing_w22(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        doc["reconciliation_fixture_pack"]["fixtures"] = [
            f for f in doc["reconciliation_fixture_pack"]["fixtures"] if f["fixture_id"] != "FIXTURE-W22"
        ]
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] in {"R5A-FIXTURE-W22", "R5A-RULE-FALLBACK-UNREACHABLE", "R5A-FIXTURE-W"} for e in report["errors"]))

    def test_16_missing_shadowing_pair(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        for f in doc["reconciliation_fixture_pack"]["fixtures"]:
            if f["fixture_id"] == "FIXTURE-W22":
                f["earlier_rules_expected_false"] = f["earlier_rules_expected_false"][:-1]
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-SHADOW-PAIR" for e in report["errors"]))

    def test_17_unreachable_rule22(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/reconciliation_rules.yaml")
        # make RULE-22 unsatisfiable again
        doc["reconciliation_rule_registry"]["rules"][21]["predicate"] = {
            "node": "all",
            "predicates": [
                {"node": "is_null", "operand": {"operand_kind": "field_ref", "field_ref": {"scope": "source_record", "path": ["status"], "data_type": "string", "nullable": True}}},
                {"node": "is_not_null", "operand": {"operand_kind": "field_ref", "field_ref": {"scope": "source_record", "path": ["status"], "data_type": "string", "nullable": True}}},
            ],
        }
        self._dump(root, "specs/round5a/reconciliation_rules.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("reconciliation_rules.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] in {"R5A-RULE-FALLBACK-UNREACHABLE", "R5A-RULE-UNREACHABLE", "R5A-FIXTURE-OWNER"} for e in report["errors"]))

    def test_18_decisive_gap(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        doc["reconciliation_fixture_pack"]["fixtures"] = [
            f for f in doc["reconciliation_fixture_pack"]["fixtures"] if f["fixture_kind"] != "MUTATION_WITNESS"
        ]
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-FIXTURE-MUT" for e in report["errors"]))

    def test_19_wrong_w22_owner(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        for f in doc["reconciliation_fixture_pack"]["fixtures"]:
            if f["fixture_id"] == "FIXTURE-W22":
                f["expected_rule"] = "RULE-01"
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-FIXTURE-OWNER" for e in report["errors"]))

    def test_20_mapping_zero_slot(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        for f in doc["reconciliation_fixture_pack"]["fixtures"]:
            if f["fixture_id"] == "FIXTURE-MAP-ZERO":
                f["expected_rule"] = "RULE-17"
                f["expected_state"]["value"] = "zero_slots_invalid_expect_fallback"
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-MAPPING-ZERO" for e in report["errors"]))

    def test_21_mapping_two_slot(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        for f in doc["reconciliation_fixture_pack"]["fixtures"]:
            if f["fixture_id"] == "FIXTURE-MAP-TWO-INVALID":
                f["input_records"] = f["input_records"][:1]
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-MAPPING-TWO" for e in report["errors"]))

    def test_24_state_b_forgery(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml")
        for f in doc["reconciliation_fixture_pack"]["fixtures"]:
            if f["fixture_id"] == "FIXTURE-STATEB-FORGED-DIGEST":
                f["expected_state"]["value"] = "ok"
        self._dump(root, "specs/round5a/fixtures/reconciliation_witnesses.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-STATE-B" for e in report["errors"]))

    def test_25_wrong_checkpoint_digest(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/checkpoint_oracles.yaml")
        for o in doc["checkpoint_oracle_pack"]["oracles"]:
            if o["expected_result"] == "PASS":
                o["expected_digest"] = "0" * 64
                break
        self._dump(root, "specs/round5a/fixtures/checkpoint_oracles.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-CKP-DIGEST" for e in report["errors"]))

    def test_27_column_acldefault_c(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/privilege_cases.yaml")
        for f in doc["privilege_fixture_pack"]["fixtures"]:
            if f["object_kind"] == "COLUMN":
                f["default_acl_semantics"]["kind"] = "acldefault_f_owner"
                break
        self._dump(root, "specs/round5a/fixtures/privilege_cases.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-PRIV-COL-DEFAULT" for e in report["errors"]))

    def test_28_fixed_role_only(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/privilege_cases.yaml")
        for f in doc["privilege_fixture_pack"]["fixtures"]:
            if "DYNAMIC" in f["fixture_id"] or "EXTRA" in f["fixture_id"]:
                f["roles"] = ["research_app", "postgres"]
        self._dump(root, "specs/round5a/fixtures/privilege_cases.yaml", doc)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-PRIV-FIXEDROLE" for e in report["errors"]))

    def test_29_evidence_count_mismatch(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/catalog_contract.yaml")
        # remove one marker object
        objs = doc["catalog_contract"]["objects"]
        for i, o in enumerate(objs):
            if str(o.get("attributes", {}).get("marker_id", "")).startswith("MARKER-"):
                del objs[i]
                break
        self._dump(root, "specs/round5a/catalog_contract.yaml", doc)
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        for e in man["registry_manifest"]["artifact_hashes"]:
            if e["path"].endswith("catalog_contract.yaml"):
                e["sha256"] = v.sha256_file(root / e["path"])
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root)
        self.assertEqual(code, 1)
        self.assertTrue(any(e["code"] == "R5A-EVIDENCE-COUNT" for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
