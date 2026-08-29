from pathlib import Path

import pytest

from tests.self_improvement_v2.helpers import init_temp_repo, sha256_text
from tools.self_improvement_v2.models import WorkerError
from tools.self_improvement_v2.patch_validator import validate_patch_object
from tools.self_improvement_v2.path_policy import load_policy


def test_delete_operation_rejected(tmp_path: Path):
    repo = tmp_path / "r"
    init_temp_repo(repo)
    policy = load_policy(repo)
    proposal = {"allowed_paths": ["docs/**"], "forbidden_paths": []}
    patch = {
        "path": "docs/README.md",
        "operation": "DELETE",
        "unified_diff": (
            "diff --git a/docs/README.md b/docs/README.md\n"
            "deleted file mode 100644\n"
            "--- a/docs/README.md\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-# Temp docs\n"
        ),
        "expected_preimage_sha256": sha256_text("# Temp docs\n"),
        "expected_postimage_sha256": "",
    }
    with pytest.raises(WorkerError):
        validate_patch_object(patch, policy=policy, proposal=proposal, repo_root=repo)
