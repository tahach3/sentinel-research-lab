"""Schema contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.self_improvement.schema_loader import SCHEMA_FILES, load_schema, validate_instance
from tools.self_improvement.models import WorkerError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_schemas_are_draft_2020_12_and_strict() -> None:
    for name in SCHEMA_FILES:
        schema = load_schema(name, root=ROOT)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema.get("additionalProperties") is False
        Draft202012Validator.check_schema(schema)


def test_fixture_candidate_and_review_validate() -> None:
    candidate = json.loads((FIXTURES / "candidate.json").read_text(encoding="utf-8"))
    review = json.loads((FIXTURES / "review_pass.json").read_text(encoding="utf-8"))
    validate_instance("candidate", candidate, root=ROOT)
    validate_instance("review_result", review, root=ROOT)


def test_unknown_field_rejected() -> None:
    candidate = json.loads((FIXTURES / "candidate.json").read_text(encoding="utf-8"))
    candidate["extra_field"] = "nope"
    with pytest.raises(WorkerError) as exc:
        validate_instance("candidate", candidate, root=ROOT)
    assert exc.value.code == "SCHEMA_INVALID"
