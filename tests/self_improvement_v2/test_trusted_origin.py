"""Trusted-code origin pin — reject worktree-derived import roots."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tools.self_improvement_v2 import risk_authority
from tools.self_improvement_v2.models import ERROR_CODES
from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.trusted_origin import (
    TrustedOriginError,
    assert_module_from_worker_install,
    assert_no_worktree_on_sys_path,
    assert_trusted_code_origin,
    reject_worktree_as_import_root,
)


def test_trusted_modules_resolve_under_worker_install() -> None:
    result = assert_trusted_code_origin()
    root = Path(result["install_root"])
    assert root == worker_package_root().resolve()
    assert "tools.self_improvement_v2.risk_authority" in result["modules"]
    path = assert_module_from_worker_install(risk_authority)
    assert path.is_file()
    assert str(worker_package_root().resolve()) in str(path)


def test_worktree_sys_path_rejected(tmp_path: Path) -> None:
    fake_wt = tmp_path / "srl-si2-wt-deadbeef" / "worktree"
    fake_wt.mkdir(parents=True)
    inserted = str(fake_wt)
    sys.path.insert(0, inserted)
    try:
        with pytest.raises(TrustedOriginError) as exc:
            assert_no_worktree_on_sys_path()
        assert exc.value.code == ERROR_CODES["TRUSTED_ORIGIN_VIOLATION"]
    finally:
        while inserted in sys.path:
            sys.path.remove(inserted)


def test_reject_worktree_as_import_root(tmp_path: Path) -> None:
    fake_wt = tmp_path / "srl-si2-wt-abc" / "worktree"
    (fake_wt / "tools" / "self_improvement_v2").mkdir(parents=True)
    with pytest.raises(TrustedOriginError) as exc:
        reject_worktree_as_import_root(fake_wt)
    assert exc.value.code == ERROR_CODES["TRUSTED_ORIGIN_VIOLATION"]
