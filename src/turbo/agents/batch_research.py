"""Simulation-only bridge between managed accounting and structural B3 output.

Float-valued research output lives in immutable artifacts, never in the legacy
integer-only journal. Accounting settlement is not research approval or activation.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

from turbo.agents.batch_authorization import canonical_bytes, utc_datetime, utc_now
from turbo.agents.batch_output import (
    DEFAULT_MAX_CONTEXT_BYTES, DEFAULT_MAX_OUTPUT_BYTES, PROMPT_PATH, SCHEMA_PATH,
    _strict_json, _validate_against_context, build_batch_context,
)
from turbo.agents.batch_registry import BatchRegistry, validate_registry_execution
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT

ARTIFACT_KIND = "batch_research_artifact_v1"
MAX_RECEIPT_BYTES = 4_000_000


def research_contract_sha256(*, root: Path = ROOT) -> str:
    """Effective execution contract stored in the existing authorization prompt slot.

    B3 context.prompt_sha256 continues to identify the raw prompt file. B4 admission
    additionally binds the output schema and byte limits without altering B1 schemas.
    """
    return canonical_sha256({"kind": ARTIFACT_KIND,
        "prompt_sha256": hashlib.sha256((root / PROMPT_PATH).read_bytes()).hexdigest(),
        "output_schema_sha256": hashlib.sha256((root / SCHEMA_PATH).read_bytes()).hexdigest(),
        "max_output_bytes": DEFAULT_MAX_OUTPUT_BYTES,
        "max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES})


def research_invocation_id(authorization_sha256: str, request_id: str) -> str:
    if not isinstance(authorization_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", authorization_sha256):
        raise ValueError("invalid authorization digest")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id):
        raise ValueError("invalid request identifier")
    return "invocation:" + canonical_sha256({"contract": ARTIFACT_KIND,
        "authorization_sha256": authorization_sha256, "request_id": request_id})[:24]


def _relative(invocation_id: str) -> str:
    return "research-artifacts/" + invocation_id.removeprefix("invocation:")


def _regular(path: Path, *, directory: bool = False) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError("required research artifact path is missing") from error
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError("research artifact paths must be regular and not symlinks")


def _read(path: Path, limit: int) -> bytes:
    _regular(path)
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("research artifact exceeds its byte limit")
    return raw


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _usage(value: Any, auth: dict[str, Any]) -> tuple[dict[str, int], int]:
    if not isinstance(value, dict) or set(value) != {"input_tokens", "output_tokens"}:
        raise ValueError("usage is unknown or malformed")
    for kind in ("input", "output"):
        number = value[kind + "_tokens"]
        if type(number) is not int or not 0 <= number <= auth["max_" + kind + "_tokens"]:
            raise ValueError("usage is unknown, noninteger, or beyond reservation")
    cost = (value["input_tokens"] * auth["pricing"]["input_microusd_per_token"]
            + value["output_tokens"] * auth["pricing"]["output_microusd_per_token"])
    return dict(value), cost


def _verdict(raw: bytes, context: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        output = _strict_json(raw)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {"valid": False, "errors": ["output is not strict finite UTF-8 JSON"]}
    errors = _validate_against_context(output, context, root=root)
    return {"valid": not errors, "errors": errors}


def _receipt(
    *, auth_digest: str, registry_id: str, request_id: str, context: dict[str, Any],
    raw: bytes, usage: dict[str, int], cost: int, verdict: dict[str, Any], created_at: str,
    execution_contract_sha256: str,
) -> dict[str, Any]:
    utc_datetime(created_at)
    return {"schema_version": 1, "kind": ARTIFACT_KIND,
        "authorization_sha256": auth_digest, "registry_id": registry_id,
        "execution_contract_sha256": execution_contract_sha256,
        "request_id": request_id, "invocation_id": context["invocation_id"],
        "context_sha256": context["context_sha256"],
        "context_file_sha256": hashlib.sha256(canonical_bytes(context)).hexdigest(),
        "output_sha256": hashlib.sha256(raw).hexdigest(), "output_bytes": len(raw),
        "output_schema_sha256": context["output_schema_sha256"], "prompt_sha256": context["prompt_sha256"],
        "usage": dict(usage), "cost_microusd": cost, "verdict": verdict,
        "outcome": "succeeded" if verdict["valid"] else "failed", "created_at_utc": created_at,
        "structural_validation_only": True, "model_invoked": False}


def _reference(receipt: dict[str, Any]) -> dict[str, str]:
    return {"kind": ARTIFACT_KIND, "artifact_path": _relative(receipt["invocation_id"]),
        "receipt_sha256": hashlib.sha256(canonical_bytes(receipt)).hexdigest(),
        "output_sha256": receipt["output_sha256"], "context_sha256": receipt["context_sha256"],
        "invocation_id": receipt["invocation_id"]}


def _persist_artifact(journal: Path, context: dict[str, Any], raw: bytes, receipt: dict[str, Any]) -> None:
    """Publish all three files together; interrupted temporary files are not output."""
    context_bytes, receipt_bytes = canonical_bytes(context), canonical_bytes(receipt)
    if (len(raw) > DEFAULT_MAX_OUTPUT_BYTES or len(context_bytes) > DEFAULT_MAX_CONTEXT_BYTES
            or len(receipt_bytes) > MAX_RECEIPT_BYTES):
        raise ValueError("artifact persistence byte limit exceeded")
    _regular(journal, directory=True)
    _regular(journal / ".lock")
    with (journal / ".lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        parent = journal / "research-artifacts"
        if not parent.exists() and not parent.is_symlink():
            parent.mkdir()
            _fsync_dir(journal)
        _regular(parent, directory=True)
        destination = journal / _relative(receipt["invocation_id"])
        if destination.exists() or destination.is_symlink():
            raise ValueError("research artifact already exists; it must not be overwritten")
        temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=parent))
        try:
            for name, value in (("context.json", context_bytes), ("output.raw", raw), ("receipt.json", receipt_bytes)):
                with (temporary / name).open("xb") as handle:
                    handle.write(value); handle.flush(); os.fsync(handle.fileno())
            _fsync_dir(temporary)
            temporary.rename(destination)
            _fsync_dir(parent)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def _contract_matches(auth: dict[str, Any], root: Path) -> None:
    if auth["prompt_sha256"] != research_contract_sha256(root=root):
        raise ValueError("authorization does not bind the current batch research execution contract")


def validate_batch_research(
    registry_dir: Path, authorization_sha256: str, preparation_dirs: Iterable[Path], *, root: Path = ROOT,
) -> dict[str, Any]:
    """Read-only replay of managed accounting and every settled B4 artifact."""
    result: dict[str, Any] = {"valid": False, "errors": [], "settled_requests": 0,
        "artifact_valid_requests": 0, "structurally_valid_outputs": 0,
        "unresolved_requests": 0, "structural_validation_only": True, "model_invoked": False}
    try:
        preparations = [Path(path) for path in preparation_dirs]
        state = validate_registry_execution(registry_dir, authorization_sha256, preparations, root=root)
        registry = BatchRegistry(registry_dir, root=root)
        journal = registry.directory / "journals" / authorization_sha256
        auth = _strict_json(_read(journal / "authorization.json", MAX_RECEIPT_BYTES))
        if canonical_sha256(auth) != authorization_sha256:
            raise ValueError("research authorization binding mismatch")
        _contract_matches(auth, root)
        for request_id, request in state["requests"].items():
            if request["status"] in {"dispatched", "unresolved"}:
                result["unresolved_requests"] += 1
            if request["status"] not in {"succeeded", "failed"}:
                continue
            result["settled_requests"] += 1
            response = request["response"]
            reference = response["output"]
            if not isinstance(reference, dict) or reference.get("kind") != ARTIFACT_KIND:
                raise ValueError("settled request has no B4 research artifact")
            invocation = research_invocation_id(authorization_sha256, request_id)
            directory = journal / _relative(invocation)
            _regular(journal / "research-artifacts", directory=True)
            _regular(directory, directory=True)
            if {path.name for path in directory.iterdir()} != {"context.json", "output.raw", "receipt.json"}:
                raise ValueError("research artifact file set mismatch")
            receipt_bytes = _read(directory / "receipt.json", MAX_RECEIPT_BYTES)
            receipt = _strict_json(receipt_bytes)
            if not isinstance(receipt, dict) or receipt_bytes != canonical_bytes(receipt):
                raise ValueError("research receipt is not a canonical object")
            if reference.get("receipt_sha256") != hashlib.sha256(receipt_bytes).hexdigest():
                raise ValueError("research receipt hash differs from journal")
            context = build_batch_context(preparations, request_id=request_id, invocation_id=invocation, root=root)
            if _read(directory / "context.json", DEFAULT_MAX_CONTEXT_BYTES) != canonical_bytes(context):
                raise ValueError("stored context does not equal verified regeneration")
            raw = _read(directory / "output.raw", DEFAULT_MAX_OUTPUT_BYTES)
            usage, cost = _usage(response["usage"], auth)
            verdict = _verdict(raw, context, root)
            expected = _receipt(auth_digest=authorization_sha256, registry_id=state["registry_id"],
                request_id=request_id, context=context, raw=raw, usage=usage, cost=cost,
                verdict=verdict, created_at=receipt.get("created_at_utc"),
                execution_contract_sha256=auth["prompt_sha256"])
            if receipt != expected or reference != _reference(expected):
                raise ValueError("research artifact receipt or reference cannot replay")
            if response["outcome"] != expected["outcome"] or request["status"] != expected["outcome"] or request["cost_microusd"] != cost:
                raise ValueError("research outcome or cost differs from journal settlement")
            result["artifact_valid_requests"] += 1
            result["structurally_valid_outputs"] += int(verdict["valid"])
        result.update(valid=True, committed_microusd=state["committed_microusd"],
                      outstanding_microusd=state["outstanding_microusd"], calls_reserved=state["calls_reserved"])
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        result["errors"].append("batch research cannot replay: " + str(error))
    return result


class BatchResearch:
    """Managed simulation facade; accepts paths and exact inputs, not a supplied ledger."""
    def __init__(self, registry_dir: Path, authorization: dict[str, Any], preparation_dirs: Iterable[Path], *,
                 root: Path = ROOT, clock: Callable[[], str] = utc_now):
        self._root = Path(root).resolve(strict=True)
        self._authorization = copy.deepcopy(authorization)
        self._preparations = tuple(Path(path).resolve(strict=True) for path in preparation_dirs)
        self._clock = clock
        _contract_matches(self._authorization, self._root)
        self._digest = canonical_sha256(self._authorization)
        self._registry = BatchRegistry(registry_dir, root=self._root)
        self._registry_path = self._registry.directory
        self._managed = self._registry.open(self._authorization, self._preparations, clock=clock)
        self._journal = self._registry_path / "journals" / self._digest

    def _check(self) -> dict[str, Any]:
        if (self._registry.directory != self._registry_path or self._registry.root.resolve(strict=True) != self._root
                or canonical_sha256(self._authorization) != self._digest
                or self._managed._registry.directory != self._registry_path
                or self._managed._digest != self._digest
                or self._managed._execution.directory.resolve(strict=True) != self._journal
                or self._managed._execution.root.resolve(strict=True) != self._root
                or tuple(Path(path).resolve(strict=True) for path in self._managed._execution.preparation_dirs) != self._preparations):
            raise ValueError("research facade is not bound to its canonical registry, inputs and journal")
        _contract_matches(self._authorization, self._root)
        return self._managed.status()

    def validate(self) -> dict[str, Any]:
        self._check()
        return validate_batch_research(self._registry_path, self._digest, self._preparations, root=self._root)

    def run(self, request_id: str, worker_id: str, transport: Callable[[dict[str, Any]], dict[str, Any]], *,
            retry_of: str | None = None) -> dict[str, Any]:
        invocation = research_invocation_id(self._digest, request_id)
        state = self._check()
        if any(row["status"] in {"succeeded", "failed"} for row in state["requests"].values()):
            replay = self.validate()
            if not replay["valid"]:
                raise ValueError("settled research artifact cannot replay: " + "; ".join(replay["errors"]))
        existing = state["requests"].get(request_id)
        if existing is not None:
            if existing["worker_id"] != worker_id or existing["retry_of"] != retry_of:
                raise ValueError("request belongs to another worker or retry chain")
            if existing["status"] != "reserved":
                return copy.deepcopy(existing)
        context = build_batch_context(self._preparations, request_id=request_id, invocation_id=invocation, root=self._root)
        self._managed.reserve(request_id, worker_id, retry_of)

        def invoke(envelope: dict[str, Any]) -> dict[str, Any]:
            current = self._check()
            expected_families = [(row["family_id"], row["preparation_id"], row["input_pack_sha256"]) for row in context["families"]]
            actual_families = [(row["family_id"], row["preparation_id"], row["pack"]["metadata"]["pack_sha256"]) for row in envelope["families"]]
            if (envelope["authorization_sha256"] != self._digest or envelope["request_id"] != request_id
                    or envelope["provider"] != "simulation" or envelope["role"] != "batch_primary"
                    or envelope["model"] != self._authorization["model"]
                    or envelope["prompt_sha256"] != self._authorization["prompt_sha256"]
                    or envelope["max_input_tokens"] != self._authorization["max_input_tokens"]
                    or envelope["max_output_tokens"] != self._authorization["max_output_tokens"]
                    or actual_families != expected_families):
                raise ValueError("managed transport envelope does not match verified research context")
            response = transport(copy.deepcopy(context))
            if not isinstance(response, dict) or set(response) != {"body", "usage"}:
                raise ValueError("fake transport response requires exact body and usage fields")
            usage, cost = _usage(response["usage"], self._authorization)
            raw = response["body"]
            if type(raw) is not bytes or len(raw) > DEFAULT_MAX_OUTPUT_BYTES:
                raise ValueError("raw output is missing or exceeds the bounded artifact size")
            fresh = build_batch_context(self._preparations, request_id=request_id, invocation_id=invocation, root=self._root)
            if fresh != context:
                raise ValueError("research inputs changed during simulation")
            verdict = _verdict(raw, fresh, self._root)
            receipt = _receipt(auth_digest=self._digest, registry_id=current["registry_id"],
                request_id=request_id, context=fresh, raw=raw, usage=usage, cost=cost,
                verdict=verdict, created_at=self._clock(),
                execution_contract_sha256=self._authorization["prompt_sha256"])
            self._check()
            _persist_artifact(self._journal, fresh, raw, receipt)
            return {"outcome": receipt["outcome"], "output": _reference(receipt), "usage": usage}

        request = self._managed.dispatch(request_id, worker_id, invoke)
        if request["status"] in {"succeeded", "failed"}:
            replay = self.validate()
            if not replay["valid"]:
                raise ValueError("settled research artifact cannot replay: " + "; ".join(replay["errors"]))
        return request
