from __future__ import annotations

import argparse
import json
from pathlib import Path

from turbo.agents.boundary_runner import run_boundary_pilot, validate_boundary_run
from turbo.agents.boundary_review import (
    run_independent_review,
    validate_independent_review_run,
)
from turbo.pipeline import GENERATED, run, validate
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_activation import (
    run_boundary_activation,
    validate_boundary_activation,
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
        latest = Path(GENERATED) / "latest-run.json"
        if not latest.exists():
            print(json.dumps({"error": "No run exists. Execute `turbo run`."}, indent=2))
            return 1
        payload = json.loads(latest.read_text(encoding="utf-8"))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
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

