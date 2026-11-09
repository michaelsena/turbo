import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents.openrouter_runner import (
    invoke_openrouter_role,
    openrouter_request_body,
    openrouter_schema,
)


def test_pack() -> dict[str, object]:
    return {
        "metadata": {"family_id": "test-family", "pack_sha256": "a" * 64},
        "scope": {"required_disposition_identity_ids": []},
        "retrieved_prior_candidate_details": [],
    }


class OpenRouterRunnerTest(unittest.TestCase):
    def test_provider_schema_omits_nonportable_constraints(self) -> None:
        canonical = {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
            },
        }
        adapted = openrouter_schema(canonical)
        self.assertEqual(adapted["properties"]["score"], {"type": "number"})
        self.assertNotIn("uniqueItems", adapted["properties"]["ids"])
        self.assertEqual(canonical["properties"]["score"]["minimum"], 0)

    def test_provider_schema_adds_types_required_by_strict_endpoints(self) -> None:
        adapted = openrouter_schema(
            {
                "type": "object",
                "properties": {
                    "version": {"const": 1},
                    "role": {"const": "adjudicator"},
                    "label": {"enum": ["fact", "inference"]},
                    "nullable": {"enum": [None, "known"]},
                },
            }
        )
        properties = adapted["properties"]
        self.assertEqual(properties["version"]["type"], "integer")
        self.assertEqual(properties["role"]["type"], "string")
        self.assertEqual(properties["label"]["type"], "string")
        self.assertEqual(properties["nullable"]["type"], ["null", "string"])

    def test_request_requires_structured_output_and_excludes_reasoning(self) -> None:
        body = openrouter_request_body(
            role_id="specialist-a",
            model="vendor/model",
            reasoning_effort="high",
            runtime_prompt_text="bounded prompt",
            schema={"type": "object"},
            invocation_id=f"invocation:{'a' * 24}",
            max_completion_tokens=10_000,
            allow_fallbacks=True,
        )
        self.assertEqual(body["model"], "vendor/model")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertTrue(body["provider"]["require_parameters"])
        self.assertTrue(body["provider"]["allow_fallbacks"])
        self.assertEqual(body["reasoning"], {"effort": "high", "exclude": True})
        self.assertFalse(body["stream"])

    @patch("turbo.agents.openrouter_runner.validate_boundary_output", return_value=[])
    @patch(
        "turbo.agents.openrouter_runner.load_specialist_schema",
        return_value={"type": "object"},
    )
    def test_valid_response_produces_redacted_audit_receipt(
        self, _schema: object, _validate: object
    ) -> None:
        captured: dict[str, object] = {}
        secret = "sk-or-test-secret"

        def transport(
            url: str,
            headers: dict[str, str],
            body: bytes,
            timeout: float,
        ) -> tuple[int, dict[str, str], bytes]:
            captured.update(
                {"url": url, "headers": headers, "body": body, "timeout": timeout}
            )
            payload = json.loads(body)
            response = {
                "id": "generation-test",
                "model": "vendor/model",
                "provider": "Provider A",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"answer": "bounded"}),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "cost": 0.01,
                    "unsafe_string": "do-not-copy",
                },
            }
            self.assertEqual(payload["session_id"].split(":")[0], "invocation")
            return 200, {}, json.dumps(response).encode("utf-8")

        pack = test_pack()
        with tempfile.TemporaryDirectory() as raw_temp:
            prompt_path = Path(raw_temp) / "prompt.md"
            prompt_path.write_text("System contract.", encoding="utf-8")
            result = invoke_openrouter_role(
                role_id="specialist-a",
                model="vendor/model",
                reasoning_effort="high",
                prompt_path=prompt_path,
                pack=pack,
                api_key=secret,
                max_attempts=1,
                transport=transport,
            )

        self.assertEqual(result.output, {"answer": "bounded"})
        self.assertEqual(result.receipt["provider"], "openrouter")
        self.assertEqual(result.receipt["generation_id"], "generation-test")
        self.assertEqual(result.receipt["served_model"], "vendor/model")
        self.assertEqual(result.receipt["served_provider"], "Provider A")
        self.assertEqual(result.receipt["usage"]["cost"], 0.01)
        self.assertNotIn("unsafe_string", result.receipt["usage"])
        self.assertFalse(result.receipt["credential_persisted"])
        self.assertNotIn(secret, json.dumps(result.receipt, sort_keys=True))
        self.assertEqual(len(result.receipt["model_calls"]), 1)
        self.assertEqual(
            captured["headers"]["Authorization"],  # type: ignore[index]
            f"Bearer {secret}",
        )

    def test_missing_api_key_fails_before_network(self) -> None:
        pack = test_pack()
        with tempfile.TemporaryDirectory() as raw_temp:
            prompt_path = Path(raw_temp) / "prompt.md"
            prompt_path.write_text("System contract.", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                    invoke_openrouter_role(
                        role_id="specialist-a",
                        model="vendor/model",
                        reasoning_effort="high",
                        prompt_path=prompt_path,
                        pack=pack,
                    )

    @patch(
        "turbo.agents.openrouter_runner.validate_boundary_output",
        side_effect=[["missing required coverage"], []],
    )
    @patch(
        "turbo.agents.openrouter_runner.load_specialist_schema",
        return_value={"type": "object"},
    )
    def test_local_validation_failure_triggers_bounded_correction(
        self, _schema: object, _validate: object
    ) -> None:
        prompts: list[str] = []

        def transport(
            _url: str,
            _headers: dict[str, str],
            body: bytes,
            _timeout: float,
        ) -> tuple[int, dict[str, str], bytes]:
            request = json.loads(body)
            prompts.append(request["messages"][0]["content"])
            response = {
                "id": f"generation-{len(prompts)}",
                "model": "vendor/model",
                "provider": "Provider A",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"round": len(prompts)})
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
            }
            return 200, {}, json.dumps(response).encode("utf-8")

        pack = test_pack()
        with tempfile.TemporaryDirectory() as raw_temp:
            prompt_path = Path(raw_temp) / "prompt.md"
            prompt_path.write_text("System contract.", encoding="utf-8")
            result = invoke_openrouter_role(
                role_id="specialist-a",
                model="vendor/model",
                reasoning_effort="high",
                prompt_path=prompt_path,
                pack=pack,
                api_key="sk-or-test-secret",
                max_validation_repairs=1,
                transport=transport,
            )

        self.assertEqual(result.output, {"round": 2})
        self.assertEqual(result.receipt["validation_repairs_used"], 1)
        self.assertEqual(len(result.receipt["model_calls"]), 2)
        self.assertNotIn("Required correction round", prompts[0])
        self.assertIn("Required correction round", prompts[1])
        self.assertIn("missing required coverage", prompts[1])

    @patch("turbo.agents.openrouter_runner.load_specialist_schema", return_value={"type": "object"})
    def test_retryable_failure_retries_and_redacts_secret(self, _schema: object) -> None:
        secret = "sk-or-test-secret"
        attempts = 0

        def transport(
            _url: str,
            _headers: dict[str, str],
            _body: bytes,
            _timeout: float,
        ) -> tuple[int, dict[str, str], bytes]:
            nonlocal attempts
            attempts += 1
            return 502, {}, f"upstream echoed {secret}".encode("utf-8")

        pack = test_pack()
        with tempfile.TemporaryDirectory() as raw_temp:
            prompt_path = Path(raw_temp) / "prompt.md"
            prompt_path.write_text("System contract.", encoding="utf-8")
            with self.assertRaises(RuntimeError) as raised:
                invoke_openrouter_role(
                    role_id="specialist-a",
                    model="vendor/model",
                    reasoning_effort="high",
                    prompt_path=prompt_path,
                    pack=pack,
                    api_key=secret,
                    max_attempts=2,
                    transport=transport,
                    sleeper=lambda _seconds: None,
                )

        self.assertEqual(attempts, 2)
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("provider error response omitted", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
