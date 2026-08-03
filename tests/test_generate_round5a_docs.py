#!/usr/bin/env python3
"""Focused unittest suite for tools/generate_round5a_docs.py."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
import generate_round5a_docs as g  # noqa: E402

CLONE_PATHS = [
    "specs/round5a/schema/round5a_registry.schema.json",
    "specs/round5a/SCHEMA_CONTRACT.md",
    "specs/round5a/catalog_contract.yaml",
    "specs/round5a/checkpoints.yaml",
    "specs/round5a/reconciliation_rules.yaml",
    "specs/round5a/evidence_aliases.yaml",
    "specs/round5a/registry_manifest.yaml",
    "specs/round5a/fixtures/reconciliation_witnesses.yaml",
    "specs/round5a/fixtures/checkpoint_oracles.yaml",
    "specs/round5a/fixtures/privilege_cases.yaml",
    "docs/ROUND_5A_REVISION_8_NORMATIVE_DECISION_RECORD.md",
    "docs/ROUND_5A_REVISION_8_EVIDENCE_POLICY.md",
    "docs/ROUND_5A_EVIDENCE_PROVENANCE_DECISION.md",
    "docs/ROUND_5A_SECURITY_BOUNDARY_REDESIGN.md",
    "docs/ROUND_5A_SECURITY_BOUNDARY_TEST_PLAN.md",
    "evidence/round5a/archived_phase1/SRL_Phase1_catalog_snapshot.sql",
    "evidence/round5a/archived_phase1/SRL_Phase1_evidence_spec.md",
    "evidence/round5a/archived_phase1/PROVENANCE.json",
    "evidence/round5a/recreated_phase1/SRL_Phase1_catalog_snapshot.sql",
    "evidence/round5a/recreated_phase1/SRL_Phase1_evidence_spec.md",
    "evidence/round5a/recreated_phase1/RUN_ORDER.txt",
    "evidence/round5a/recreated_phase1/SHA256SUMS.txt",
    "evidence/round5a/recreated_phase1/PROVENANCE.json",
    "tools/validate_round5a.py",
    "tests/test_validate_round5a.py",
]

OUTPUTS = [
    "docs/generated/round5a/ARCHITECTURE.md",
    "docs/generated/round5a/VERIFICATION.md",
    "docs/generated/round5a/TRACEABILITY.md",
    "docs/generated/round5a/generation_manifest.json",
]


class GenerateRound5ADocsTests(unittest.TestCase):
    def _clone_repo(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="r5a-gen-"))
        for rel in CLONE_PATHS:
            src = ROOT / rel
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        (tmp / ".git").mkdir()
        (tmp / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
        (tmp / ".git" / "refs" / "heads").mkdir(parents=True)
        (tmp / ".git" / "refs" / "heads" / "master").write_text(("ab" * 20) + "\n", encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return tmp

    def _run(self, root: Path, *args: str) -> tuple[int, dict]:
        report = root / "gen-report.json"
        code = g.main(["--root", str(root), *args, "--report", str(report)])
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        return code, data

    def _load(self, root: Path, rel: str) -> dict:
        return json.loads((root / rel).read_text(encoding="utf-8"))

    def _dump(self, root: Path, rel: str, doc: dict) -> None:
        (root / rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def _codes(self, report: dict) -> set[str]:
        return {e["code"] for e in report.get("errors", [])}

    def test_01_clean_sources_generate_all_outputs(self):
        root = self._clone_repo()
        code, report = self._run(root, "--write")
        self.assertEqual(code, 0)
        self.assertEqual(report["final_status"], "PASS")
        for rel in OUTPUTS:
            self.assertTrue((root / rel).exists(), rel)

    def test_02_two_renders_identical_bytes(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        first = {rel: (root / rel).read_bytes() for rel in OUTPUTS}
        # delete and regenerate
        for rel in OUTPUTS:
            (root / rel).unlink()
        self.assertEqual(self._run(root, "--write")[0], 0)
        second = {rel: (root / rel).read_bytes() for rel in OUTPUTS}
        self.assertEqual(first, second)

    def test_03_check_passes_after_write(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        code, report = self._run(root, "--check")
        self.assertEqual(code, 0)
        self.assertEqual(report["final_status"], "PASS")
        self.assertEqual(report.get("drift"), [])

    def test_04_architecture_drift_fails(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        p = root / "docs/generated/round5a/ARCHITECTURE.md"
        p.write_bytes(p.read_bytes() + b"\nmanual edit\n")
        code, report = self._run(root, "--check")
        self.assertEqual(code, 1)
        self.assertIn("R5A-GEN-DRIFT-MISMATCH", self._codes(report))

    def test_05_verification_drift_fails(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        p = root / "docs/generated/round5a/VERIFICATION.md"
        p.write_bytes(p.read_bytes() + b"\nmanual edit\n")
        code, report = self._run(root, "--check")
        self.assertEqual(code, 1)
        self.assertIn("R5A-GEN-DRIFT-MISMATCH", self._codes(report))

    def test_06_missing_generated_output_fails(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        (root / "docs/generated/round5a/TRACEABILITY.md").unlink()
        code, report = self._run(root, "--check")
        self.assertEqual(code, 1)
        self.assertIn("R5A-GEN-DRIFT-MISSING", self._codes(report))

    def test_07_missing_normative_source_env_failure(self):
        root = self._clone_repo()
        (root / "specs/round5a/catalog_contract.yaml").unlink()
        code, report = self._run(root, "--write")
        self.assertEqual(code, 2)
        self.assertIn("R5A-GEN-FILE-MISSING", self._codes(report))

    def test_08_invalid_source_json_prevents_generation(self):
        root = self._clone_repo()
        (root / "specs/round5a/fixtures/privilege_cases.yaml").write_text("{", encoding="utf-8")
        code, report = self._run(root, "--write")
        self.assertEqual(code, 2)
        self.assertIn("R5A-GEN-SOURCE-JSON", self._codes(report))
        self.assertFalse((root / "docs/generated/round5a/ARCHITECTURE.md").exists())

    def test_09_validator_failure_prevents_generation(self):
        root = self._clone_repo()
        doc = self._load(root, "specs/round5a/fixtures/privilege_cases.yaml")
        doc["privilege_fixture_pack"]["fixtures"][0].pop("owner")
        self._dump(root, "specs/round5a/fixtures/privilege_cases.yaml", doc)
        code, report = self._run(root, "--write")
        self.assertEqual(code, 1)
        self.assertIn("R5A-GEN-SOURCE-VALIDATOR", self._codes(report))
        self.assertFalse((root / "docs/generated/round5a/ARCHITECTURE.md").exists())

    def test_10_manifest_hash_mismatch_prevents_generation(self):
        root = self._clone_repo()
        man = self._load(root, "specs/round5a/registry_manifest.yaml")
        man["registry_manifest"]["artifact_hashes"][0]["sha256"] = "0" * 64
        self._dump(root, "specs/round5a/registry_manifest.yaml", man)
        code, report = self._run(root, "--write")
        self.assertEqual(code, 1)
        codes = self._codes(report)
        self.assertTrue("R5A-GEN-MANIFEST-HASH" in codes or "R5A-GEN-SOURCE-VALIDATOR" in codes)

    def test_11_all_31_markers_in_architecture(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        cat = self._load(root, "specs/round5a/catalog_contract.yaml")["catalog_contract"]
        markers = [
            o["attributes"]["marker_id"]
            for o in cat["objects"]
            if str(o.get("attributes", {}).get("marker_id", "")).startswith("MARKER-")
        ]
        self.assertEqual(len(markers), 31)
        for mid in markers:
            self.assertIn(mid, text)

    def test_12_all_18_checkpoints_appear(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        cps = self._load(root, "specs/round5a/checkpoints.yaml")["checkpoint_registry"]["checkpoints"]
        self.assertEqual(len(cps), 18)
        for c in cps:
            self.assertIn(c["checkpoint_id"], text)

    def test_13_all_22_rules_exact_order(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        positions = []
        for i in range(1, 23):
            rid = f"RULE-{i:02d}"
            self.assertIn(rid, text)
            positions.append(text.index(f"Order {i}: {rid}"))
        self.assertEqual(positions, sorted(positions))

    def test_14_rule22_reachable_failed_frozen(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        idx = text.index("Order 22: RULE-22")
        section = text[idx : idx + 800]
        self.assertIn("Fallback: yes", section)
        self.assertIn("Reachable: yes", section)
        self.assertIn("failed_frozen", section)
        self.assertIn("missing required status", section)

    def test_15_w1_w22_in_verification(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/VERIFICATION.md").read_text(encoding="utf-8")
        for i in range(1, 23):
            self.assertIn(f"FIXTURE-W{i}", text)

    def test_16_b1_b21_in_verification(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/VERIFICATION.md").read_text(encoding="utf-8")
        for i in range(1, 22):
            self.assertIn(f"FIXTURE-B{i}", text)

    def test_17_shadowing_total_231(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/VERIFICATION.md").read_text(encoding="utf-8")
        self.assertIn("Shadowing pairs: 231", text)
        man = self._load(root, "docs/generated/round5a/generation_manifest.json")
        self.assertEqual(man["counts"]["shadowing_pairs"], 231)

    def test_18_every_nd_in_traceability(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        nds = set()
        for rel in [
            "specs/round5a/catalog_contract.yaml",
            "specs/round5a/checkpoints.yaml",
            "specs/round5a/reconciliation_rules.yaml",
            "specs/round5a/fixtures/reconciliation_witnesses.yaml",
            "specs/round5a/fixtures/checkpoint_oracles.yaml",
            "specs/round5a/fixtures/privilege_cases.yaml",
            "specs/round5a/registry_manifest.yaml",
        ]:
            nds.update(re.findall(r"ND-[A-Z0-9-]+", (root / rel).read_text(encoding="utf-8")))
        for nd in sorted(nds):
            self.assertIn(nd, text)

    def test_19_every_marker_in_traceability(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        cat = self._load(root, "specs/round5a/catalog_contract.yaml")["catalog_contract"]
        for o in cat["objects"]:
            mid = o.get("attributes", {}).get("marker_id", "")
            if str(mid).startswith("MARKER-"):
                self.assertIn(mid, text)

    def test_20_non_normative_warning_present(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        for rel in OUTPUTS[:3]:
            text = (root / rel).read_text(encoding="utf-8")
            self.assertIn("AUTOGENERATED — DO NOT EDIT MANUALLY", text)
            self.assertIn("Generated documentation is non-normative.", text)
            self.assertIn("When generated text conflicts with a registry, the registry controls.", text)

    def test_21_no_timestamp_in_generated(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        for rel in OUTPUTS:
            text = (root / rel).read_text(encoding="utf-8")
            self.assertNotIn("generated_at", text)
            self.assertIsNone(re.search(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", text))

    def test_22_no_absolute_temp_path(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        for rel in OUTPUTS:
            text = (root / rel).read_text(encoding="utf-8").replace("\\", "/")
            self.assertNotIn("AppData/Local/Temp", text)
            self.assertNotRegex(text, r"(?i)C:/Users/")
            self.assertNotIn("/tmp/", text)

    def test_23_lf_and_final_newline(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        for rel in OUTPUTS:
            data = (root / rel).read_bytes()
            self.assertFalse(b"\r" in data, rel)
            self.assertTrue(data.endswith(b"\n"), rel)

    def test_24_manifest_output_hashes_match_files(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        man = self._load(root, "docs/generated/round5a/generation_manifest.json")
        for rel, digest in man["generated_outputs"].items():
            self.assertEqual(digest, g.sha256_file(root / rel))

    def test_25_manifest_self_hash_absent(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        man = self._load(root, "docs/generated/round5a/generation_manifest.json")
        self.assertNotIn("docs/generated/round5a/generation_manifest.json", man.get("generated_outputs", {}))
        self.assertNotIn("manifest_sha256", man)
        self.assertNotIn("self_hash", man)

    def test_26_evidence_alias_table_generated(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        self.assertIn("## Evidence aliases", text)
        self.assertIn("| Archived EV | Mapping type | Recreated EV | Current EV | Affected markers | Decision | Status |", text)

    def test_27_every_mapping_appears(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        aliases = self._load(root, "specs/round5a/evidence_aliases.yaml")
        for m in aliases["evidence_alias_registry"]["mappings"]:
            self.assertIn(m["mapping_type"], text)
            for cur in m["current_evidence_ids"]:
                self.assertIn(cur, text)

    def test_28_all_31_markers_resolve_via_aliases(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        text = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        cat = self._load(root, "specs/round5a/catalog_contract.yaml")["catalog_contract"]
        count = 0
        for o in cat["objects"]:
            mid = o.get("attributes", {}).get("marker_id", "")
            if str(mid).startswith("MARKER-"):
                count += 1
                self.assertIn(mid, text)
        self.assertEqual(count, 31)

    def test_29_historical_authentication_unverified(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        arch = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        trace = (root / "docs/generated/round5a/TRACEABILITY.md").read_text(encoding="utf-8")
        self.assertIn("UNVERIFIED", arch)
        self.assertIn("Historical authentication rendered: `UNVERIFIED`", trace)
        self.assertNotIn("historical authentication: VERIFIED", arch.lower())

    def test_30_provenance_sections_and_no_abs_paths(self):
        root = self._clone_repo()
        self.assertEqual(self._run(root, "--write")[0], 0)
        arch = (root / "docs/generated/round5a/ARCHITECTURE.md").read_text(encoding="utf-8")
        ver = (root / "docs/generated/round5a/VERIFICATION.md").read_text(encoding="utf-8")
        self.assertIn("## Evidence provenance", arch)
        self.assertIn("ROUND5A-RECONSTRUCTED-REFERENCE-SCHEMA8", arch)
        self.assertIn("R5A-PROV-SOURCE-*", ver)
        self.assertIn("R5A-PROV-ALIAS-*", ver)
        for rel in OUTPUTS:
            text = (root / rel).read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", text)
            self.assertNotIn("AppData\\Local\\Temp", text)


if __name__ == "__main__":
    unittest.main()
