#!/usr/bin/env python3
"""Build offline qualification artifacts, never an execution authority."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from turbo.agents.reviewer_qualification_builder import build

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--source-workflow', type=Path, required=True)
    p.add_argument('--input-root', type=Path, required=True)
    p.add_argument('--reviewer-config', type=Path, required=True, help='Role settings JSON, not account metadata')
    p.add_argument('--preparation-dir', type=Path, action='append')
    a = p.parse_args()
    print(json.dumps(build(a.destination, a.source_workflow, a.input_root,
          json.loads(a.reviewer_config.read_text()), preparation_dirs=a.preparation_dir), indent=2))
