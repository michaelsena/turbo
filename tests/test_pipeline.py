import gzip
import json
import unittest
from unittest.mock import patch

from turbo.pipeline import RUNS, run, validate_manifest_metadata


class PipelineTest(unittest.TestCase):
    def test_manifest_metadata_requires_nonempty_utc_governance_fields(self) -> None:
        manifest = {
            "acquired_at": "2026-11-08T12:00:00",
            "dataset_id": "dataset",
            "file": "source.zip",
            "publisher": "",
            "reuse": "public",
            "role": "evidence",
            "sha256": "not-a-hash",
            "source_url": "http://example.com",
        }
        errors = validate_manifest_metadata(manifest, "test.snapshot.json")
        self.assertTrue(any("publisher" in error for error in errors))
        self.assertTrue(any("must be UTC" in error for error in errors))
        self.assertTrue(any("invalid sha256" in error for error in errors))
        self.assertTrue(any("must use https" in error for error in errors))

    def test_run_fails_closed_when_source_validation_fails(self) -> None:
        with patch("turbo.pipeline.validate", return_value=["tampered NAPCS snapshot"]):
            with self.assertRaisesRegex(ValueError, "tampered NAPCS snapshot"):
                run()

    def test_replay_reuses_same_immutable_run(self) -> None:
        first = run()
        receipt = RUNS / first["run_id"] / "run-receipt.json"
        before = receipt.read_bytes()
        second = run()
        after = receipt.read_bytes()
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(before, after)
        self.assertEqual(first["canonical_markets"], 0)
        self.assertEqual(first["research_scores"], 0)
        self.assertGreaterEqual(first["governed_source_snapshots"], 8)
        self.assertEqual(first["identity_source_counts"]["collection_to_trilateral_rows"], 3_520)
        for artifact in first["output_hashes"]:
            self.assertTrue(artifact.endswith(".json.gz"))
            payload = gzip.decompress((RUNS / first["run_id"] / artifact).read_bytes())
            self.assertIsInstance(json.loads(payload), dict)


if __name__ == "__main__":
    unittest.main()

