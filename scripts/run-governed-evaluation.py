#!/usr/bin/env python3
"""Explicit eligibility/submodel operator; read-only unless initialize or execute."""
import argparse
import json
import os
from pathlib import Path
from turbo.agents import evaluation_execution as runtime

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--initialize',type=Path,metavar='AUTHORITY_JSON')
    group.add_argument('--execute',choices=['eligibility','evaluator_a','evaluator_b','adjudicator','comparator'])
    group.add_argument('--projection',action='store_true')
    args=parser.parse_args()
    try:
        if args.initialize: result=runtime.initialize(args.input,runtime._read(args.initialize))
        elif args.execute: result=runtime.run_task(args.input,args.execute,execute=True,api_key=os.environ.get('OPENROUTER_API_KEY'))
        elif args.projection: result=runtime.projection(args.input)
        else: result=runtime.preflight(args.input)
    except (ValueError,KeyError,TypeError,OSError):
        print(json.dumps({'status':'INVALID_OR_BLOCKED_WORK_UNIT','execution_enabled':False}));return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result.get('status') not in ('failed','unresolved','reserved','dispatched') else 2

if __name__=='__main__':raise SystemExit(main())
