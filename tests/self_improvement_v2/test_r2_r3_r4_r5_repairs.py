"""R2-A / R3 / R4 / R5 repair probes (code half)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.self_improvement_v2.import_closure import assert_pin_covers_static_closure
from tools.self_improvement_v2.launcher.install_launcher import (
    LAUNCHER_ENTRYPOINT,
    LAUNCHER_PIN_REL,
    LAUNCHER_TRUSTED_MODULE_NAMES,
    compute_verifier_digest,
    install_launcher,
)
from tools.self_improvement_v2.runtime_config import RuntimeConfigError, load_runtime_config
from tools.self_improvement_v2.trusted_origin import (
    ENV_REPOSITORY_ROOT,
    ENV_REVIEWED_HEAD,
    PIN_REL,
    TrustedOriginError,
    _git_head,
    assert_trusted_code_origin,
)

REPO = Path(__file__).resolve().parents[2]


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def test_r2a_raw_git_ignores_ambient_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init"], cwd=other, check=True, capture_output=True)
    (other / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=other, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "x"],
        cwd=other,
        check=True,
        capture_output=True,
    )
    other_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=other, text=True).strip()
    real = _head()
    assert other_head != real
    monkeypatch.setenv("GIT_DIR", str((other / ".git").resolve()))
    monkeypatch.setenv("GIT_WORK_TREE", str(other.resolve()))
    assert _git_head(REPO) == real


def test_r2a_launcher_script_sanitizes_git_env(tmp_path: Path) -> None:
    installed = install_launcher(
        repository_root=REPO,
        reviewed_head=_head(),
        install_dir=tmp_path / "SentinelResearchLab",
    )
    sh = Path(installed["launch_worker_sh"]).read_text(encoding="utf-8")
    ps1 = Path(installed["launch_worker_ps1"]).read_text(encoding="utf-8")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        assert name in sh
        assert name in ps1
    assert "unset" in sh
    assert "Remove-Item Env:GIT_DIR" in ps1
    att = json.loads(Path(installed["attestation"]).read_text(encoding="utf-8"))
    assert Path(att["git_executable"]).is_file()


def test_r3_install_refuses_wrong_head(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reviewed_head must equal live HEAD"):
        install_launcher(
            repository_root=REPO,
            reviewed_head="a" * 40,
            install_dir=tmp_path / "SentinelResearchLab",
        )


def test_r3_install_refuses_dirty_tree(tmp_path: Path) -> None:
    marker = REPO / ".r3_dirty_probe_marker"
    assert not marker.exists()
    marker.write_text("dirty\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="dirty worktree"):
            install_launcher(
                repository_root=REPO,
                reviewed_head=_head(),
                install_dir=tmp_path / "SentinelResearchLab",
            )
    finally:
        marker.unlink(missing_ok=True)


def test_r3_install_refuses_digest_override_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected_digest must match on-disk"):
        install_launcher(
            repository_root=REPO,
            reviewed_head=_head(),
            install_dir=tmp_path / "SentinelResearchLab",
            expected_digest="a" * 64,
        )


def test_r3_launcher_pin_equals_installer_closure() -> None:
    assert_pin_covers_static_closure(
        REPO, LAUNCHER_TRUSTED_MODULE_NAMES, entrypoint=LAUNCHER_ENTRYPOINT
    )
    pin = json.loads((REPO / LAUNCHER_PIN_REL).read_text(encoding="utf-8"))
    assert set(pin["modules"]) == set(LAUNCHER_TRUSTED_MODULE_NAMES)
    assert "tools.self_improvement_v2.launcher.install_launcher" in pin["modules"]
    assert "tools.self_improvement_v2.launcher.paths" in pin["modules"]
    # Pin file authenticates itself via install-time byte match + attestation digest.
    assert (REPO / LAUNCHER_PIN_REL).is_file()


def test_r3_launcher_pin_negative_under_coverage_fails() -> None:
    under = tuple(m for m in LAUNCHER_TRUSTED_MODULE_NAMES if not m.endswith(".paths"))
    with pytest.raises(AssertionError, match="missing|extra"):
        assert_pin_covers_static_closure(REPO, under, entrypoint=LAUNCHER_ENTRYPOINT)


def test_r3_launcher_pin_negative_extra_module_breaks_equality(tmp_path: Path) -> None:
    pkg = tmp_path / "tools" / "self_improvement_v2" / "launcher"
    pkg.mkdir(parents=True)
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "self_improvement_v2" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "install_launcher.py").write_text(
        "from tools.self_improvement_v2.launcher import paths\n"
        "from tools.self_improvement_v2.launcher import _extra_probe\n"
        "from tools.self_improvement_v2 import import_closure\n",
        encoding="utf-8",
    )
    (pkg / "paths.py").write_text("X=1\n", encoding="utf-8")
    (pkg / "_extra_probe.py").write_text("Y=2\n", encoding="utf-8")
    (tmp_path / "tools" / "self_improvement_v2" / "import_closure.py").write_text(
        "ENTRYPOINT='x'\n", encoding="utf-8"
    )
    pinned = frozenset(
        {
            "tools.self_improvement_v2.launcher.install_launcher",
            "tools.self_improvement_v2.launcher.paths",
            "tools.self_improvement_v2.import_closure",
        }
    )
    with pytest.raises(AssertionError, match="missing"):
        assert_pin_covers_static_closure(
            tmp_path,
            pinned,
            entrypoint="tools.self_improvement_v2.launcher.install_launcher",
        )


def test_r4_load_runtime_config_refuses_divergent_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V-R4: P4 verbatim — load_runtime_config directly must refuse divergence."""
    from tests.self_improvement_v2.helpers import init_temp_repo

    token = "test-worker-token-not-for-production"
    attested = tmp_path / "attested" / "sentinel-research-lab"
    rogue = tmp_path / "rogue" / "sentinel-research-lab"
    init_temp_repo(attested)
    init_temp_repo(rogue)
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(attested.resolve()))
    monkeypatch.setenv("SRL_WORKER_TOKEN", token)
    with pytest.raises(RuntimeConfigError, match="must equal SRL_REPOSITORY_ROOT"):
        load_runtime_config(
            repository_root=str(rogue.resolve()),
            state_db=str(tmp_path / "db.sqlite"),
            worker_token=token,
            worker_host="127.0.0.1",
            worker_port=8765,
        )


def test_r5_unknown_pin_keys_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Work against a local clone so production pin stays intact.
    clone = tmp_path / "sentinel-research-lab"
    subprocess.run(
        ["git", "clone", "--local", str(REPO), str(clone)],
        check=True,
        capture_output=True,
    )
    pin_path = clone / PIN_REL
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    pin["extra_unvalidated_key"] = "nope"
    pin_path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=clone, text=True).strip()
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(clone))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, head)
    with pytest.raises(TrustedOriginError, match="unknown keys"):
        assert_trusted_code_origin()


def test_r5_head_content_binding_no_longer_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional-if-present path deleted — pin without the field still accepts when otherwise valid."""
    head = _head()
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(REPO))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, head)
    pin = json.loads((REPO / PIN_REL).read_text(encoding="utf-8"))
    assert "head_content_binding" not in pin
    result = assert_trusted_code_origin()
    assert result["reviewed_git_head"] == head
    assert compute_verifier_digest(REPO)
