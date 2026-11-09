import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.pipeline_paths import ROOT
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
        self.assertEqual(ledger["counts"]["prior_candidates"], 978)
        self.assertEqual(ledger["counts"]["retrieved_candidates"], 920)
        self.assertEqual(ledger["counts"]["unretrieved_candidates"], 58)

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
