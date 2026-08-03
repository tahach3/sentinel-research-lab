"""Patch safety negative tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.self_improvement.helpers import create_file_diff, init_temp_repo, modify_file_diff, sha256_text
from tools.self_improvement.models import WorkerError
from tools.self_improvement.patch_validator import validate_patch_object
from tools.self_improvement.policy import load_policy

ROOT = Path(__file__).resolve().parents[2]


def _proposal(path: str = "docs/x.md") -> dict:
    return {
        "allowed_paths": ["docs/**", "tests/**"],
        "forbidden_paths": [],
        "patches": [],
    }


def test_path_traversal_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    patch = {
        "path": "docs/../secrets/x.md",
        "operation": "CREATE",
        "unified_diff": create_file_diff("docs/../secrets/x.md", "x\n"),
        "expected_preimage_sha256": "",
        "expected_postimage_sha256": sha256_text("x\n"),
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "PATH_TRAVERSAL"


def test_absolute_patch_path_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    abs_path = str((repo / "docs" / "x.md").resolve())
    patch = {
        "path": abs_path,
        "operation": "CREATE",
        "unified_diff": f"diff --git a/{abs_path} b/{abs_path}\n--- /dev/null\n+++ b/{abs_path}\n@@ -0,0 +1,1 @@\n+x\n",
        "expected_preimage_sha256": "",
        "expected_postimage_sha256": sha256_text("x\n"),
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "ABSOLUTE_PATH"


def test_binary_patch_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    patch = {
        "path": "docs/bin.md",
        "operation": "CREATE",
        "unified_diff": "diff --git a/docs/bin.md b/docs/bin.md\nGIT binary patch\nliteral 1\n",
        "expected_preimage_sha256": "",
        "expected_postimage_sha256": "a" * 64,
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "BINARY_PATCH"


def test_deletion_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    patch = {
        "path": "docs/README.md",
        "operation": "DELETE",
        "unified_diff": "diff --git a/docs/README.md b/docs/README.md\ndeleted file mode 100644\n--- a/docs/README.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-# Temp docs\n",
        "expected_preimage_sha256": sha256_text("# Temp docs\n"),
        "expected_postimage_sha256": "",
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "DELETION_PROHIBITED"


def test_preimage_and_postimage_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    old_bytes = (repo / "docs" / "README.md").read_bytes()
    old = old_bytes.decode("utf-8")
    new = "# Changed\n"
    import hashlib

    actual_pre = hashlib.sha256(old_bytes).hexdigest()
    patch = {
        "path": "docs/README.md",
        "operation": "MODIFY",
        "unified_diff": modify_file_diff("docs/README.md", old, new),
        "expected_preimage_sha256": "0" * 64,
        "expected_postimage_sha256": sha256_text(new),
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "PREIMAGE_MISMATCH"

    patch2 = {
        "path": "docs/README.md",
        "operation": "MODIFY",
        "unified_diff": modify_file_diff("docs/README.md", old, new),
        "expected_preimage_sha256": actual_pre,
        "expected_postimage_sha256": "nope",
    }
    with pytest.raises(WorkerError) as exc2:
        validate_patch_object(patch2, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc2.value.code == "POSTIMAGE_MISMATCH"


def test_forbidden_path_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_temp_repo(repo)
    policy = load_policy(ROOT)
    patch = {
        "path": ".env",
        "operation": "CREATE",
        "unified_diff": create_file_diff(".env", "X=1\n"),
        "expected_preimage_sha256": "",
        "expected_postimage_sha256": sha256_text("X=1\n"),
    }
    with pytest.raises(WorkerError) as exc:
        validate_patch_object(patch, policy=policy, proposal=_proposal(), repo_root=repo)
    assert exc.value.code == "FORBIDDEN_PATH"
