"""Concordance-only source records retain their original observation identity."""
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2, validate_family_preparation_v2


class FamilyPackObservationIdsTest(unittest.TestCase):
    def test_concordance_only_family_prepares_and_replays_original_records(self):
        expected = {
            "source-observation:census-napcs-2022-collection-to-trilateral:data-sheet:931:collection-label",
            "source-observation:census-napcs-2022-trilateral-to-collection:data-sheet:248:collection-label",
        }
        with tempfile.TemporaryDirectory() as raw:
            result = prepare_family_v2("family:coverage:napcs-collection:20:001", output_root=Path(raw))
            directory = Path(result["preparation_path"])
            pack = json.loads((directory / "family-evidence-pack-v2.json").read_text())
            records = {card["record_id"]: card for card in pack["source_record_cards"]}
            self.assertTrue(expected <= records.keys())
            for record_id in expected:
                self.assertEqual(records[record_id]["record_kind"], "concordance_product")
                self.assertIn("field:collection_description", records[record_id]["locator"])
            replay = validate_family_preparation_v2(directory)
            self.assertTrue(replay["valid"], replay["errors"])

    def test_observation_namespace_accepts_only_supported_concordance_ids(self):
        schema = json.loads((ROOT / "schemas/family-evidence-pack-v2.schema.json").read_text())
        validator = Draft202012Validator(schema["$defs"]["sourceRecordCard"]["properties"]["record_id"])
        for record_id in (
            "source-row:existing-record:1",
            "source-observation:census-napcs-2022-collection-to-trilateral:data-sheet:931:collection-label",
            "source-observation:census-napcs-2022-trilateral-to-collection:data-sheet:248:trilateral-label",
        ):
            with self.subTest(record_id=record_id):
                self.assertEqual(list(validator.iter_errors(record_id)), [])
        for record_id in (
            "source-observation:unrecognized:1",
            "source-observation:census-napcs-2022-collection-to-trilateral:data-sheet:0:collection-label",
            "source-observation:census-napcs-2022-collection-to-trilateral:data-sheet:931:invented-label",
            "source-observation:census-napcs-2022-collection-to-trilateral:data-sheet:931:collection-label:extra",
            "source-row:",
        ):
            with self.subTest(record_id=record_id):
                self.assertTrue(list(validator.iter_errors(record_id)))


if __name__ == "__main__":
    unittest.main()
