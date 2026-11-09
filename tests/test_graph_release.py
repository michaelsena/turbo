import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.pipeline_paths import ROOT
from turbo.universe.graph_release import compile_graph_release, run_graph_release


CONFIG = ROOT / "config/universe/graph-releases/canonical-universe-v1.json"
EXECUTION_COMMIT = "2" * 40


class GraphReleaseTest(unittest.TestCase):
    def test_compiles_cumulative_release_from_approved_activation(self) -> None:
        compiled = compile_graph_release(CONFIG, execution_commit=EXECUTION_COMMIT)
        projection = compiled["projection"]
        self.assertEqual(len(compiled["activation_bindings"]), 1)
        self.assertEqual(len(projection["markets"]), 3)
        self.assertEqual(len(projection["mappings"]), 1)
        self.assertEqual(len(projection["active_event_ids"]), 4)

    def test_duplicate_activation_fails_closed(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["activations"].append(dict(config["activations"][0]))
        with tempfile.TemporaryDirectory() as raw_temp:
            path = Path(raw_temp) / "release.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate graph release activation"):
                compile_graph_release(path, execution_commit=EXECUTION_COMMIT)

    def test_publication_requires_clean_worktree(self) -> None:
        with patch(
            "turbo.universe.graph_release._git_worktree_clean", return_value=False
        ):
            with self.assertRaisesRegex(RuntimeError, "requires a clean Git worktree"):
                run_graph_release(CONFIG)


if __name__ == "__main__":
    unittest.main()
