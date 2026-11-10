#!/usr/bin/env python3
"""Default read-only preflight; execution requires external authority and one cell."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from turbo.agents import reviewer_qualification as qualification

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--authority', type=Path)
    p.add_argument('--registry', type=Path)
    p.add_argument('--cell', choices=list(qualification.CELLS))
    p.add_argument('--execute', action='store_true')
    p.add_argument('--report', action='store_true')
    a = p.parse_args()
    try:
        if a.execute and a.report: raise ValueError('choose execution or read-only report')
        authority = qualification.read(a.authority) if a.authority else None
        if a.execute:
            if authority is None or a.registry is None or a.cell is None:
                raise ValueError('execution requires authority, dedicated registry and one exact cell')
            result = qualification.run_cell(a.bundle, authority, a.registry, a.cell,
                execute=True, api_key=os.environ.get('OPENROUTER_API_KEY'))
        elif a.report:
            if authority is None or a.registry is None: raise ValueError('report requires authority and registry')
            result = qualification.comparison(a.bundle, authority, a.registry)
        else:
            result = qualification.preflight(a.bundle, authority, registry=a.registry)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError):
        # Do not echo credential-bearing exception details or raw provider text.
        print(json.dumps({'kind': qualification.KIND, 'status': 'refused', 'error': 'qualification_preflight_or_execution_failed'}))
        raise SystemExit(1)
