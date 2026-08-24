"""Workflow design validator tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.self_improvement.workflow_validator import validate_workflow

ROOT = Path(__file__).resolve().parents[2]


def test_design_workflow_passes() -> None:
    report = validate_workflow(ROOT, ROOT / "workflows/design/self_improvement_loop_v1.json")
    assert report["status"] == "PASS"


def test_workflow_active_true_rejected(tmp_path: Path) -> None:
    src = json.loads((ROOT / "workflows/design/self_improvement_loop_v1.json").read_text(encoding="utf-8"))
    src["active"] = True
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(src), encoding="utf-8")
    report = validate_workflow(ROOT, path)
    assert report["status"] == "FAIL"
    assert any(e["code"] == "WORKFLOW_ACTIVE" for e in report["errors"])


def test_credentials_included_rejected(tmp_path: Path) -> None:
    src = json.loads((ROOT / "workflows/design/self_improvement_loop_v1.json").read_text(encoding="utf-8"))
    src["nodes"].append(
        {
            "id": "bad",
            "name": "Bad Creds",
            "type": "n8n-nodes-base.code",
            "parameters": {"jsCode": "return [{json:{password: 'supersecretvalue123'}}];"},
            "typeVersion": 2,
        }
    )
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(src), encoding="utf-8")
    report = validate_workflow(ROOT, path)
    assert report["status"] == "FAIL"
    assert any(e["code"] == "CREDENTIALS_IN_WORKFLOW" for e in report["errors"])
