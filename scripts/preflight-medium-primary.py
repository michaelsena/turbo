#!/usr/bin/env python3
"""Replay one frozen primary assignment and print offline admission diagnostics."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from turbo.agents.batch_output import _strict_json
from turbo.agents.primary_preflight import assess_primary

# Execute the existing frozen implementation, not today's compiler over old inputs.
# assignment() performs the existing narrow preparation/context replay and reads its
# lock; no workflow or registry artifacts are created or modified.
CAPTURE = r'''
import hashlib,json,sys
from pathlib import Path
from turbo.agents import batch_workflow as w,batch_provider as p
from turbo.agents.openrouter_attempt import bounded_request_body
from turbo.agents.openrouter_runner import openrouter_role_schema
root=Path(sys.argv[1]).resolve();directory=Path(sys.argv[2]).resolve()
roles=json.loads(Path(sys.argv[3]).read_text());config=roles['primary']
task=w.assignment(directory,'primary',input_root=root)
if config['prompt_sha256']!=p.contract_bindings(input_root=root)['primary']['prompt_sha256'] or config['schema_sha256']!=p.contract_bindings(input_root=root)['primary']['schema_sha256']:
 raise ValueError('role prompt/schema binding differs from frozen input')
request=bounded_request_body(routing=config['routing'],role_id='primary',model=config['model'],reasoning_effort=config['reasoning_effort'],runtime_prompt_text=p.role_prompt(input_root=root)+'\n# Frozen assignment\n'+p._bytes(task).decode(),schema=openrouter_role_schema(p.role_schema('primary',input_root=root),role_id='primary',model=config['model']),invocation_id='invocation:'+'0'*24,max_completion_tokens=config['max_output_tokens'],allow_fallbacks=False,schema_name='turbo_workflow_role')
families=task['context']['families'];plan=json.loads((directory/'plan.json').read_text())
print(json.dumps({'role':'primary','representation':'plain','request':request,'role_config':config,'bindings':{'workflow_plan_sha256':task['plan_sha256'],'context_sha256':task['context']['context_sha256'],'assignment_sha256':p._hash(task),'input_tree':plan['input_tree'],'prompt_sha256':config['prompt_sha256'],'role_schema_sha256':config['schema_sha256'],'frozen_request_builder_sha256':hashlib.sha256((root/'src/turbo/agents/openrouter_attempt.py').read_bytes()).hexdigest()},'subjects':{'family_ids':[f['family_id'] for f in families],'required_identities':sum(len(f['required_identity_ids']) for f in families),'required_candidates':sum(len(f['required_candidate_ids']) for f in families),'evidence_items':sum(len(f['evidence_catalog']) for f in families)}}))
'''


def _verify_frozen_input(root, workflow):
    """Reject dirty or substituted frozen code before importing it in the child."""
    root = root.resolve()
    plan = _strict_json((workflow.resolve() / 'plan.json').read_bytes())
    def git(*args):
        return subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != root:
        raise ValueError('input root must be the exact Git toplevel')
    if git('rev-parse', 'HEAD^{tree}') != plan['input_tree']:
        raise ValueError('frozen input tree moved')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('frozen input checkout has tracked or untracked changes')
    return git('rev-parse', 'HEAD')


def capture_primary(root, workflow, roles):
    commit = _verify_frozen_input(root, workflow)
    env = {**os.environ, 'PYTHONPATH': str(root.resolve() / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-c', CAPTURE, str(root.resolve()),
                             str(workflow.resolve()), str(roles.resolve())],
                            cwd=root.resolve(), env=env, capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError('frozen primary assignment replay failed; no request admitted')
    capture = _strict_json(result.stdout)
    capture['bindings']['input_commit'] = commit
    return capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--workflow', type=Path, required=True)
    parser.add_argument('--roles', type=Path, required=True)
    parser.add_argument('--model-metadata', type=Path, required=True)
    parser.add_argument('--metadata-observed-at', help='Optional observation timestamp; never treated as retrieval provenance')
    parser.add_argument('--private-budget', action='store_true', help='Include hypothetical reservation arithmetic; keep output private')
    args = parser.parse_args()
    capture = capture_primary(args.input_root, args.workflow, args.roles)
    report = assess_primary(capture, _strict_json(args.model_metadata.read_bytes()),
                            metadata_observed_at=args.metadata_observed_at,
                            include_private_budget=args.private_budget)
    report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
