"""Kernel validator CLI tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.round5a_kernel.validate_kernel import (
    KernelValidator,
    build_manifest,
    main,
    manifest_bytes,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[2]

TRACKED_KERNEL_PATHS = [
    "specs/round5a_kernel/kernel_manifest.json",
    "specs/round5a_kernel/privilege_contract.json",
    "specs/round5a_kernel/reconciliation_contract.json",
    "specs/round5a_kernel/oracles/privilege_composition_cases.json",
    "specs/round5a_kernel/oracles/bounded_domain.json",
    "tools/round5a_kernel/privilege_reference.py",
    "tools/round5a_kernel/bounded_domain.py",
    "tools/round5a_kernel/validate_kernel.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_builder_is_pure_by_default(tmp_path: Path) -> None:
    before = _sha(ROOT / "specs/round5a_kernel/kernel_manifest.json")
    manifest = build_manifest(ROOT)
    data = manifest_bytes(ROOT)
    assert manifest["artifact_type"] == "kernel_manifest"
    assert all(a["path"] != "specs/round5a_kernel/kernel_manifest.json" for a in manifest["artifacts"])
    assert isinstance(data, (bytes, bytearray))
    assert _sha(ROOT / "specs/round5a_kernel/kernel_manifest.json") == before


def test_manifest_write_only_to_explicit_destination(tmp_path: Path) -> None:
    before = _sha(ROOT / "specs/round5a_kernel/kernel_manifest.json")
    dest = tmp_path / "kernel_manifest.json"
    write_manifest(ROOT, dest)
    assert dest.is_file()
    assert _sha(ROOT / "specs/round5a_kernel/kernel_manifest.json") == before
    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert loaded["artifact_type"] == "kernel_manifest"


def test_validator_pass_uses_tmp_report(tmp_path: Path) -> None:
    before = {rel: _sha(ROOT / rel) for rel in TRACKED_KERNEL_PATHS}
    report_path = tmp_path / "report.json"
    code = main(["--root", str(ROOT), "--report", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["final_status"] == "PASS"
    assert report["checks"]["bounded-domain disagreements"] == 0
    assert report["checks"]["reachable_rules"] == 22
    assert report["checks"]["genuine mutations"] == 10
    assert report["checks"]["mutation detections"] == 10
    assert report["checks"]["tautological mutations"] == 0
    assert report["checks"]["missing axes"] == 0
    assert report["checks"]["missing axis values"] == 0
    after = {rel: _sha(ROOT / rel) for rel in TRACKED_KERNEL_PATHS}
    assert after == before


def test_tracked_file_hash_guard(tmp_path: Path) -> None:
    before = {rel: _sha(ROOT / rel) for rel in TRACKED_KERNEL_PATHS}
    report_path = tmp_path / "report.json"
    code = main(["--root", str(ROOT), "--report", str(report_path)])
    assert code == 0
    after = {rel: _sha(ROOT / rel) for rel in TRACKED_KERNEL_PATHS}
    if after != before:
        raise AssertionError("KR-TEST-TRACKED-FILE-MODIFIED")
