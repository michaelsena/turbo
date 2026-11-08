import json
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.graph import (
    EVENT_TYPES,
    IDENTITY_DIMENSIONS,
    MARKET_VERSION_FIELDS,
    RELATIONSHIP_TYPES,
)
from turbo.universe.multisource import reconcile


class SchemaParityTest(unittest.TestCase):
    def load(self, name: str) -> dict[str, object]:
        return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

    def test_source_record_schema_matches_generated_contract(self) -> None:
        schema = self.load("source-record.schema.json")
        generated = reconcile()["source_records"][0]
        self.assertEqual(set(schema["required"]), set(generated))
        self.assertFalse(schema["additionalProperties"])

    def test_event_schema_enums_and_market_version_match_runtime(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        properties = schema["properties"]
        self.assertEqual(set(properties["event_type"]["enum"]), EVENT_TYPES)
        self.assertEqual(
            set(properties["relationship_type"]["enum"]),
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


if __name__ == "__main__":
    unittest.main()
