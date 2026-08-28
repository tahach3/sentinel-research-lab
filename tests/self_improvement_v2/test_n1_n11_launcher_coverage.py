"""N1 pin=closure, N11 HEAD equality, launcher-path coverage."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from tools.self_improvement_v2.import_closure import (
    assert_pin_covers_static_closure,
    compute_static_import_closure,
)
from tools.self_improvement_v2.launcher.install_launcher import (
    bash_runtime_bridge_exec_line,
    compute_verifier_digest,
    install_launcher,
)
from tools.self_improvement_v2.trusted_origin import (
    ENV_REPOSITORY_ROOT,
    ENV_REVIEWED_HEAD,
    TRUSTED_MODULE_NAMES,
    TrustedOriginError,
    assert_trusted_code_origin,
    build_content_only_pin,
)

REPO = Path(__file__).resolve().parents[2]


def test_n1_pin_equals_static_import_closure() -> None:
    closure = compute_static_import_closure(REPO)
    assert frozenset(TRUSTED_MODULE_NAMES) == closure
    assert_pin_covers_static_closure(REPO, TRUSTED_MODULE_NAMES)


def test_n1_negative_extra_module_breaks_equality(tmp_path: Path) -> None:
    """Inject a new in-package module into the closure; equality must fail."""
    pkg = tmp_path / "tools" / "self_improvement_v2"
    pkg.mkdir(parents=True)
    # Minimal package: copy only what the calculator needs for a fake entrypoint.
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "runtime_bridge.py").write_text(
        "from tools.self_improvement_v2 import models\n"
        "from tools.self_improvement_v2 import _closure_probe_extra\n",
        encoding="utf-8",
    )
    (pkg / "models.py").write_text("X=1\n", encoding="utf-8")
    (pkg / "_closure_probe_extra.py").write_text("Y=2\n", encoding="utf-8")
    # Pretend tools package root
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    closure = compute_static_import_closure(
        tmp_path,
        entrypoint="tools.self_improvement_v2.runtime_bridge",
    )
    pinned = frozenset(
        {
            "tools.self_improvement_v2.runtime_bridge",
            "tools.self_improvement_v2.models",
            # deliberately omit _closure_probe_extra
        }
    )
    with pytest.raises(AssertionError, match="missing"):
        assert_pin_covers_static_closure(
            tmp_path,
            pinned,
            entrypoint="tools.self_improvement_v2.runtime_bridge",
        )
    assert "tools.self_improvement_v2._closure_probe_extra" in closure
    assert "tools.self_improvement_v2" in closure  # package __init__ is in the closure


def test_n1_relative_import_is_visible_to_closure(tmp_path: Path) -> None:
    """Relative imports are static constructs and must enter the closure (NP-2)."""
    pkg = tmp_path / "tools" / "self_improvement_v2"
    pkg.mkdir(parents=True)
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "runtime_bridge.py").write_text(
        "from . import evil_relative\nfrom .evil_relative import MARK\n",
        encoding="utf-8",
    )
    (pkg / "evil_relative.py").write_text("MARK = 1\n", encoding="utf-8")
    closure = compute_static_import_closure(
        tmp_path,
        entrypoint="tools.self_improvement_v2.runtime_bridge",
    )
    assert "tools.self_improvement_v2.evil_relative" in closure
    assert "tools.self_improvement_v2" in closure


def test_n1_negative_underpin_fails_equality() -> None:
    under = list(TRUSTED_MODULE_NAMES)[:-1]
    with pytest.raises(AssertionError, match="missing|extra"):
        assert_pin_covers_static_closure(REPO, under)


def test_n11_reviewed_head_must_equal_live_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(REPO))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, "0" * 40)
    with pytest.raises(TrustedOriginError, match="reviewed HEAD identity mismatch"):
        assert_trusted_code_origin()


def test_n11_matching_head_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    monkeypatch.setenv(ENV_REPOSITORY_ROOT, str(REPO))
    monkeypatch.setenv(ENV_REVIEWED_HEAD, head)
    result = assert_trusted_code_origin()
    assert result["reviewed_git_head"] == head
    assert result["git_head"] == head


def test_launcher_path_starts_worker_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """At least one test must exercise install_launcher → worker, not conftest hand-set env."""
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    digest = compute_verifier_digest(REPO)
    installed = install_launcher(
        repository_root=REPO,
        docker_endpoint="unix:///var/run/docker.sock",
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    sh = Path(installed["launch_worker_sh"])
    # Replace exec with a one-shot health check using the launcher-exported env.
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        source /dev/null
        """
    )
    # Rewrite launcher to run a Python health assert instead of long-lived server.
    text = sh.read_text(encoding="utf-8")
    replacement = textwrap.dedent(
        """\
        python3 - <<'PY'
        import os, sys
        from pathlib import Path
        root = Path(os.environ["SRL_REPOSITORY_ROOT"])
        head = os.environ["SRL_REVIEWED_HEAD"]
        assert root.is_dir(), root
        assert len(head) == 40, head
        sys.path.insert(0, str(root))
        from tools.self_improvement_v2.trusted_origin import assert_trusted_code_origin
        result = assert_trusted_code_origin()
        assert result["reviewed_git_head"] == head
        print("launcher-path-ok", result["reviewed_git_head"])
        PY
        """
    )
    text = text.replace(
        bash_runtime_bridge_exec_line(),
        replacement,
    )
    sh.write_text(text, encoding="utf-8")
    # Clear conftest-style env so only the launcher supplies anchors.
    env = {k: v for k, v in os.environ.items() if k not in {ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD}}
    proc = subprocess.run(["bash", str(sh)], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "launcher-path-ok" in proc.stdout


def test_launcher_wrong_digest_refuses(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    digest = compute_verifier_digest(REPO)
    installed = install_launcher(
        repository_root=REPO,
        docker_endpoint="unix:///var/run/docker.sock",
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    sh = Path(installed["launch_worker_sh"])
    text = sh.read_text(encoding="utf-8")
    sh.write_text(text.replace(digest, "a" * 64), encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(sh)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
    assert "digest mismatch" in (proc.stderr + proc.stdout)


def test_launcher_wrong_head_refuses_after_digest_ok(tmp_path: Path) -> None:
    """Launcher sets wrong HEAD; worker must refuse once digest gate passes."""
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    digest = compute_verifier_digest(REPO)
    installed = install_launcher(
        repository_root=REPO,
        docker_endpoint="unix:///var/run/docker.sock",
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    sh = Path(installed["launch_worker_sh"])
    text = sh.read_text(encoding="utf-8")
    text = text.replace(f"REVIEWED_HEAD='{head}'", "REVIEWED_HEAD='" + ("b" * 40) + "'")
    text = text.replace(
        bash_runtime_bridge_exec_line(),
        "python3 -c 'from tools.self_improvement_v2.trusted_origin import assert_trusted_code_origin; assert_trusted_code_origin()'",
    )
    sh.write_text(text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in {ENV_REPOSITORY_ROOT, ENV_REVIEWED_HEAD}}
    proc = subprocess.run(["bash", str(sh)], capture_output=True, text=True, env=env, cwd=str(REPO))
    assert proc.returncode != 0
    assert "reviewed HEAD identity mismatch" in (proc.stderr + proc.stdout)


def test_host_secret_path_refuses_container_run_secrets() -> None:
    from tools.self_improvement_v2.launcher.paths import (
        assert_host_secret_path,
        default_host_secret_dir,
        is_container_secret_path,
    )
    from tools.self_improvement_v2.runtime_config import (
        DEFAULT_CONSUME_TOKEN_FILE,
        DEFAULT_TOKEN_FILE,
    )

    assert DEFAULT_TOKEN_FILE == "/run/secrets/srl_worker_token"
    assert DEFAULT_CONSUME_TOKEN_FILE == "/run/secrets/srl_topology_consume_token"
    assert is_container_secret_path(DEFAULT_TOKEN_FILE)
    assert is_container_secret_path(DEFAULT_CONSUME_TOKEN_FILE)
    with pytest.raises(ValueError, match="container"):
        assert_host_secret_path(DEFAULT_TOKEN_FILE)
    with pytest.raises(ValueError, match="container"):
        assert_host_secret_path("/run/secrets/srl_topology_consume_token")
    host_dir = default_host_secret_dir()
    assert host_dir.name == "secrets"
    assert "SentinelResearchLab" in str(host_dir)
    assert not is_container_secret_path(host_dir / "srl_worker_token")
    assert_host_secret_path(host_dir / "srl_worker_token")


def test_launcher_scripts_bind_sys_executable_and_dash_p(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    digest = compute_verifier_digest(REPO)
    installed = install_launcher(
        repository_root=REPO,
        docker_endpoint="unix:///var/run/docker.sock",
        reviewed_head=head,
        install_dir=tmp_path / "SentinelResearchLab",
        expected_digest=digest,
    )
    sh = Path(installed["launch_worker_sh"]).read_text(encoding="utf-8")
    ps1 = Path(installed["launch_worker_ps1"]).read_text(encoding="utf-8")
    exe = str(Path(__import__("sys").executable).resolve())
    assert exe in sh
    assert "-P -m tools.self_improvement_v2.runtime_bridge" in sh
    assert "exec python3 -m" not in sh
    assert exe in ps1 or exe.replace("\\", "/") in ps1.replace("\\", "/")
    assert "-P -m tools.self_improvement_v2.runtime_bridge" in ps1
    assert (tmp_path / "SentinelResearchLab" / "secrets").is_dir()
