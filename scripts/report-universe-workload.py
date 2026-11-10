#!/usr/bin/env python3
"""Print a closure-aware technical workload report; no model calls or writes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from turbo.universe.workload_envelope import build_report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publication-manifest', action='append', required=True)
    parser.add_argument('--scenario', type=Path, help='Explicit assumption scenario JSON; omitted by default')
    args = parser.parse_args()
    try:
        scenario = json.loads(args.scenario.read_text()) if args.scenario else None
        print(json.dumps(build_report(root=ROOT, publication_manifests=args.publication_manifest, scenario=scenario), indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
