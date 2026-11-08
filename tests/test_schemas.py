import json
import unittest

from jsonschema import Draft202012Validator

from turbo.pipeline_paths import ROOT
from turbo.universe.graph import (
    EVENT_TYPES,
    IDENTITY_DIMENSIONS,
    MARKET_VERSION_FIELDS,
    RELATIONSHIP_TYPES,
    validate_event,
)
from turbo.universe.multisource import reconcile
from tests.test_graph import creation, event


class SchemaParityTest(unittest.TestCase):
    def load(self, name: str) -> dict[str, object]:
        return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

    def test_source_record_schema_matches_generated_contract(self) -> None:
        schema = self.load("source-record.schema.json")
        generated = reconcile()["source_records"]
        self.assertEqual(set(schema["required"]), set(generated[0]))
        self.assertFalse(schema["additionalProperties"])
        validator = Draft202012Validator(schema)
        errors = [
            error.message
            for record in generated
            for error in validator.iter_errors(record)
        ]
        self.assertEqual(errors, [])

    def test_event_schema_enums_and_market_version_match_runtime(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        properties = schema["properties"]
        self.assertEqual(set(properties["event_type"]["enum"]), EVENT_TYPES)
        self.assertEqual(
            {item for item in properties["relationship_type"]["enum"] if item is not None},
            RELATIONSHIP_TYPES,
        )
        self.assertEqual(
            set(schema["$defs"]["operatingIdentity"]["required"]),
            IDENTITY_DIMENSIONS,
        )
        self.assertEqual(
            set(schema["$defs"]["marketVersion"]["required"]),
            MARKET_VERSION_FIELDS,
        )

    def test_runtime_and_json_schema_share_event_fixtures(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        validator = Draft202012Validator(
            schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        valid = creation("create-valid", "2026-11-08T12:00:00Z")
        self.assertEqual(list(validator.iter_errors(valid)), [])
        self.assertEqual(validate_event(valid), [])

        invalid_map = event(
            "map-invalid",
            "2026-11-08T12:00:00Z",
            input_market_ids=["market:invalid"],
        )
        self.assertNotEqual(list(validator.iter_errors(invalid_map)), [])
        self.assertNotEqual(validate_event(invalid_map), [])

        invalid_review = event("review-invalid", "2026-11-08T12:00:00Z")
        invalid_review["review"]["proposer"] = 7
        self.assertNotEqual(list(validator.iter_errors(invalid_review)), [])
        self.assertNotEqual(validate_event(invalid_review), [])


if __name__ == "__main__":
    unittest.main()
