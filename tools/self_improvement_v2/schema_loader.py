"""JSON Schema loading and validation for Self-Improvement Loop V2 contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from tools.self_improvement_v2.models import ERROR_CODES, SCHEMA_VERSION, WorkerError

SPEC_REL = Path("specs/self_improvement/v2")

SCHEMA_FILES = {
    "candidate": "improvement_candidate.schema.json",
    "proposal": "implementation_proposal.schema.json",
    "execution_bundle": "execution_bundle.schema.json",
    "review_result": "review_result.schema.json",
    "finalization_result": "finalization_result.schema.json",
    "learning_record": "learning_record.schema.json",
    "agent_runtime_contract": "agent_runtime_contract.schema.json",
}


def worker_package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def specs_dir(root: Path | None = None) -> Path:
    base = root if root is not None else worker_package_root()
    return (base / SPEC_REL).resolve()


@lru_cache(maxsize=16)
def _load_schema_cached(schema_path: str) -> dict[str, Any]:
    path = Path(schema_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], f"not Draft 2020-12: {path.name}")
    if data.get("additionalProperties") is not False:
        raise WorkerError(
            ERROR_CODES["SCHEMA_INVALID"],
            f"additionalProperties must be false: {path.name}",
        )
    return data


def load_schema(name: str, root: Path | None = None) -> dict[str, Any]:
    if name not in SCHEMA_FILES:
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], f"unknown schema: {name}")
    path = specs_dir(root) / SCHEMA_FILES[name]
    if not path.is_file():
        path = specs_dir(worker_package_root()) / SCHEMA_FILES[name]
    return _load_schema_cached(str(path.resolve()))


def validate_instance(name: str, instance: dict[str, Any], root: Path | None = None) -> None:
    schema = load_schema(name, root=root)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        first: ValidationError = errors[0]
        path = "/".join(str(p) for p in first.path) or "<root>"
        raise WorkerError(
            ERROR_CODES["SCHEMA_INVALID"],
            f"{name} invalid at {path}: {first.message}",
            state="POLICY_REJECTED",
        )


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WorkerError(ERROR_CODES["SCHEMA_INVALID"], f"expected object: {path.name}")
    return data


def ensure_schema_version(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.setdefault("schema_version", SCHEMA_VERSION)
    return out


def load_policy_dict(root: Path | None = None) -> dict[str, Any]:
    base = root if root is not None else worker_package_root()
    path = (base / SPEC_REL / "policy.json").resolve()
    if not path.is_file():
        path = (worker_package_root() / SPEC_REL / "policy.json").resolve()
    return json.loads(path.read_text(encoding="utf-8"))
