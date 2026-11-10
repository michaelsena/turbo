#!/usr/bin/env python3
"""Explicit serial controller; default invocation only reads current status."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from turbo.agents import batch_controller as controller
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
g=p.add_mutually_exclusive_group();g.add_argument('--initialize',action='store_true');g.add_argument('--execute',action='store_true');g.add_argument('--publish',action='store_true')
p.add_argument('--workflow',type=Path);p.add_argument('--registry',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--input-root',type=Path);p.add_argument('--preparation-dirs',nargs='+',type=Path);p.add_argument('--release-config',type=Path);p.add_argument('--publication-config',type=Path)
a=p.parse_args()
try:
 if a.publication_config and not a.publish:p.error('publication config requires publish')
 if a.initialize:
  if any(x is None for x in (a.workflow,a.registry,a.authorization,a.input_root)):p.error('initialize requires workflow, registry, authorization and input-root')
  v=controller.initialize(a.directory.resolve(),workflow_dir=a.workflow.resolve(),registry_dir=a.registry.resolve(),authorization=json.loads(a.authorization.read_text()),input_root=a.input_root.resolve(),preparation_dirs=[x.resolve() for x in a.preparation_dirs] if a.preparation_dirs else None);result={'state':'INITIALIZED','manifest_sha256':v['manifest_sha256']}
 elif a.publish:
  from turbo.agents.batch_publication import publish
  if a.release_config:p.error('release config requires execute')
  result=publish(a.directory.resolve(),config_path=a.publication_config.resolve() if a.publication_config else None)
 elif a.execute:result=controller.execute(a.directory.resolve(),api_key=os.environ.get('OPENROUTER_API_KEY'),release_config=a.release_config.resolve() if a.release_config else None)
 else:
  if a.release_config:p.error('release config requires execute')
  result=controller.status(a.directory.resolve())
 print(json.dumps(result,indent=2));raise SystemExit(1 if result.get('state')=='STOPPED' else 0)
except Exception as error:
 print(json.dumps({'state':'STOPPED','reason':'controller_validation_error','error_type':type(error).__name__}));raise SystemExit(1)
