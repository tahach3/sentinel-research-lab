"""Kernel validator CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.round5a_kernel.validate_kernel import KernelValidator, build_manifest, main

ROOT = Path(__file__).resolve().parents[2]


def test_validator_pass_and_manifest_builder(tmp_path: Path) -> None:
    manifest = build_manifest(ROOT)
    assert manifest["artifact_type"] == "kernel_manifest"
    assert all(a["path"] != "specs/round5a_kernel/kernel_manifest.json" for a in manifest["artifacts"])
    (ROOT / "specs/round5a_kernel/kernel_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    report_path = tmp_path / "report.json"
    code = main(["--root", str(ROOT), "--report", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["final_status"] == "PASS"
    assert report["checks"]["bounded-domain disagreements"] == 0
    assert report["checks"]["reachable_rules"] == 22
