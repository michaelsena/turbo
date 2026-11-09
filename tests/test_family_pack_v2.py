import copy
import gzip
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import (
    _load_run_artifact,
    _pack_hash,
    _verified_graph,
    compile_family_evidence_pack_v2,
    dry_run_family_preparation_v2,
    generate_family_config_v2,
    prepare_family_v2,
    validate_family_evidence_pack_v2,
    validate_family_preparation_v2,
)
from turbo.agents.boundary_harness import canonical_sha256


UNLINKED_FAMILY = "family:coverage:napcs-collection:10:001"
NAICS_FAMILY = "family:naics-2022:111110"
CANDIDATE_FAMILY = "family:coverage:prior-candidate:global-challenger:001"


class FamilyPackV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = generate_family_config_v2(UNLINKED_FAMILY)
        cls.pack = compile_family_evidence_pack_v2(cls.config)

    def test_required_naics_retains_manual_boundary_and_index_evidence(self) -> None:
        config = generate_family_config_v2(NAICS_FAMILY)
        pack = compile_family_evidence_pack_v2(config)
        definitions = pack["manual_definitions"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["identity_id"], "identity:naics:111110")
        self.assertIn("soybeans", definitions[0]["narrative_text"].lower())
        self.assertIn("111191", definitions[0]["cross_references_text"])
        self.assertTrue(definitions[0]["snapshot_id"])
        self.assertTrue(definitions[0]["locator"])
        self.assertEqual(pack["counts"]["manual_index_entries"], 1)
        self.assertIn("naics-identity-evidence.json.gz", pack["metadata"]["source_artifact_hashes"])
        tampered = copy.deepcopy(pack)
        tampered["manual_definitions"][0]["cross_references_text"] = ""
        tampered["metadata"]["pack_sha256"] = _pack_hash(tampered)
        self.assertTrue(validate_family_evidence_pack_v2(tampered, config))

    def test_retrieved_nonowned_candidates_remain_context_only(self) -> None:
        required = self.pack["scope"]["required_prior_candidate_ids"]
        context = self.pack["context_candidate_cards"]
        self.assertEqual(required, [])
        self.assertEqual(len(context), 5)
        retrieved = {candidate_id for card in self.pack["mapping_cards"]
                     for candidate_id in card["retrieved_candidate_ids"]}
        self.assertEqual(retrieved, {card["candidate_market_id"] for card in context})
        records = {card["record_id"] for card in self.pack["source_record_cards"]}
        self.assertTrue(all(set(card["source_record_ids"]) <= records for card in context))
        tampered = copy.deepcopy(self.pack)
        tampered["context_candidate_cards"] = []
        tampered["metadata"]["pack_sha256"] = _pack_hash(tampered)
        self.assertTrue(validate_family_evidence_pack_v2(tampered, self.config))

    def test_implementation_and_schema_bytes_are_bound(self) -> None:
        hashes = self.config["implementation_hashes"]
        for path in ("src/turbo/universe/family_pack_v2.py",
                     "schemas/family-config-v2.schema.json",
                     "schemas/family-evidence-pack-v2.schema.json"):
            self.assertEqual(hashes[path], hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        self.assertEqual(self.pack["metadata"]["implementation_hashes"], hashes)
        tampered = copy.deepcopy(self.config)
        tampered["implementation_hashes"]["src/turbo/universe/family_pack_v2.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact schedule entry"):
            compile_family_evidence_pack_v2(tampered)

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

    def test_graph_projection_is_bound_to_receipt_and_internal_counts(self) -> None:
        def copied_graph_root(raw: str) -> tuple[Path, Path, Path, Path]:
            root = Path(raw) / "root"
            generated = root / "data/generated"
            generated.mkdir(parents=True)
            source_pointer = json.loads(
                (ROOT / "data/generated/latest-graph.json").read_text(encoding="utf-8")
            )
            release_dir = root / source_pointer["release_path"]
            release_dir.parent.mkdir(parents=True)
            shutil.copytree(ROOT / source_pointer["release_path"], release_dir)
            pointer_path = generated / "latest-graph.json"
            pointer_path.write_text(json.dumps(source_pointer), encoding="utf-8")
            return root, pointer_path, release_dir / "graph-receipt.json", release_dir / "projection.json"

        with tempfile.TemporaryDirectory() as raw:
            root, pointer_path, _, projection_path = copied_graph_root(raw)
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            projection = json.loads(projection_path.read_text(encoding="utf-8"))
            projection["graph_version_id"] = "graph-tampered"
            projection_path.write_text(json.dumps(projection), encoding="utf-8")
            pointer["projection_sha256"] = canonical_sha256(projection)
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt does not bind"):
                _verified_graph(root=root)

        with tempfile.TemporaryDirectory() as raw:
            root, pointer_path, receipt_path, _ = copied_graph_root(raw)
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["counts"]["canonical_markets"] = 0
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            pointer["receipt_sha256"] = canonical_sha256(receipt)
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "counts do not match"):
                _verified_graph(root=root)

        with tempfile.TemporaryDirectory() as raw:
            root, pointer_path, _, _ = copied_graph_root(raw)
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["source_universe_run_id"] = "run-00000000000000000000"
            pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_universe_run_id mismatch"):
                _verified_graph(root=root)

    def test_schedule_source_hash_rejects_candidate_and_raw_evidence_tampering(self) -> None:
        run_id = self.config["schedule_binding"]["source_run_id"]
        name = "multisource-reconciliation.json.gz"
        source_path = ROOT / "data/runs" / run_id / name
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            original = json.load(handle)
        run_receipt = json.loads(
            (ROOT / "data/runs" / run_id / "run-receipt.json").read_text(encoding="utf-8")
        )
        schedule_receipt = json.loads(
            (
                ROOT
                / "data/family_schedules/family-partition:60517981ab96e7f243c7033e/schedule-receipt.json"
            ).read_text(encoding="utf-8")
        )
        for label, mutate in (
            ("candidate", lambda value: value["candidate_markets"][0].update(name="tampered candidate")),
            ("raw evidence", lambda value: value["source_records"][0].update(raw_label="tampered raw label")),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                run_dir = root / "data/runs" / run_id
                run_dir.mkdir(parents=True)
                tampered = copy.deepcopy(original)
                mutate(tampered)
                payload = gzip.compress(
                    (json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                    compresslevel=9,
                    mtime=0,
                )
                (run_dir / name).write_bytes(payload)
                changed_receipt = copy.deepcopy(run_receipt)
                changed_receipt["output_hashes"][name] = hashlib.sha256(payload).hexdigest()
                with self.assertRaisesRegex(ValueError, "run/schedule hash disagreement"):
                    _load_run_artifact(
                        root,
                        run_id,
                        changed_receipt,
                        schedule_receipt["source_hashes"],
                        name,
                    )

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

    def test_standalone_pack_validation_rejects_completeness_tampering(self) -> None:
        mutations = {
            "context set": lambda pack: pack["scope"]["context_only_identity_ids"].pop(),
            "identity cards": lambda pack: pack["identity_cards"].pop(),
            "source record cards": lambda pack: pack["source_record_cards"].pop(),
            "mapping cards": lambda pack: pack["mapping_cards"].pop(),
            "context edges": lambda pack: pack["context_edges"].clear(),
            "counts": lambda pack: pack["counts"].update(context_edges=0),
            "metadata lineage": lambda pack: pack["metadata"].update(graph_release_id="graph-release-tampered"),
            "graph context": lambda pack: pack["graph_context"].update(graph_version_id="graph-tampered"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                tampered = copy.deepcopy(self.pack)
                mutate(tampered)
                tampered["metadata"]["pack_sha256"] = _pack_hash(tampered)
                errors = validate_family_evidence_pack_v2(tampered, self.config)
                self.assertTrue(
                    any("exact regenerated content" in error for error in errors),
                    errors,
                )
        candidate_config = generate_family_config_v2(CANDIDATE_FAMILY)
        candidate_pack = compile_family_evidence_pack_v2(candidate_config)
        candidate_pack["required_candidate_cards"].pop()
        candidate_pack["metadata"]["pack_sha256"] = _pack_hash(candidate_pack)
        candidate_errors = validate_family_evidence_pack_v2(
            candidate_pack, candidate_config
        )
        self.assertTrue(
            any("required_candidate_cards" in error for error in candidate_errors),
            candidate_errors,
        )

    def test_persisted_preparation_replays_and_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output_root = Path(raw) / "preparations"
            result = prepare_family_v2(UNLINKED_FAMILY, output_root=output_root)
            preparation_dir = Path(result["preparation_path"])
            valid = validate_family_preparation_v2(preparation_dir)
            self.assertTrue(valid["valid"], valid["errors"])
            for filename, label in (
                ("family-config-v2.json", "config"),
                ("family-evidence-pack-v2.json", "pack"),
                ("preparation-receipt.json", "receipt"),
            ):
                path = preparation_dir / filename
                canonical_bytes = path.read_bytes()
                value = json.loads(canonical_bytes)
                path.write_text(json.dumps(value, indent=2), encoding="utf-8")
                noncanonical = validate_family_preparation_v2(preparation_dir)
                self.assertFalse(noncanonical["valid"])
                self.assertIn(
                    f"persisted {label} bytes are not canonical",
                    noncanonical["errors"],
                )
                path.write_bytes(canonical_bytes)
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
