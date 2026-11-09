import json
import tempfile
import unittest
from pathlib import Path

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.system_context import compile_system_context
from turbo.universe.graph_release import compile_graph_release, _receipt
from turbo.universe.family_scheduler import compile_family_plan


CONFIG = ROOT / "config/universe/graph-releases/canonical-universe-v1.json"
EXECUTION_COMMIT = "2" * 40
FAMILY_CONFIG = ROOT / "config/universe/family-partition-v1.json"


class SystemContextTest(unittest.TestCase):
    def _copy_source_pointer(self, root: Path) -> None:
        generated = root / "data/generated"
        generated.mkdir(parents=True)
        latest = json.loads(
            (ROOT / "data/generated/latest-run.json").read_text(encoding="utf-8")
        )
        source_dir = ROOT / latest["immutable_run_path"]
        target_dir = root / latest["immutable_run_path"]
        target_dir.mkdir(parents=True)
        receipt = json.loads(
            (source_dir / "run-receipt.json").read_text(encoding="utf-8")
        )
        (target_dir / "run-receipt.json").write_bytes(
            (source_dir / "run-receipt.json").read_bytes()
        )
        for name in receipt["output_hashes"]:
            (target_dir / name).write_bytes((source_dir / name).read_bytes())
        (generated / "latest-run.json").write_text(
            json.dumps(latest), encoding="utf-8"
        )

    def test_source_only_context_does_not_invent_graph_markets(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            self._copy_source_pointer(root)
            context = compile_system_context(root=root)
        self.assertEqual(context["canonical_markets"], 0)
        self.assertEqual(context["current_stage"], "source_reconciliation_complete")

    def test_source_context_rehashes_every_declared_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            self._copy_source_pointer(root)
            latest = json.loads(
                (root / "data/generated/latest-run.json").read_text(encoding="utf-8")
            )
            receipt_path = root / latest["immutable_run_path"] / "run-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            artifact_name = sorted(receipt["output_hashes"])[0]
            artifact_path = receipt_path.parent / artifact_name
            artifact_path.write_bytes(artifact_path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "source-run artifact hash mismatch"):
                compile_system_context(root=root)

    def test_composed_context_reads_hash_verified_cumulative_graph(self) -> None:
        compiled = compile_graph_release(CONFIG, execution_commit=EXECUTION_COMMIT)
        receipt = _receipt(compiled)
        projection = compiled["projection"]
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            self._copy_source_pointer(root)
            release_dir = root / "data/market_graph/versions" / compiled["release_id"]
            release_dir.mkdir(parents=True)
            (release_dir / "graph-receipt.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            (release_dir / "projection.json").write_text(
                json.dumps(projection), encoding="utf-8"
            )
            pointer = {
                "schema_version": 1,
                "release_id": receipt["release_id"],
                "graph_version_id": receipt["graph_version_id"],
                "source_universe_run_id": receipt["source_universe_run_id"],
                "release_path": str(release_dir.relative_to(root)),
                "receipt_sha256": canonical_sha256(receipt),
                "projection_sha256": canonical_sha256(projection),
            }
            (root / "data/generated/latest-graph.json").write_text(
                json.dumps(pointer), encoding="utf-8"
            )
            context = compile_system_context(root=root)
        self.assertEqual(context["canonical_markets"], 3)
        self.assertEqual(
            context["current_stage"], "canonical_universe_construction_in_progress"
        )

    def test_composed_context_verifies_family_schedule_artifacts(self) -> None:
        compiled = compile_family_plan(FAMILY_CONFIG, execution_commit="3" * 40)
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            self._copy_source_pointer(root)
            schedule_dir = root / "data/family_schedules" / compiled["partition_id"]
            schedule_dir.mkdir(parents=True)
            for name, value in compiled["artifacts"].items():
                path = schedule_dir / name
                if name.endswith(".gz"):
                    from turbo.universe.family_scheduler import _canonical_gzip

                    path.write_bytes(_canonical_gzip(value))
                else:
                    from turbo.universe.family_scheduler import _canonical_bytes

                    path.write_bytes(_canonical_bytes(value))
            receipt = compiled["receipt"]
            (schedule_dir / "schedule-receipt.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            pointer = {
                "schema_version": 1,
                "status": receipt["status"],
                "partition_id": receipt["partition_id"],
                "source_run_id": receipt["source_run_id"],
                "schedule_path": str(schedule_dir.relative_to(root)),
                "receipt_sha256": canonical_sha256(receipt),
                "counts": receipt["counts"],
            }
            (root / "data/generated/latest-family-schedule.json").write_text(
                json.dumps(pointer), encoding="utf-8"
            )
            context = compile_system_context(root=root)
            (schedule_dir / "batch-manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
                compile_system_context(root=root)
        self.assertEqual(
            context["family_schedule"]["counts"]["normalized_identities"], 11_543
        )


if __name__ == "__main__":
    unittest.main()
