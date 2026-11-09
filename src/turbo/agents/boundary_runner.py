from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.codex_runner import invoke_codex_role
from turbo.agents.openrouter_runner import invoke_openrouter_role
from turbo.agents.runtime import InvocationResult, sha256_text
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack


def _role_model(execution: dict[str, Any], role_id: str) -> str:
    role_models = execution.get("role_models", {})
    if role_id in role_models:
        return role_models[role_id]
    if role_id == "adjudicator":
        return execution["adjudicator_model"]
    return execution["specialist_model"]


def invoke_configured_role(
    execution: dict[str, Any],
    *,
    role_id: str,
    prompt_path: Path,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None = None,
    timeout_seconds: int,
    root: Path,
) -> InvocationResult:
    provider = execution.get("provider", "codex_cli")
    common = {
        "role_id": role_id,
        "model": _role_model(execution, role_id),
        "reasoning_effort": execution["reasoning_effort"],
        "prompt_path": prompt_path,
        "pack": pack,
        "specialist_outputs": specialist_outputs,
        "timeout_seconds": timeout_seconds,
        "root": root,
    }
    if provider == "codex_cli":
        return invoke_codex_role(**common)
    if provider == "openrouter":
        openrouter = execution.get("openrouter", {})
        return invoke_openrouter_role(
            **common,
            max_completion_tokens=openrouter.get("max_completion_tokens", 128_000),
            allow_fallbacks=openrouter.get("allow_fallbacks", True),
            max_attempts=openrouter.get("max_attempts", 3),
            max_validation_repairs=openrouter.get("max_validation_repairs", 2),
            api_url=openrouter.get(
                "api_url", "https://openrouter.ai/api/v1/chat/completions"
            ),
        )
    raise ValueError(f"unsupported model provider: {provider}")


def run_boundary_pilot(
    config_path: Path,
    *,
    output_root: Path | None = None,
    root: Path = ROOT,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    pack = build_boundary_pack(config_path, root=root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    execution = config["baseline_execution"]
    specialist_prompt = root / "prompts/universe/boundary-specialist-v1.md"
    adjudicator_prompt = root / "prompts/universe/boundary-adjudicator-v1.md"

    def run_specialist(role_id: str) -> InvocationResult:
        return invoke_configured_role(
            execution,
            role_id=role_id,
            prompt_path=specialist_prompt,
            pack=pack,
            timeout_seconds=timeout_seconds,
            root=root,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            role_id: executor.submit(run_specialist, role_id)
            for role_id in ("specialist-a", "specialist-b")
        }
        specialist_results = [futures[role_id].result() for role_id in sorted(futures)]

    adjudication = invoke_configured_role(
        execution,
        role_id="adjudicator",
        prompt_path=adjudicator_prompt,
        pack=pack,
        specialist_outputs=[result.output for result in specialist_results],
        timeout_seconds=timeout_seconds,
        root=root,
    )

    run_fingerprint = canonical_sha256(
        {
            "pack_sha256": pack["metadata"]["pack_sha256"],
            "invocation_ids": [
                result.receipt["invocation_id"]
                for result in [*specialist_results, adjudication]
            ],
        }
    )[:20]
    run_id = f"boundary-run-{run_fingerprint}"
    destination = output_root or root / "data/agent_runs"
    run_dir = destination / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for result in specialist_results + [adjudication]:
        role = result.receipt["role_id"]
        (run_dir / f"{role}.json").write_text(
            json.dumps(result.output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (run_dir / f"{role}.receipt.json").write_text(
            json.dumps(result.receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    run_receipt = {
        "schema_version": 1,
        "boundary_run_id": run_id,
        "family_id": pack["metadata"]["family_id"],
        "source_run_id": pack["metadata"]["source_run_id"],
        "input_pack_sha256": pack["metadata"]["pack_sha256"],
        "config_sha256": sha256_text(config_path.read_text(encoding="utf-8")),
        "provider": execution.get("provider", "codex_cli"),
        "specialist_output_sha256": [
            result.receipt["output_sha256"] for result in specialist_results
        ],
        "adjudication_output_sha256": adjudication.receipt["output_sha256"],
        "status": "validated_proposal_not_activated",
        "raw_reasoning_persisted": False,
    }
    (run_dir / "run-receipt.json").write_text(
        json.dumps(run_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"run_dir": str(run_dir), **run_receipt}
