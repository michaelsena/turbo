#!/usr/bin/env python3
"""Read-only Issue 86a work-unit preflight. Production execution is blocked."""
import argparse
import json
from pathlib import Path

from turbo.agents.evaluation_workflow import preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = preflight(args.input)
    except (ValueError, KeyError, TypeError, OSError):
        print(json.dumps({'status': 'INVALID_WORK_UNIT', 'execution_enabled': False}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2  # Blocked is never a successful execution/preflight gate.


if __name__ == '__main__':
    raise SystemExit(main())
