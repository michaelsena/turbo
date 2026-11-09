#!/usr/bin/env python3
"""Run one real Codex research batch over verified frozen inputs. Never retry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from turbo.agents.batch_authorization import canonical_bytes
from turbo.agents.batch_output import (
    DEFAULT_MAX_CONTEXT_BYTES, DEFAULT_MAX_OUTPUT_BYTES, PROMPT_PATH, SCHEMA_PATH,
    _strict_json, build_batch_context, validate_batch_output_file,
)
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _save(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(canonical_bytes(value)); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _usage(stdout: str) -> dict[str, int]:
    usage: dict[str, int] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                value = event["usage"].get(key)
                if type(value) is int and value >= 0:
                    usage[key] = usage.get(key, 0) + value
    return usage


def codex_process(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Kill the complete session on timeout, even if its leader already exited."""
    timeout, input_text = kwargs.pop("timeout"), kwargs.pop("input")
    kwargs.pop("check", None)
    kwargs.pop("capture_output", None)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True, **kwargs)
    try:
        stdout, stderr = process.communicate(input_text, timeout=timeout)
    except BaseException:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _error_category(stdout: str, stderr: str) -> str:
    text = (stdout + "\n" + stderr).lower()
    for category, markers in (
        ("context_limit", ("context length", "context window", "maximum context")),
        ("rate_or_usage_limit", ("rate limit", "usage limit", "quota")),
        ("authentication_failed", ("unauthorized", "not logged", "authentication")),
        ("unsupported_cli_argument", ("unexpected argument", "unknown argument", "unrecognized option")),
        ("schema_rejected", ("schema",)),
        ("network_failed", ("connection", "network", "dns", "timed out")),
    ):
        if any(marker in text for marker in markers): return category
    return "codex_nonzero_exit"


