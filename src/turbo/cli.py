from __future__ import annotations

import argparse
import json
from pathlib import Path

from turbo.agents.batch_authorization import validate_authorization
from turbo.agents.batch_execution import inspect_execution, validate_execution
from turbo.agents.batch_registry import (
    initialize_registry,
    inspect_registry,
    validate_registry_execution,
)
from turbo.agents.batch_output import build_batch_context, validate_batch_output_file

from turbo.agents.boundary_runner import run_boundary_pilot, validate_boundary_run
from turbo.agents.boundary_review import (
    run_independent_review,
    validate_independent_review_run,
)
from turbo.pipeline import run, validate
from turbo.pipeline_paths import ROOT
from turbo.system_context import compile_system_context
from turbo.universe.boundary_activation import (
    run_boundary_activation,
    validate_boundary_activation,
)
from turbo.universe.graph_release import run_graph_release, validate_graph_release
from turbo.universe.family_scheduler import run_family_plan, validate_family_plan
from turbo.universe.family_pack_v2 import (
    dry_run_family_preparation_v2,
    prepare_family_v2,
    validate_family_preparation_v2,
)
from turbo.universe.boundary_pack import (
    build_boundary_pack,
    validate_boundary_pack,
    write_boundary_pack,
)


DEFAULT_BOUNDARY_CONFIG = (
    ROOT / "config/universe/families/office-administrative-services-v1.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="turbo", description="Turbo market research engine")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Build the source universe and reconciliation worklist")
    commands.add_parser("validate", help="Validate immutable inputs and market hierarchy")
    commands.add_parser("context", help="Render the current run receipt")
    batch_dry_run = commands.add_parser(
        "batch-dry-run", help="Validate a simulation authorization and exact V2 batch inputs; no dispatch"
    )
    batch_dry_run.add_argument("authorization", type=Path)
    batch_dry_run.add_argument("preparation_dirs", type=Path, nargs="+")
    batch_status = commands.add_parser(
        "batch-status", help="Read and replay a simulation execution journal without changing it"
    )
    batch_status.add_argument("execution_dir", type=Path)
    batch_validate = commands.add_parser(
        "batch-validate-execution", help="Replay a simulation journal against exact V2 preparations"
    )
    batch_validate.add_argument("execution_dir", type=Path)
    batch_validate.add_argument("preparation_dirs", type=Path, nargs="+")
    registry_init = commands.add_parser(
        "batch-registry-init", help="Explicitly initialize a new trusted local simulation registry"
    )
    registry_init.add_argument("registry_dir", type=Path)
    registry_status = commands.add_parser(
        "batch-registry-status", help="Inspect existing registered journals without changing them"
    )
    registry_status.add_argument("registry_dir", type=Path)
    registry_validate = commands.add_parser(
        "batch-registry-validate", help="Replay one registered simulation journal against exact preparations"
    )
    registry_validate.add_argument("registry_dir", type=Path)
    registry_validate.add_argument("authorization_sha256")
    registry_validate.add_argument("preparation_dirs", type=Path, nargs="+")
    output_context = commands.add_parser(
        "batch-output-context", help="Render a verified batch output contract context without model calls"
    )
    output_context.add_argument("request_id")
    output_context.add_argument("invocation_id")
    output_context.add_argument("preparation_dirs", type=Path, nargs="+")
    output_context.add_argument("--max-output-bytes", type=int, default=1_000_000)
    output_validate = commands.add_parser(
        "batch-output-validate", help="Validate proposed output against regenerated exact batch inputs"
    )
    output_validate.add_argument("output_file", type=Path)
    output_validate.add_argument("request_id")
    output_validate.add_argument("invocation_id")
    output_validate.add_argument("preparation_dirs", type=Path, nargs="+")
    output_validate.add_argument("--max-output-bytes", type=int, default=1_000_000)
    graph_release = commands.add_parser(
        "graph-release",
        help="Publish a cumulative canonical Market Graph from approved activations",
    )
    graph_release.add_argument("config", type=Path)
    graph_release.add_argument("--output-root", type=Path)
    graph_validate = commands.add_parser(
        "graph-validate-release",
        help="Replay a persisted cumulative canonical Market Graph release",
    )
    graph_validate.add_argument("release_dir", type=Path)
    graph_validate.add_argument("config", type=Path)
    family_plan = commands.add_parser(
        "family-plan",
        help="Compile and publish the deterministic operating-family schedule",
    )
    family_plan.add_argument("config", type=Path)
    family_plan.add_argument("--output-root", type=Path)
    family_validate = commands.add_parser(
        "family-validate-plan",
        help="Replay a persisted deterministic operating-family schedule",
    )
    family_validate.add_argument("schedule_dir", type=Path)
    family_validate.add_argument("config", type=Path)
    family_prepare = commands.add_parser(
        "family-prepare",
        help="Prepare a content-addressed V2 family config and evidence pack without model calls",
    )
    family_prepare.add_argument("family_id")
    family_prepare.add_argument("--output-root", type=Path)
    family_dry_run = commands.add_parser(
        "family-dry-run",
        help="Compile and validate one V2 family preparation without persisting or invoking a model",
    )
    family_dry_run.add_argument("family_id")
    family_validate_preparation = commands.add_parser(
        "family-validate-preparation",
        help="Replay a persisted V2 family preparation against exact immutable inputs",
    )
    family_validate_preparation.add_argument("preparation_dir", type=Path)
    boundary_pack = commands.add_parser(
        "boundary-pack",
        help="Compile and validate a frozen operating-market family evidence pack",
    )
    boundary_pack.add_argument("--config", type=Path, default=DEFAULT_BOUNDARY_CONFIG)
    boundary_pack.add_argument("--output", type=Path)
    boundary_run = commands.add_parser(
        "boundary-run",
        help="Run two blind boundary specialists and the mandatory adjudicator",
    )
    boundary_run.add_argument("--config", type=Path, default=DEFAULT_BOUNDARY_CONFIG)
    boundary_run.add_argument("--output-root", type=Path)
    boundary_run.add_argument("--timeout-seconds", type=int, default=1800)
    boundary_validate = commands.add_parser(
        "boundary-validate-run",
        help="Replay validation for a persisted boundary run",
    )
    boundary_validate.add_argument("run_dir", type=Path)
    boundary_validate.add_argument("--config", type=Path, default=DEFAULT_BOUNDARY_CONFIG)
    boundary_review = commands.add_parser(
        "boundary-review",
        help="Run a preregistered independent review of a persisted boundary run",
    )
    boundary_review.add_argument("review_config", type=Path)
    boundary_review.add_argument("--config", type=Path, default=DEFAULT_BOUNDARY_CONFIG)
    boundary_review.add_argument("--output-root", type=Path)
    boundary_review.add_argument("--timeout-seconds", type=int, default=1800)
    boundary_validate_review = commands.add_parser(
        "boundary-validate-review",
        help="Replay validation for a persisted independent boundary review",
    )
    boundary_validate_review.add_argument("review_dir", type=Path)
    boundary_validate_review.add_argument("review_config", type=Path)
    boundary_validate_review.add_argument(
        "--config", type=Path, default=DEFAULT_BOUNDARY_CONFIG
    )
    boundary_activate = commands.add_parser(
        "boundary-activate",
        help="Compile an approved boundary proposal into deterministic graph events",
    )
    boundary_activate.add_argument("activation_config", type=Path)
    boundary_activate.add_argument("--output-root", type=Path)
    boundary_validate_activation = commands.add_parser(
        "boundary-validate-activation",
        help="Replay a persisted deterministic boundary activation",
    )
    boundary_validate_activation.add_argument("activation_dir", type=Path)
    boundary_validate_activation.add_argument("activation_config", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command in {"batch-output-context", "batch-output-validate"}:
        try:
            if args.command == "batch-output-context":
                result = build_batch_context(
                    args.preparation_dirs, request_id=args.request_id,
                    invocation_id=args.invocation_id, max_output_bytes=args.max_output_bytes,
                )
            else:
                result = validate_batch_output_file(
                    args.output_file, args.preparation_dirs,
                    expected_request_id=args.request_id,
                    expected_invocation_id=args.invocation_id,
                    max_output_bytes=args.max_output_bytes,
                )
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(json.dumps({"valid": False, "errors": [str(error)]}, indent=2))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if result.get("valid", True) else 1
    if args.command in {"batch-registry-init", "batch-registry-status", "batch-registry-validate"}:
        try:
            if args.command == "batch-registry-init":
                result = initialize_registry(args.registry_dir)
            elif args.command == "batch-registry-status":
                result = inspect_registry(args.registry_dir)
            else:
                result = validate_registry_execution(
                    args.registry_dir, args.authorization_sha256, args.preparation_dirs
                )
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(json.dumps({"valid": False, "errors": [str(error)]}, indent=2))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("valid", True) else 1
    if args.command in {"batch-dry-run", "batch-status", "batch-validate-execution"}:
        try:
            if args.command == "batch-dry-run":
                authorization = json.loads(args.authorization.read_text(encoding="utf-8"))
                result = validate_authorization(authorization, args.preparation_dirs)
            elif args.command == "batch-status":
                result = inspect_execution(args.execution_dir)
            else:
                result = validate_execution(args.execution_dir, args.preparation_dirs)
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(json.dumps({"valid": False, "errors": [str(error)]}, indent=2))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("valid", True) else 1
    if args.command == "run":
        print(json.dumps(run(), indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        errors = validate()
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            return 1
        print(json.dumps({"valid": True, "errors": []}, indent=2))
        return 0
    if args.command == "context":
        try:
            payload = compile_system_context()
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            print(json.dumps({"error": f"Context validation failed: {error}"}, indent=2))
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "graph-release":
        print(
            json.dumps(
                run_graph_release(args.config, output_root=args.output_root),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "graph-validate-release":
        result = validate_graph_release(args.release_dir, args.config)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    if args.command == "family-plan":
        print(
            json.dumps(
                run_family_plan(args.config, output_root=args.output_root),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "family-validate-plan":
        result = validate_family_plan(args.schedule_dir, args.config)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    if args.command == "family-prepare":
        print(
            json.dumps(
                prepare_family_v2(args.family_id, output_root=args.output_root),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "family-dry-run":
        print(
            json.dumps(
                dry_run_family_preparation_v2(args.family_id),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "family-validate-preparation":
        result = validate_family_preparation_v2(args.preparation_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    if args.command == "boundary-pack":
        pack = build_boundary_pack(args.config)
        errors = validate_boundary_pack(pack)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            return 1
        if args.output:
            write_boundary_pack(pack, args.output)
        print(
            json.dumps(
                {
                    "valid": True,
                    "family_id": pack["metadata"]["family_id"],
                    "source_run_id": pack["metadata"]["source_run_id"],
                    "pack_sha256": pack["metadata"]["pack_sha256"],
                    "counts": pack["summary"]["counts"],
                    "evidence_items": len(pack["evidence_catalog"]),
                    "output": str(args.output) if args.output else None,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "boundary-run":
        print(
            json.dumps(
                run_boundary_pilot(
                    args.config,
                    output_root=args.output_root,
                    timeout_seconds=args.timeout_seconds,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "boundary-validate-run":
        result = validate_boundary_run(args.run_dir, args.config)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    if args.command == "boundary-review":
        print(
            json.dumps(
                run_independent_review(
                    args.review_config,
                    args.config,
                    output_root=args.output_root,
                    timeout_seconds=args.timeout_seconds,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "boundary-validate-review":
        result = validate_independent_review_run(
            args.review_dir, args.review_config, args.config
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    if args.command == "boundary-activate":
        print(
            json.dumps(
                run_boundary_activation(
                    args.activation_config, output_root=args.output_root
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "boundary-validate-activation":
        result = validate_boundary_activation(
            args.activation_dir, args.activation_config
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

