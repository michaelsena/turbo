import tempfile
import unittest
from pathlib import Path

from turbo.agents.boundary_harness import load_adjudication_schema, load_specialist_schema
from turbo.agents.codex_runner import _runtime_prompt, codex_command
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack


CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"


class CodexRunnerContractTest(unittest.TestCase):
    def test_model_schemas_use_the_supported_structured_output_subset(self) -> None:
        def assert_supported(value: object) -> None:
            if isinstance(value, dict):
                self.assertNotIn("oneOf", value)
                self.assertNotIn("uniqueItems", value)
                for child in value.values():
                    assert_supported(child)
            elif isinstance(value, list):
                for child in value:
                    assert_supported(child)

        assert_supported(load_specialist_schema())
        assert_supported(load_adjudication_schema())

    def test_command_is_ephemeral_isolated_read_only_and_schema_bound(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            work_dir = Path(raw_temp)
            command = codex_command(
                work_dir=work_dir,
                model="test-model",
                reasoning_effort="high",
                schema_path=work_dir / "schema.json",
                output_path=work_dir / "output.json",
            )
        self.assertEqual(command[:2], ["codex", "exec"])
        for flag in (
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--output-schema",
        ):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[-1], "-")
        self.assertNotIn("--json", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_blind_specialist_runtime_contains_no_other_model_output(self) -> None:
        pack = build_boundary_pack(CONFIG)
        prompt = _runtime_prompt(
            "base",
            role_id="specialist-a",
            invocation_id=f"invocation:{'a' * 24}",
            pack=pack,
            specialist_outputs=None,
        )
        self.assertIn('"expected_role_id":"specialist-a"', prompt)
        self.assertNotIn("validated_specialist_outputs", prompt)
        self.assertNotIn("expected_specialist_output_sha256", prompt)


if __name__ == "__main__":
    unittest.main()