def run_batch(
    context_path: Path, preparation_dirs: list[Path], output_root: Path, *,
    root: Path = ROOT, timeout_seconds: int = 3600, runner: Callable = codex_process,
    model: str | None = None, reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if model is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", model):
        raise ValueError("invalid explicit model")
    if reasoning_effort is not None and reasoning_effort not in {"minimal", "low", "medium", "high", "xhigh"}:
        raise ValueError("invalid explicit reasoning effort")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be 1..86400")
    with Path(context_path).open("rb") as handle:
        raw_context = handle.read(DEFAULT_MAX_CONTEXT_BYTES + 1)
    if len(raw_context) > DEFAULT_MAX_CONTEXT_BYTES:
        raise ValueError("context exceeds its byte bound")
    supplied = _strict_json(raw_context)
    if not isinstance(supplied, dict) or supplied.get("limits") != {
            "max_output_bytes": DEFAULT_MAX_OUTPUT_BYTES, "max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES}:
        raise ValueError("context must use the standard output/context limits")
    context = build_batch_context(preparation_dirs, request_id=supplied["request_id"],
        invocation_id=supplied["invocation_id"], root=root)
    if canonical_bytes(supplied) != canonical_bytes(context):
        raise ValueError("context does not match verified frozen preparations")
    prompt = (root / PROMPT_PATH).read_text(encoding="utf-8")
    schema = (root / SCHEMA_PATH).read_bytes()
    if hashlib.sha256(prompt.encode()).hexdigest() != context["prompt_sha256"] or hashlib.sha256(schema).hexdigest() != context["output_schema_sha256"]:
        raise ValueError("prompt/schema changed during input verification")
    context_bytes = canonical_bytes(context)
    manifest = {"request_id": context["request_id"], "invocation_id": context["invocation_id"],
        "context_sha256": context["context_sha256"],
        "context_file_sha256": hashlib.sha256(context_bytes).hexdigest(),
        "families": [{"family_id": family["family_id"],
            "required_identities": len(family["required_identity_ids"]),
            "required_candidates": len(family["required_candidate_ids"])} for family in context["families"]]}
    runtime_prompt = (prompt + "\n\nThe complete verified batch context is in context.json in your working directory. "
        "Read this file using local tools; you may inspect its sections incrementally with Python. "
        "It contains every required subject, all frozen evidence values and exact citation IDs; no evidence was truncated. "
        "Read all required IDs, inspect relevant evidence, and return dispositions covering the entire requested batch. "
        "No external research, credential access, repository edits, or further model dispatch is authorized. "
        "Return only the required JSON; preserve uncertainty and propose useful operating-market boundaries where supported.\n\n"
        "Exact input manifest:\n" + canonical_bytes(manifest).decode())
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    directory = output_root / supplied["invocation_id"].removeprefix("invocation:")
    directory.mkdir()  # Atomic claim. Existing/interrupted invocations never rerun.
    descriptor = os.open(output_root, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    receipt = {"schema_version": 1, "provider": "codex_cli", "execution_mode": "real_research",
        "requested_model": model or "configured_default",
        "reasoning_effort": reasoning_effort or "configured_default",
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "request_id": context["request_id"],
        "invocation_id": context["invocation_id"], "context_sha256": context["context_sha256"],
        "prompt_sha256": context["prompt_sha256"], "schema_sha256": context["output_schema_sha256"],
        "runtime_prompt_sha256": hashlib.sha256(runtime_prompt.encode()).hexdigest(),
        "input_bindings": context["input_bindings"], "git_commit": git.stdout.strip() if git.returncode == 0 else None,
        "started_at_utc": now(), "status": "in_progress", "model_invoked": "unknown",
        "raw_reasoning_persisted": False, "credential_persisted": False,
        "automatic_retries": 0, "structural_validation_only": True}
    receipt_path = directory / "run-receipt.json"
    _save(receipt_path, receipt)
    # Durable exact context precedes invocation; only the final answer is retained.
    with (directory / "context.json").open("xb") as handle:
        handle.write(canonical_bytes(context)); handle.flush(); os.fsync(handle.fileno())
    descriptor = os.open(directory, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    try:
        version = runner(["codex", "--version"], input="", capture_output=True, text=True,
                         encoding="utf-8", timeout=30, check=False)
        if version.returncode != 0 or not re.fullmatch(r"codex-cli [A-Za-z0-9.+_-]+", version.stdout.strip()):
            receipt.update(status="failed", model_invoked=False, failure_reason="codex_version_unavailable", completed_at_utc=now())
            _save(receipt_path, receipt)
            return {"run_directory": str(directory), "receipt_path": str(receipt_path), **receipt}
        receipt["codex_cli_version"] = version.stdout.strip()
        _save(receipt_path, receipt)
        with tempfile.TemporaryDirectory(prefix="turbo-real-batch-") as temporary:
            work = Path(temporary)
            schema_path, final_path = work / "schema.json", work / "output.json"
            schema_path.write_bytes(schema)
            (work / "context.json").write_bytes(context_bytes)
            command = ["codex", "-a", "never", "-s", "read-only", "-C", str(work),
                "exec", "--ephemeral", "--skip-git-repo-check", "--json", "--output-schema", str(schema_path),
                "--output-last-message", str(final_path)]
            if model is not None: command.extend(["-m", model])
            if reasoning_effort is not None: command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
            command.append("-")
            result = runner(command, input=runtime_prompt, capture_output=True, text=True,
                            encoding="utf-8", timeout=timeout_seconds, check=False)
            receipt.update(exit_code=result.returncode,
                stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
                stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest(),
                usage=_usage(result.stdout))
            if result.returncode != 0:
                receipt.update(status="failed", failure_reason=_error_category(result.stdout, result.stderr))
            elif not final_path.exists():
                receipt.update(status="invalid", failure_reason="missing_final_output")
            elif final_path.stat().st_size > DEFAULT_MAX_OUTPUT_BYTES:
                receipt.update(status="invalid", failure_reason="oversize_final_output")
            else:
                final_raw = final_path.read_bytes()
                destination = directory / "output.json"
                with destination.open("xb") as handle:
                    handle.write(final_raw); handle.flush(); os.fsync(handle.fileno())
                verdict = validate_batch_output_file(destination, preparation_dirs,
                    expected_request_id=context["request_id"], expected_invocation_id=context["invocation_id"], root=root)
                receipt.update(model_invoked=True, output_sha256=hashlib.sha256(final_raw).hexdigest(),
                    validation=verdict, status="valid" if verdict["valid"] else "invalid")
    except subprocess.TimeoutExpired:
        receipt.update(status="uncertain", failure_reason="codex_timeout")
    except BaseException as error:
        receipt.update(status="uncertain", failure_reason="invocation_interrupted_or_failed")
        receipt["completed_at_utc"] = now()
        _save(receipt_path, receipt)
        if not isinstance(error, Exception):
            raise
    receipt["completed_at_utc"] = now()
    _save(receipt_path, receipt)
    return {"run_directory": str(directory), "receipt_path": str(receipt_path), **receipt}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path)
    parser.add_argument("preparation_dirs", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--model", help="Optional explicitly selected model; otherwise preserve CLI default")
    parser.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high", "xhigh"])
    args = parser.parse_args(argv)
    try:
        result = run_batch(args.context, args.preparation_dirs, args.output_root, timeout_seconds=args.timeout_seconds, model=args.model, reasoning_effort=args.reasoning_effort)
        print(json.dumps({key: result[key] for key in ("status", "run_directory", "receipt_path")}, indent=2))
        return 0 if result["status"] == "valid" else 1
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "reason": "input_validation_or_existing_invocation"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
