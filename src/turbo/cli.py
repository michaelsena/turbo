from __future__ import annotations

import argparse
import json
from pathlib import Path

from turbo.pipeline import GENERATED, run, validate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="turbo", description="Turbo market research engine")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Build and score the current market universe")
    commands.add_parser("validate", help="Validate immutable inputs and market hierarchy")
    context = commands.add_parser("context", help="Render a narrow current context view")
    context.add_argument("--limit", type=int, default=10)
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

