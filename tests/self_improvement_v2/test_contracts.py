from jsonschema import Draft202012Validator

from tools.self_improvement_v2.schema_loader import SCHEMA_FILES, load_schema


def test_all_schemas_draft_and_strict():
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        assert schema["$schema"].endswith("draft/2020-12/schema")
        assert schema.get("additionalProperties") is False
        Draft202012Validator.check_schema(schema)
