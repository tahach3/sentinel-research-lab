from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.validate_system import SystemValidator


def test_system_validator_probes_pass():
    root = worker_package_root()
    report = SystemValidator(root).run()
    assert report["final_status"] == "PASS", report["errors"]
    assert len(report["probe_results"]["nested_paths"]) >= 7
    assert report["probe_results"]["proposal_immutability"] == "SI2-STORE-IMMUTABILITY"
    v1 = report["probe_results"]["v1_pwned"]
    if isinstance(v1, dict):
        assert v1["detected"] is True
        assert v1["actual_error_code"] == "CONTENT_BINDING_MISMATCH"
    else:
        assert v1 == "CONTENT_BINDING_MISMATCH"
    assert report["probe_results"]["workflow_graph_mutations"]
    assert all(p["detected"] for p in report["probe_results"]["workflow_graph_mutations"])
    assert report["probe_results"]["git_hooks_signing"]
    assert all(p["detected"] for p in report["probe_results"]["git_hooks_signing"])
    assert report["probe_results"]["proposal_binding"]
    assert all(p["detected"] for p in report["probe_results"]["proposal_binding"])
