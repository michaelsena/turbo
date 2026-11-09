from __future__ import annotations

import concurrent.futures
import hashlib
import json
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from turbo.agents.boundary_harness import (
    canonical_sha256,
    load_adjudication_schema,
    load_specialist_schema,
    validate_boundary_output,
)
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack


@dataclass(frozen=True)
class InvocationResult:
    output: dict[str, Any]
    receipt: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _codex_version() -> str:
    result = subprocess.run(
        ["codex", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def codex_command(
    *,
    work_dir: Path,
    model: str,
    reasoning_effort: str,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        str(work_dir),
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
        "-",
    ]


def _runtime_prompt(
    base_prompt: str,
    *,
    role_id: str,
    invocation_id: str,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None,
) -> str:
    envelope: dict[str, Any] = {
        "expected_role_id": role_id,
        "expected_invocation_id": invocation_id,
        "expected_family_id": pack["metadata"]["family_id"],
        "expected_input_pack_sha256": pack["metadata"]["pack_sha256"],
        "frozen_evidence_pack": pack,
    }
    if specialist_outputs is not None:
        envelope["validated_specialist_outputs"] = specialist_outputs
        envelope["expected_specialist_output_sha256"] = [
            canonical_sha256(item) for item in specialist_outputs
        ]
    return base_prompt.rstrip() + "\n\n# Runtime envelope\n\n" + json.dumps(
        envelope, sort_keys=True, separators=(",", ":")
    )


def invoke_codex_role(
    *,
    role_id: str,
    model: str,
    reasoning_effort: str,
    prompt_path: Path,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None = None,
    timeout_seconds: int = 1800,
    root: Path = ROOT,
) -> InvocationResult:
    if role_id not in {"specialist-a", "specialist-b", "adjudicator"}:
        raise ValueError(f"unsupported boundary role: {role_id}")
    if role_id == "adjudicator" and (
        specialist_outputs is None or len(specialist_outputs) != 2
    ):
        raise ValueError("adjudicator requires exactly two validated specialist outputs")
    if role_id != "adjudicator" and specialist_outputs is not None:
        raise ValueError("blind specialists cannot receive specialist outputs")

    invocation_id = f"invocation:{secrets.token_hex(12)}"
    base_prompt = prompt_path.read_text(encoding="utf-8")
    runtime_prompt = _runtime_prompt(
        base_prompt,
        role_id=role_id,
        invocation_id=invocation_id,
        pack=pack,
        specialist_outputs=specialist_outputs,
    )
    schema = (
        load_adjudication_schema(root=root)
        if role_id == "adjudicator"
        else load_specialist_schema(root=root)
    )
    schema_text = json.dumps(schema, sort_keys=True, separators=(",", ":")) + "\n"
    started_at = _utc_now()
    cli_version = _codex_version()

    with tempfile.TemporaryDirectory(prefix=f"turbo-{role_id}-") as raw_temp:
        temp_dir = Path(raw_temp)
        schema_path = temp_dir / "output.schema.json"
        output_path = temp_dir / "final.json"
        schema_path.write_text(schema_text, encoding="utf-8")
        command = codex_command(
            work_dir=temp_dir,
            model=model,
            reasoning_effort=reasoning_effort,
            schema_path=schema_path,
            output_path=output_path,
        )
        completed = subprocess.run(
            command,
            input=runtime_prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        completed_at = _utc_now()
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "invocation_id": invocation_id,
            "role_id": role_id,
            "family_id": pack["metadata"]["family_id"],
            "model": model,
            "reasoning_effort": reasoning_effort,
            "codex_cli_version": cli_version,
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
            "prompt_sha256": _sha256_text(base_prompt),
            "runtime_prompt_sha256": _sha256_text(runtime_prompt),
            "schema_sha256": _sha256_text(schema_text),
            "input_pack_sha256": pack["metadata"]["pack_sha256"],
            "exit_code": completed.returncode,
            "stdout_sha256": _sha256_text(completed.stdout),
            "stderr_sha256": _sha256_text(completed.stderr),
            "raw_reasoning_persisted": False,
            "status": "failed",
        }
        if completed.returncode != 0:
            stderr_tail = completed.stderr[-2_000:].strip()
            raise RuntimeError(
                f"{role_id} invocation failed with exit code {completed.returncode}; "
                f"stderr_tail={stderr_tail!r}; "
                f"receipt={json.dumps(receipt, sort_keys=True)}"
            )
        if not output_path.exists():
            raise RuntimeError(f"{role_id} invocation produced no final output file")
        try:
            output = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{role_id} final output was not JSON: {error}") from error
        errors = validate_boundary_output(
            output,
            pack,
            expected_role=role_id,
            specialist_outputs=specialist_outputs,
            root=root,
        )
        receipt["output_sha256"] = canonical_sha256(output)
        receipt["validation_errors"] = errors
        receipt["status"] = "valid" if not errors else "invalid"
        if errors:
            raise RuntimeError(
                f"{role_id} output failed closed-world validation: "
                + json.dumps(errors)
            )
        return InvocationResult(output=output, receipt=receipt)


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
        return invoke_codex_role(
            role_id=role_id,
            model=execution["specialist_model"],
            reasoning_effort=execution["reasoning_effort"],
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

    adjudication = invoke_codex_role(
        role_id="adjudicator",
        model=execution["adjudicator_model"],
        reasoning_effort=execution["reasoning_effort"],
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
        "config_sha256": _sha256_text(config_path.read_text(encoding="utf-8")),
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
