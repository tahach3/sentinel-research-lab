from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.validate_system import SystemValidator


def test_system_validator_probes_pass():
    root = worker_package_root()
    report = SystemValidator(root).run()
    assert report["final_status"] == "PASS", report["errors"]
    assert len(report["probe_results"]["nested_paths"]) >= 7
    assert report["probe_results"]["proposal_immutability"] == "SI2-STORE-IMMUTABILITY"
    assert report["probe_results"]["v1_pwned"] == "CONTENT_BINDING_MISMATCH"
