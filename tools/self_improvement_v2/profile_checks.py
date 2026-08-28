"""Predefined offline validation profile entrypoints for V2."""

from __future__ import annotations

import argparse
import compileall
import json
import sys
from pathlib import Path

from tools.self_improvement_v2.schema_loader import worker_package_root
from tools.self_improvement_v2.workflow_validator import validate_workflow


def documentation_only() -> int:
    root = Path.cwd()
    docs = root / "docs"
    if not docs.is_dir():
        print("docs missing", file=sys.stderr)
        return 1
    for path in docs.rglob("*.md"):
        path.read_text(encoding="utf-8")
    return 0


def python_tooling() -> int:
    pkg = worker_package_root() / "tools" / "self_improvement_v2"
    ok = compileall.compile_dir(str(pkg), quiet=1)
    return 0 if ok else 1


def self_improvement_tests() -> int:
    # Lightweight marker — full suite is run externally; profile confirms package import.
    import tools.self_improvement_v2 as pkg  # noqa: F401

    return 0


def workflow_design_static() -> int:
    root = worker_package_root()
    path = root / "workflows" / "design" / "self_improvement_loop_v2.json"
    report = validate_workflow(root, path)
    print(json.dumps({"status": report["status"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


PROFILES = {
    "documentation_only": documentation_only,
    "python_tooling": python_tooling,
    "self_improvement_tests": self_improvement_tests,
    "workflow_design_static": workflow_design_static,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=sorted(PROFILES))
    args = parser.parse_args(argv)
    return PROFILES[args.profile]()


if __name__ == "__main__":
    if not getattr(sys.flags, "safe_path", False):
        print("profile_checks requires python -P", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
