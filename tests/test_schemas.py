import json
import unittest

from jsonschema import Draft202012Validator

from turbo.pipeline_paths import ROOT
from turbo.universe.graph import (
    EVENT_TYPES,
    IDENTITY_DIMENSIONS,
    MARKET_VERSION_FIELDS,
    RELATIONSHIP_TYPES,
    market_id_from_creation,
    validate_event,
)
from turbo.universe.multisource import reconcile
from tests.test_graph import creation, event, market_version


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

    def test_runtime_and_schema_reject_duplicate_or_blank_string_arrays(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        validator = Draft202012Validator(schema)
        market_fields = (
            "aliases",
            "explicit_exclusions",
            "source_record_ids",
            "mapping_event_ids",
            "candidate_market_ids",
        )
        for field in market_fields:
            for invalid_values in (["duplicate", "duplicate"], [" "]):
                candidate = creation(f"market-{field}-{len(invalid_values)}", "2026-11-08T12:00:00Z")
                candidate["market_version"][field] = invalid_values
                with self.subTest(scope="market_version", field=field, values=invalid_values):
                    self.assertNotEqual(list(validator.iter_errors(candidate)), [])
                    self.assertNotEqual(validate_event(candidate), [])

    def test_runtime_and_schema_reject_the_same_invalid_scalar_types(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        validator = Draft202012Validator(
            schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        fixtures: list[tuple[str, dict[str, object]]] = []

        invalid_event_id = creation("invalid-event-id", "2026-11-08T12:00:00Z")
        invalid_event_id["event_id"] = 7
        fixtures.append(("event_id", invalid_event_id))

        invalid_recorded_at = event("invalid-recorded-at", "2026-11-08T12:00:00Z")
        invalid_recorded_at["recorded_at"] = 7
        fixtures.append(("recorded_at", invalid_recorded_at))

        invalid_result = event("invalid-result", "2026-11-08T12:00:00Z")
        invalid_result["operating_identity"]["buyer"]["result"] = 7
        fixtures.append(("identity_result", invalid_result))

        invalid_identity_confidence = event(
            "invalid-identity-confidence", "2026-11-08T12:00:00Z"
        )
        invalid_identity_confidence["operating_identity"]["buyer"]["confidence"] = True
        fixtures.append(("identity_confidence", invalid_identity_confidence))

        invalid_market_confidence = creation(
            "invalid-market-confidence", "2026-11-08T12:00:00Z"
        )
        invalid_market_confidence["market_version"]["confidence_by_dimension"][
            "buyer"
        ] = True
        fixtures.append(("market_confidence", invalid_market_confidence))

        invalid_parent = creation("invalid-parent", "2026-11-08T12:00:00Z")
        invalid_parent["market_version"]["parent_market_id"] = "not-a-market-id"
        fixtures.append(("parent_market_id", invalid_parent))

        blank_name = creation("blank-market-name", "2026-11-08T12:00:00Z")
        blank_name["market_version"]["canonical_name"] = " "
        fixtures.append(("blank_market_name", blank_name))

        blank_reviewer = event("blank-reviewer", "2026-11-08T12:00:00Z")
        blank_reviewer["review"]["independent_reviewer"] = " "
        fixtures.append(("blank_reviewer", blank_reviewer))

        for name, candidate in fixtures:
            with self.subTest(name=name):
                self.assertNotEqual(list(validator.iter_errors(candidate)), [])
                self.assertNotEqual(validate_event(candidate), [])

    def test_runtime_and_schema_share_multiline_and_timestamp_domains(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        validator = Draft202012Validator(
            schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

        multiline_event = event("event\nmultiline", "2026-11-08T12:00:00Z")
        multiline_event["review"]["independent_reviewer"] = "reviewer\nsecond-line"
        self.assertEqual(list(validator.iter_errors(multiline_event)), [])
        self.assertEqual(validate_event(multiline_event), [])

        multiline_market = creation("multiline-market", "2026-11-08T12:00:00Z")
        multiline_market["market_version"]["canonical_name"] = "Market\nname"
        multiline_market["market_version"]["definition"] = "Line one\nline two"
        multiline_market["market_version"]["boundary"] = "Included\nExcluded"
        self.assertEqual(list(validator.iter_errors(multiline_market)), [])
        self.assertEqual(validate_event(multiline_market), [])

        for invalid_timestamp in (
            "2026-11-08t12:00:00z",
            "2016-12-31T23:59:60Z",
            "2026-11-08T12:00:00+00:00",
        ):
            candidate = event("invalid-time-domain", "2026-11-08T12:00:00Z")
            candidate["recorded_at"] = invalid_timestamp
            with self.subTest(recorded_at=invalid_timestamp):
                self.assertNotEqual(list(validator.iter_errors(candidate)), [])
                self.assertNotEqual(validate_event(candidate), [])

        event_fields = (
            "input_source_record_ids",
            "input_market_ids",
            "input_candidate_market_ids",
            "output_market_ids",
            "supporting_record_ids",
            "counterevidence_record_ids",
            "supersedes",
            "supersedes_market_version_ids",
        )
        for field in event_fields:
            for invalid_values in (["duplicate", "duplicate"], [" "]):
                candidate = event(
                    f"event-{field}-{len(invalid_values)}",
                    "2026-11-08T12:00:00Z",
                )
                candidate[field] = invalid_values
                with self.subTest(scope="event", field=field, values=invalid_values):
                    self.assertNotEqual(list(validator.iter_errors(candidate)), [])
                    self.assertNotEqual(validate_event(candidate), [])

    def test_cross_field_parity_boundary_is_explicit_and_runtime_enforced(self) -> None:
        schema = self.load("reconciliation-event.schema.json")
        validator = Draft202012Validator(schema)
        self.assertIn("Cross-field identity invariants", schema["$comment"])

        split_id = "split-cross-field"
        outputs = [market_id_from_creation(split_id, index) for index in range(2)]
        split = event(
            split_id,
            "2026-11-08T12:00:00Z",
            event_type="split",
            input_source_record_ids=[],
            input_market_ids=["market:111111111111111111111111"],
            output_market_ids=outputs,
            relationship_type=None,
            market_versions=[
                market_version(split_id, output, f"Successor {index}")
                for index, output in enumerate(outputs, 1)
            ],
        )
        split["market_versions"].append(
            market_version(split_id, outputs[0], "Extra version")
        )
        self.assertEqual(list(validator.iter_errors(split)), [])
        self.assertIn(
            "split requires one market version per output",
            validate_event(split),
        )

        original = creation("rename-source", "2026-11-08T11:00:00Z")
        input_market_id = original["output_market_ids"][0]
        output_market_id = market_id_from_creation("rename-different-output")
        rename = event(
            "rename-cross-field",
            "2026-11-08T12:00:00Z",
            event_type="rename",
            input_source_record_ids=[],
            input_market_ids=[input_market_id],
            output_market_ids=[output_market_id],
            relationship_type=None,
            supersedes_market_version_ids=[
                original["market_version"]["market_version_id"]
            ],
            market_version=market_version(
                "rename-cross-field", output_market_id, "Renamed market"
            ),
        )
        self.assertEqual(list(validator.iter_errors(rename)), [])
        self.assertIn(
            "rename must preserve exactly one market ID",
            validate_event(rename),
        )


if __name__ == "__main__":
    unittest.main()
