import os
from pathlib import Path

from tools.self_improvement_v2.validation_runner import sanitized_environ


def test_sanitized_env_no_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "C:\\Windows"))
    env = sanitized_environ(pythonpath="X")
    assert "OPENAI_API_KEY" not in env
    assert "DATABASE_URL" not in env
    assert env["PYTHONPATH"] == "X"
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
