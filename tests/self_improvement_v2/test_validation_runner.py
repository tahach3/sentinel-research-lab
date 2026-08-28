import json
import os
import subprocess
import sys
from pathlib import Path

from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.validation_runner import (
    bind_python_argv,
    run_validation_profile,
    sanitized_environ,
)


REPO = Path(__file__).resolve().parents[2]


def test_sanitized_env_no_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "C:\\Windows"))
    env = sanitized_environ(pythonpath="X")
    assert "OPENAI_API_KEY" not in env
    assert "DATABASE_URL" not in env
    assert env["PYTHONPATH"] == "X"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONSAFEPATH"] == "1"
    import ast

    tree = ast.parse(Path("tools/self_improvement_v2/validation_runner.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "copy":
            val = node.func.value
            assert not (
                isinstance(val, ast.Attribute)
                and val.attr == "environ"
                and isinstance(val.value, ast.Name)
                and val.value.id == "os"
            )


def test_bind_python_argv_uses_sys_executable_and_dash_p() -> None:
    argv = bind_python_argv(
        ["python", "-m", "tools.self_improvement_v2.profile_checks", "python_tooling"]
    )
    assert argv[0] == sys.executable
    assert "-P" in argv
    assert argv[1] == "-P"
    assert "python" not in argv[0].lower() or argv[0] == sys.executable
    assert argv[argv.index("-m") + 1] == "tools.self_improvement_v2.profile_checks"


def test_run_validation_profile_launches_sys_executable_dash_p(monkeypatch) -> None:
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        recorded.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    policy = json.loads((REPO / "specs/self_improvement/v2/policy.json").read_text(encoding="utf-8"))
    run_validation_profile(policy=policy, profile_name="PYTHON_TOOLING", cwd=REPO)
    assert recorded
    launched = recorded[0]
    assert launched[0] == sys.executable
    assert "-P" in launched
    assert launched[1] == "-P"
    assert "tools.self_improvement_v2.profile_checks" in launched


def test_profile_checks_user_site_cannot_override(tmp_path: Path) -> None:
    """usercustomize in PYTHONUSERBASE must not change profile_checks under -P/-s."""
    env_probe = {k: v for k, v in os.environ.items() if k not in {"PYTHONNOUSERSITE", "PYTHONSAFEPATH"}}
    env_probe["PYTHONUSERBASE"] = str(tmp_path / "pybase")
    probe = subprocess.run(
        [sys.executable, "-c", "import site; print(site.getusersitepackages())"],
        env=env_probe,
        capture_output=True,
        text=True,
        check=True,
    )
    usersite = Path(probe.stdout.strip())
    usersite.mkdir(parents=True, exist_ok=True)
    (usersite / "usercustomize.py").write_text("raise SystemExit('usersite-hijack')\n", encoding="utf-8")

    hijack_env = dict(env_probe)
    hijack = subprocess.run(
        [sys.executable, "-c", "print('reachable')"],
        env=hijack_env,
        capture_output=True,
        text=True,
    )
    assert hijack.returncode != 0
    assert "usersite-hijack" in (hijack.stderr + hijack.stdout)

    isolated_env = sanitized_environ(pythonpath=str(worker_package_root()))
    isolated_env["PYTHONUSERBASE"] = env_probe["PYTHONUSERBASE"]
    isolated = subprocess.run(
        bind_python_argv(
            ["python", "-m", "tools.self_improvement_v2.profile_checks", "python_tooling"]
        ),
        cwd=str(REPO),
        env=isolated_env,
        capture_output=True,
        text=True,
    )
    assert isolated.returncode == 0, isolated.stdout + isolated.stderr
    assert "usersite-hijack" not in (isolated.stdout + isolated.stderr)
