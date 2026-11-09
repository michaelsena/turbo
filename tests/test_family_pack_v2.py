import json
import tempfile
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import (
    compile_family_evidence_pack_v2,
    dry_run_family_preparation_v2,
    generate_family_config_v2,
    prepare_family_v2,
    validate_family_evidence_pack_v2,
    validate_family_preparation_v2,
)


UNLINKED_FAMILY = "family:coverage:napcs-collection:10:001"
NAICS_FAMILY = "family:naics-2022:111110"
CANDIDATE_FAMILY = "family:coverage:prior-candidate:global-challenger:001"


class FamilyPackV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = generate_family_config_v2(UNLINKED_FAMILY)
        cls.pack = compile_family_evidence_pack_v2(cls.config)

    def test_config_binds_exact_corrected_schedule_and_graph(self) -> None:
        self.assertEqual(
            self.config["schedule_binding"]["partition_id"],
            "family-partition:60517981ab96e7f243c7033e",
        )
        self.assertEqual(self.config["family_kind"], "unlinked_collection_coverage_challenge")
        self.assertFalse(self.config["model_invoked"])
        self.assertEqual(self.config["expected_counts"]["required_identities"], 1)
        self.assertEqual(self.config["expected_counts"]["context_identities"], 6)
        self.assertEqual(self.config["expected_counts"]["context_edges"], 11)

    def test_pack_keeps_context_separate_and_uses_edge_ledger(self) -> None:
        scope = self.pack["scope"]
        self.assertFalse(
            set(scope["required_disposition_identity_ids"])
            & set(scope["context_only_identity_ids"])
        )
        self.assertEqual(len(self.pack["identity_cards"]), 7)
        self.assertEqual(len(self.pack["mapping_cards"]), 1)
        self.assertEqual(len(self.pack["context_edges"]), 11)
        self.assertTrue(
            all(edge["relationship_id"].startswith("relationship:") for edge in self.pack["context_edges"])
        )
        self.assertEqual(validate_family_evidence_pack_v2(self.pack, self.config), [])

    def test_all_schedulable_family_kinds_compile(self) -> None:
        for family_id, expected_kind in (
            (NAICS_FAMILY, "naics_leaf_anchor"),
            (UNLINKED_FAMILY, "unlinked_collection_coverage_challenge"),
            (CANDIDATE_FAMILY, "global_prior_candidate_challenge"),
        ):
            with self.subTest(family_id=family_id):
                result = dry_run_family_preparation_v2(family_id)
                self.assertTrue(result["valid"])
                self.assertEqual(result["family_kind"], expected_kind)
                self.assertFalse(result["model_invoked"])
                self.assertFalse(result["persisted"])
                if expected_kind == "global_prior_candidate_challenge":
                    self.assertEqual(result["counts"]["required_candidates"], 58)
                    self.assertEqual(result["counts"]["source_record_cards"], 58)

    def test_schedule_pointer_hash_tampering_fails_closed(self) -> None:
        pointer = json.loads(
            (ROOT / "data/generated/latest-family-schedule.json").read_text(encoding="utf-8")
        )
        pointer["receipt_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "pointer.json"
            path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt hash mismatch"):
                generate_family_config_v2(UNLINKED_FAMILY, pointer_path=path)

    def test_count_and_size_gates_fail_closed_without_truncation(self) -> None:
        with self.assertRaisesRegex(ValueError, "context_edges"):
            generate_family_config_v2(
                UNLINKED_FAMILY,
                limits={"max_context_edges": 1},
            )
        small = generate_family_config_v2(
            UNLINKED_FAMILY,
            limits={"max_pack_bytes": 1024},
        )
        with self.assertRaisesRegex(ValueError, "byte-size limit"):
            compile_family_evidence_pack_v2(small)

    def test_persisted_preparation_replays_and_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output_root = Path(raw) / "preparations"
            result = prepare_family_v2(UNLINKED_FAMILY, output_root=output_root)
            preparation_dir = Path(result["preparation_path"])
            valid = validate_family_preparation_v2(preparation_dir)
            self.assertTrue(valid["valid"], valid["errors"])
            pack_path = preparation_dir / "family-evidence-pack-v2.json"
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            pack["metadata"]["family_kind"] = "tampered"
            pack_path.write_text(json.dumps(pack), encoding="utf-8")
            invalid = validate_family_preparation_v2(preparation_dir)
            self.assertFalse(invalid["valid"])
            self.assertIn(
                "persisted pack does not match deterministic regeneration",
                invalid["errors"],
            )


if __name__ == "__main__":
    unittest.main()
