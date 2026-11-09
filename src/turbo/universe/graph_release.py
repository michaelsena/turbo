from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_activation import validate_boundary_activation
from turbo.universe.graph import project_graph


FULL_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{path} must contain an array of JSON objects")
    return value


def _load_gzip_object(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_worktree_clean(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def _git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and FULL_GIT_COMMIT.fullmatch(value) else None


def _git_commit_exists(root: Path, commit: str) -> bool:
    if FULL_GIT_COMMIT.fullmatch(commit) is None:
        return False
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def compile_graph_release(
    config_path: Path,
    *,
    execution_commit: str,
    root: Path = ROOT,
    input_root: Path | None = None,
    preparation_dirs=None,
) -> dict[str, Any]:
    if FULL_GIT_COMMIT.fullmatch(execution_commit) is None:
        raise ValueError("execution_commit must be a complete lowercase hexadecimal Git commit")
    config = _load_object(config_path)
    schema = _load_object(root / "schemas" / "graph-release-config.schema.json")
    schema_errors = sorted(
        error.message for error in Draft202012Validator(schema).iter_errors(config)
    )
    if schema_errors:
        raise ValueError("invalid graph release config: " + "; ".join(schema_errors))
    if config.get("schema_version") != 1:
        raise ValueError("graph release config schema_version must equal 1")
    if config.get("prohibited_actions") != [
        "target-universe filtering",
        "market evaluation or scoring",
        "company discovery or evaluation",
        "model invocation",
    ]:
        raise ValueError("graph release config prohibited_actions mismatch")
    activations = config.get("activations")
    if not isinstance(activations, list) or not activations:
        raise ValueError("graph release requires at least one activation")

    source_run_id = config.get("source_universe_run_id")
    run_dir = root / "data" / "runs" / str(source_run_id)
    run_receipt = _load_object(run_dir / "run-receipt.json")
    if run_receipt.get("run_id") != source_run_id:
        raise ValueError("graph release source run does not match its receipt")
    reconciliation_path = run_dir / "multisource-reconciliation.json.gz"
    expected_reconciliation_hash = run_receipt["output_hashes"].get(
        "multisource-reconciliation.json.gz"
    )
    if _sha256_path(reconciliation_path) != expected_reconciliation_hash:
        raise ValueError("graph release source reconciliation hash mismatch")
    reconciliation = _load_gzip_object(reconciliation_path)
    known_source_ids = {
        item["record_id"] for item in reconciliation["source_records"]
    }
    known_candidate_ids = {
        item["candidate_market_id"] for item in reconciliation["candidate_markets"]
    }

    events: list[dict[str, Any]] = []
    activation_bindings: list[dict[str, Any]] = []
    seen_activation_ids: set[str] = set()
    for item in activations:
        if not isinstance(item, dict):
            raise ValueError("graph release activation entry must be an object")
        activation_dir = _resolve(root, item["activation_dir"])
        activation_config = _resolve(root, item["activation_config"])
        is_batch = item.get("kind") == "batch"
        if is_batch:
            from turbo.universe.batch_closure import validate_batch_activation
            replay = validate_batch_activation(activation_dir, activation_config, root=root,
                                               input_root=input_root, preparation_dirs=preparation_dirs)
        else:
            replay = validate_boundary_activation(activation_dir, activation_config, root=root)
        if not replay["valid"]:
            raise ValueError(
                f"activation {activation_dir.name} failed replay: {replay['errors']}"
            )
        receipt = _load_object(activation_dir / "activation-receipt.json")
        activation_id = receipt["activation_id"]
        if activation_id in seen_activation_ids:
            raise ValueError(f"duplicate graph release activation: {activation_id}")
        seen_activation_ids.add(activation_id)
        if item.get("activation_id") != activation_id:
            raise ValueError(f"activation ID mismatch for {activation_id}")
        for field in (
            "events_sha256",
            "projection_sha256",
            "activation_config_sha256",
        ):
            if item.get(field) != receipt.get(field):
                raise ValueError(f"activation {activation_id} {field} mismatch")
        if is_batch:
            if receipt.get("source_universe_run_id") != source_run_id:
                raise ValueError("batch activation belongs to another source-universe run")
            if (sorted(e["event_id"] for e in events) != receipt["required_base_event_ids"]
                    or canonical_sha256(sorted(events, key=lambda e: e["event_id"])) != receipt["required_base_events_sha256"]):
                raise ValueError("batch activation requires its exact reviewed cumulative base")
        else:
            family_config = _load_object(
                _resolve(root, _load_object(activation_config)["source_family_config"])
            )
            if family_config.get("source_run_id") != source_run_id:
                raise ValueError(f"activation {activation_id} belongs to another source-universe run")
        activation_events = _load_array(activation_dir / "events.json")
        if canonical_sha256(activation_events) != receipt["events_sha256"]:
            raise ValueError(f"activation {activation_id} event hash mismatch")
        events.extend(activation_events)
        activation_bindings.append(
            {
                "activation_id": activation_id,
                "activation_dir": str(activation_dir.relative_to(root)),
                "activation_config": str(activation_config.relative_to(root)),
                "activation_config_sha256": receipt["activation_config_sha256"],
                "events_sha256": receipt["events_sha256"],
                "projection_sha256": receipt["projection_sha256"],
            }
        )

        if is_batch:
            activation_bindings[-1]["kind"] = "batch"

    config_sha256 = canonical_sha256(config)
    projection = project_graph(
        events,
        as_of=config["as_of_utc"],
        known_source_record_ids=known_source_ids,
        known_candidate_market_ids=known_candidate_ids,
        source_hashes=run_receipt["output_hashes"],
        config_hash=config_sha256,
        code_hash=execution_commit,
    )
    release_id = "graph-release-" + canonical_sha256(
        {
            "source_universe_run_id": source_run_id,
            "as_of_utc": config["as_of_utc"],
            "activation_bindings": activation_bindings,
            "config_sha256": config_sha256,
            "execution_commit": execution_commit,
        }
    )[:20]
    return {
        "release_id": release_id,
        "source_universe_run_id": source_run_id,
        "config_sha256": config_sha256,
        "execution_commit": execution_commit,
        "activation_bindings": activation_bindings,
        "projection": projection,
    }


def _receipt(compiled: dict[str, Any]) -> dict[str, Any]:
    projection = compiled["projection"]
    return {
        "schema_version": 1,
        "release_id": compiled["release_id"],
        "source_universe_run_id": compiled["source_universe_run_id"],
        "config_sha256": compiled["config_sha256"],
        "execution_commit": compiled["execution_commit"],
        "as_of_utc": projection["as_of"],
        "graph_version_id": projection["graph_version_id"],
        "activation_bindings": compiled["activation_bindings"],
        "projection_sha256": canonical_sha256(projection),
        "counts": {
            "activations": len(compiled["activation_bindings"]),
            "active_events": len(projection["active_event_ids"]),
            "canonical_markets": len(projection["markets"]),
            "mappings": len(projection["mappings"]),
            "retired_markets": len(projection["retired_market_ids"]),
        },
        "model_invoked": False,
        "status": "published_cumulative_canonical_graph",
    }


def run_graph_release(
    config_path: Path,
    *,
    output_root: Path | None = None,
    pointer_path: Path | None = None,
    root: Path = ROOT,
    input_root: Path | None = None,
    preparation_dirs=None,
) -> dict[str, Any]:
    if not _git_worktree_clean(root):
        raise RuntimeError(
            "graph release requires a clean Git worktree so its exact commit contains "
            "the executed compiler and configuration"
        )
    execution_commit = _git_head(root)
    if execution_commit is None:
        raise RuntimeError("cannot determine exact Git commit for graph release")
    compiled = compile_graph_release(
        config_path, execution_commit=execution_commit, root=root,
        input_root=input_root, preparation_dirs=preparation_dirs
    )
    destination = output_root or root / "data" / "market_graph" / "versions"
    release_dir = destination / compiled["release_id"]
    receipt = _receipt(compiled)
    destination.mkdir(parents=True, exist_ok=True)
    if release_dir.exists():
        raise FileExistsError(f"graph release already exists: {release_dir}")
    with tempfile.TemporaryDirectory(prefix=".graph-release-", dir=destination) as raw_temp:
        temporary_dir = Path(raw_temp)
        (temporary_dir / "projection.json").write_text(
            json.dumps(compiled["projection"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temporary_dir / "graph-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_dir.replace(release_dir)
    pointer = {
        "schema_version": 1,
        "release_id": receipt["release_id"],
        "graph_version_id": receipt["graph_version_id"],
        "source_universe_run_id": receipt["source_universe_run_id"],
        "release_path": str(release_dir.relative_to(root)),
        "receipt_sha256": canonical_sha256(receipt),
        "projection_sha256": receipt["projection_sha256"],
    }
    resolved_pointer = pointer_path or root / "data" / "generated" / "latest-graph.json"
    temporary = resolved_pointer.with_suffix(resolved_pointer.suffix + ".tmp")
    temporary.write_text(
        json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(resolved_pointer)
    return {"release_dir": str(release_dir), **receipt}


def validate_graph_release(
    release_dir: Path,
    config_path: Path,
    *,
    root: Path = ROOT,
    input_root: Path | None = None,
    preparation_dirs=None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        receipt = _load_object(release_dir / "graph-receipt.json")
        projection = _load_object(release_dir / "projection.json")
        execution_commit = receipt["execution_commit"]
        if not _git_commit_exists(root, execution_commit):
            raise ValueError("execution_commit is not a resolvable full Git commit")
        compiled = compile_graph_release(
            config_path, execution_commit=execution_commit, root=root,
        input_root=input_root, preparation_dirs=preparation_dirs
        )
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "errors": [f"graph release cannot replay: {error}"],
            "release_id": release_dir.name,
        }
    expected_receipt = _receipt(compiled)
    if projection != compiled["projection"]:
        errors.append("persisted projection does not match deterministic compilation")
    if receipt != expected_receipt:
        errors.append("persisted graph receipt does not match deterministic compilation")
    if release_dir.name != compiled["release_id"]:
        errors.append("graph release directory name does not match release_id")
    return {
        "valid": not errors,
        "errors": errors,
        "release_id": compiled["release_id"],
        "graph_version_id": compiled["projection"]["graph_version_id"],
        "canonical_markets": len(compiled["projection"]["markets"]),
    }
