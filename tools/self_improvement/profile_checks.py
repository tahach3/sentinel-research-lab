"""Fixed allowlisted validation profile entrypoints (no proposal-driven code)."""

from __future__ import annotations

import argparse
import compileall
import os
import subprocess
import sys
from pathlib import Path


def _target_root() -> Path:
    env = os.environ.get("SRL_SELF_IMPROVEMENT_TARGET_ROOT")
    return Path(env).resolve() if env else Path.cwd().resolve()


def _worker_root() -> Path:
    env = os.environ.get("SRL_SELF_IMPROVEMENT_WORKER_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def documentation_only() -> int:
    root = _target_root()
    docs = list((root / "docs").rglob("*.md")) if (root / "docs").is_dir() else []
    if not docs:
        print("FAIL: no documentation markdown files", file=sys.stderr)
        return 1
    for path in docs:
        path.read_text(encoding="utf-8")
    print(f"docs_ok {len(docs)}")
    return 0


def python_tooling() -> int:
    root = _target_root()
    target = root / "tools" / "self_improvement"
    if not target.is_dir():
        # Fall back to worker package when target is a thin temp fixture repo.
        target = _worker_root() / "tools" / "self_improvement"
    ok = compileall.compile_dir(str(target), quiet=1)
    print("python_tooling_ok" if ok else "python_tooling_fail")
    return 0 if ok else 1


def self_improvement_tests() -> int:
    worker = _worker_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(worker)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/self_improvement",
            "-q",
            "--tb=line",
        ],
        cwd=str(worker),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        shell=False,
        env=env,
    )
    sys.stdout.write(proc.stdout[-4000:])
    sys.stderr.write(proc.stderr[-4000:])
    return proc.returncode


def workflow_design_static() -> int:
    worker = _worker_root()
    workflow = worker / "workflows" / "design" / "self_improvement_loop_v1.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(worker)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.self_improvement.workflow_validator",
            "--root",
            str(worker),
            "--workflow",
            str(workflow),
        ],
        cwd=str(worker),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        shell=False,
        env=env,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


HANDLERS = {
    "documentation_only": documentation_only,
    "python_tooling": python_tooling,
    "self_improvement_tests": self_improvement_tests,
    "workflow_design_static": workflow_design_static,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-improvement validation profile checks")
    parser.add_argument("profile_check", choices=sorted(HANDLERS.keys()))
    args = parser.parse_args(argv)
    return HANDLERS[args.profile_check]()


if __name__ == "__main__":
    raise SystemExit(main())
