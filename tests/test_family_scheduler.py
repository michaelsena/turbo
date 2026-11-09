import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack
from turbo.universe.family_scheduler import compile_family_plan, run_family_plan


CONFIG = ROOT / "config/universe/family-partition-v1.json"
EXECUTION_COMMIT = "3" * 40


class FamilySchedulerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled = compile_family_plan(CONFIG, execution_commit=EXECUTION_COMMIT)

    def test_accounts_for_every_identity_once(self) -> None:
        coverage = self.compiled["artifacts"]["coverage-ledger.json.gz"]
        assignments = coverage["assignments"]
        self.assertEqual(len(assignments), 11_543)
        self.assertEqual(len({item["identity_id"] for item in assignments}), 11_543)
        self.assertEqual(
            sum(item["assignment_role"] == "required_review" for item in assignments),
            8_248,
        )
        self.assertEqual(
            sum(item["assignment_role"] == "context_only" for item in assignments),
            3_295,
        )
        self.assertTrue(
            all(
                item["owner_family_id"] in item["appearance_family_ids"]
                for item in assignments
            )
        )

    def test_candidate_ledger_is_complete_and_keeps_unretrieved_challengers(self) -> None:
        ledger = self.compiled["artifacts"]["candidate-collision-ledger.json.gz"]
        manifest = self.compiled["artifacts"]["family-manifest.json.gz"]
        families = {item["family_id"]: item for item in manifest["families"]}
        self.assertEqual(ledger["counts"]["prior_candidates"], 978)
        self.assertEqual(ledger["counts"]["retrieved_candidates"], 920)
        self.assertEqual(ledger["counts"]["unretrieved_candidates"], 58)
        self.assertEqual(ledger["counts"]["context_only_collision_candidates"], 0)
        self.assertEqual(
            sum(
                item["coverage_status"] == "context_only_collision_challenger"
                for item in ledger["candidates"]
            ),
            0,
        )
        self.assertTrue(
            all(
                families[item["primary_family_id"]]["schedulable"]
                or families[item["primary_family_id"]]["status"]
                == "completed_regression_fixture"
                for item in ledger["candidates"]
            )
        )
        repaired_candidate_ids = {
            "candidate-market:e007e822bf1951d24dacbd13",
            "candidate-market:ef502835138bdd6a5f88bd59",
        }
        repaired = {
            item["candidate_market_id"]: item
            for item in ledger["candidates"]
            if item["candidate_market_id"] in repaired_candidate_ids
        }
        self.assertEqual(set(repaired), repaired_candidate_ids)
        self.assertTrue(
            all(
                repaired[item_id]["coverage_status"] == "retrieved_collision"
                and families[repaired[item_id]["primary_family_id"]]["schedulable"]
                for item_id in repaired_candidate_ids
            )
        )

    def test_pilot_surface_is_pinned_and_completed(self) -> None:
        manifest = self.compiled["artifacts"]["family-manifest.json.gz"]
        family = next(
            item
            for item in manifest["families"]
            if item["family_id"] == "family:naics-2022:561110"
        )
        self.assertEqual(family["status"], "completed_regression_fixture")
        self.assertFalse(family["schedulable"])
        self.assertEqual(family["counts"]["required_identities"], 66)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        pilot = config["pilot_regression"]
        pack = build_boundary_pack(ROOT / pilot["source_family_config"])
        expected_required = set(pack["scope"]["required_disposition_identity_ids"])
        expected_context = set(pack["scope"]["context_only_identity_ids"])
        expected_context.update(pack["scope"]["linked_trilateral_product_identity_ids"])
        expected_context.update(
            subject_id
            for evidence in pack["evidence_catalog"]
            if evidence["context_only"]
            for subject_id in evidence["subject_ids"]
            if subject_id not in expected_required
        )
        self.assertEqual(pack["metadata"]["pack_sha256"], pilot["source_pack_sha256"])
        self.assertEqual(
            set(family["required_disposition_identity_ids"]), expected_required
        )
        self.assertEqual(set(family["context_only_identity_ids"]), expected_context)
        receipt = self.compiled["receipt"]["pilot_regression"]
        self.assertEqual(receipt["required_identities"], 66)
        self.assertEqual(receipt["context_identities"], 162)
        self.assertEqual(
            receipt["required_identity_set_sha256"],
            canonical_sha256(sorted(expected_required)),
        )
        self.assertEqual(
            receipt["context_identity_set_sha256"],
            canonical_sha256(sorted(expected_context)),
        )

    def test_context_edge_ledger_is_complete_and_resolves_assignment_edges(self) -> None:
        ledger = self.compiled["artifacts"]["context-edge-ledger.json.gz"]
        coverage = self.compiled["artifacts"]["coverage-ledger.json.gz"]
        self.assertEqual(ledger["counts"]["industry_product_relationships"], 37_232)
        self.assertEqual(ledger["counts"]["napcs_concordance_relationships"], 3_516)
        self.assertEqual(ledger["counts"]["napcs_concordance_non_mappings"], 7)
        relationship_ids = {
            item["relationship_id"]
            for collection in (
                "industry_product_relationships",
                "napcs_concordance_relationships",
                "napcs_concordance_non_mappings",
            )
            for item in ledger[collection]
        }
        referenced_ids = {
            relationship_id
            for assignment in coverage["assignments"]
            for relationship_id in assignment["supporting_relationship_ids"]
        }
        self.assertTrue(referenced_ids)
        self.assertEqual(referenced_ids - relationship_ids, set())

    def test_compilation_is_independent_of_source_record_order(self) -> None:
        baseline = self.compiled["receipt"]["output_hashes"]
        with patch(
            "turbo.universe.family_scheduler._load_verified_run_artifact"
        ) as loader:
            from turbo.universe.boundary_pack import _load_verified_run_artifact

            def permuted(run_dir, receipt, name):
                value = copy.deepcopy(_load_verified_run_artifact(run_dir, receipt, name))
                for field in (
                    "source_identities",
                    "source_records",
                    "mappings",
                    "candidate_markets",
                    "industry_product_relationships",
                    "napcs_concordance_relationships",
                    "napcs_concordance_non_mappings",
                    "nodes",
                ):
                    if isinstance(value.get(field), list):
                        value[field].reverse()
                return value

            loader.side_effect = permuted
            replay = compile_family_plan(CONFIG, execution_commit=EXECUTION_COMMIT)
        self.assertEqual(replay["receipt"]["output_hashes"], baseline)

    def test_count_gate_tampering_fails_closed(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["expected_counts"]["normalized_identities"] = 1
        with tempfile.TemporaryDirectory() as raw_temp:
            path = Path(raw_temp) / "partition.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "count gate normalized_identities"):
                compile_family_plan(path, execution_commit=EXECUTION_COMMIT)

    def test_publication_requires_clean_worktree(self) -> None:
        with patch(
            "turbo.universe.family_scheduler._git_worktree_clean", return_value=False
        ):
            with self.assertRaisesRegex(RuntimeError, "requires a clean Git worktree"):
                run_family_plan(CONFIG)


if __name__ == "__main__":
    unittest.main()
