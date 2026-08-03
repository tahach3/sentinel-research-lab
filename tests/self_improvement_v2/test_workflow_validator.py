from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.workflow_validator import validate_workflow


def test_workflow_inactive_with_risk_branches():
    root = worker_package_root()
    report = validate_workflow(root, root / "workflows/design/self_improvement_loop_v2.json")
    assert report["status"] == "PASS"
