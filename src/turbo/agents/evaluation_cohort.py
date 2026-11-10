"""Read-only admission of six fresh evaluation units with fixed budget ceilings.

This is a planning receipt, never execution authority or a shared spend ledger.
"""
from pathlib import Path
from turbo.agents import evaluation_execution as runtime

KIND = 'governed-six-submodel-cohort-plan-v1'
CATALOG = 'config/evaluation/calibration/service-cohort-v0.1/calibration-manifest.json'


def _resolved(value):
    if not isinstance(value, str):
        raise ValueError('explicit absolute path required')
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        raise ValueError('resolved absolute path required')
    return path


def _fresh_registry(path):
    if not path.exists():
        if path.is_symlink():
            raise ValueError('registry alias is not permitted')
        return
    runtime.ledger._registry(path)
    if {p.name for p in path.iterdir()} != {'registry.json', '.lock', 'claims', 'journals'}:
        raise ValueError('registry has existing ownership or unknown state')
    for name in ('claims', 'journals'):
        directory = path / name
        runtime.ledger._regular(directory, True)
        if any(directory.iterdir()):
            raise ValueError('registry has prior claims or journal exposure')


def preflight(manifest):
    """Validate operator-supplied fresh plans/authorities without writing anything.

    Authority hashes use the runtime canonical JSON hash. Artifact/catalog hashes
    use exact file bytes. Existing execution state is deliberately unsupported.
    """
    if (not isinstance(manifest, dict) or set(manifest) != {
            'schema_version', 'kind', 'calibration_manifest_sha256',
            'max_cost_microusd', 'units'} or type(manifest['schema_version']) is not int
            or manifest['schema_version'] != 1 or manifest['kind'] != KIND):
        raise ValueError('exact cohort manifest required')
    cap = manifest['max_cost_microusd']
    if type(cap) is not int or cap < 0:
        raise ValueError('nonnegative integer cohort ceiling required')
    catalog_path = runtime.ROOT / CATALOG
    if runtime.packaging._file_sha(catalog_path) != manifest['calibration_manifest_sha256']:
        raise ValueError('calibration manifest changed')
    catalog = runtime._read(catalog_path)
    registered = {r['submodel_version_id']: r for r in catalog['submodel_artifacts']}
    units = manifest['units']
    if len(registered) != 6 or not isinstance(units, list) or len(units) != 6:
        raise ValueError('exact six registered submodels required')
    seen = {k: set() for k in ('submodel', 'directory', 'registry', 'plan', 'authority')}
    common = None
    rows = []
    total = 0
    start, end = None, None
    for item in units:
        if not isinstance(item, dict) or set(item) != {
                'submodel_version_id', 'work_unit_dir', 'plan_sha256',
                'authority_path', 'authority_sha256'}:
            raise ValueError('exact child bindings required')
        submodel = item['submodel_version_id']
        if not isinstance(submodel, str) or submodel not in registered:
            raise ValueError('unregistered submodel')
        directory = _resolved(item['work_unit_dir'])
        authority_path = _resolved(item['authority_path'])
        runtime.ledger._regular(authority_path)
        plan = runtime.load_plan(directory)
        if plan['kind'] != runtime.EVALUATION_KIND or plan['submodel_version_id'] != submodel:
            raise ValueError('child submodel mismatch')
        authority = runtime._read(authority_path)
        plan_hash, auth_hash = runtime._sha(plan), runtime.ledger._hash(authority)
        if plan_hash != item['plan_sha256'] or auth_hash != item['authority_sha256']:
            raise ValueError('child plan or authority hash mismatch')
        registry = _resolved(plan['registry_path'])
        identities = {'submodel': submodel, 'directory': str(directory),
                      'registry': str(registry), 'plan': plan_hash, 'authority': auth_hash}
        for key, value in identities.items():
            if value in seen[key]:
                raise ValueError('duplicate cohort ' + key)
            seen[key].add(value)
        # A registry may be absent or explicitly initialized but completely unused.
        # Any journal/claim, including another authority's, is prior exposure.
        _fresh_registry(registry)
        if any((directory / name).exists() or (directory / name).is_symlink()
               for name in ('execution-owner.json', 'execution-authority.json', '.execution.lock')):
            raise ValueError('initialized child is outside fresh planning scope')
        registered_factor = runtime.ROOT / registered[submodel]['path']
        expected = registered[submodel]['sha256']
        if (runtime.packaging._file_sha(registered_factor) != expected
                or plan['files'][plan['factors']] != expected):
            raise ValueError('registered factor bytes changed')
        factor = runtime._artifact(directory, plan, 'factors')
        if any(f['model_policy'] != catalog['task_model_policy'] for f in factor['factors']):
            raise ValueError('registered task model policy changed')
        # These are the same real eligibility and exact-authority checks used by
        # the execution adapter. No caller-supplied eligibility flag is accepted.
        runtime._validated_input(directory, plan)
        runtime._authority(directory, plan, authority)
        scope = {'market_version_ids': plan['market_version_ids'],
                 'evidence_cutoff': plan['evidence_cutoff'],
                 **{key: plan['files'][plan[key]]
                    for key in ('graph', 'strategy', 'evidence', 'eligibility')}}
        if common is not None and common != scope:
            raise ValueError('cohort graph strategy evidence eligibility or market scope differs')
        common = scope
        a = runtime.ledger.utc_datetime(authority['valid_from_utc'])
        b = runtime.ledger.utc_datetime(authority['expires_at_utc'])
        start, end = max(start, a) if start else a, min(end, b) if end else b
        total += authority['max_cost_microusd']
        rows.append({**item, 'registry_path': str(registry),
                     'max_cost_microusd': authority['max_cost_microusd'],
                     'max_calls': authority['max_calls']})
    if seen['submodel'] != set(registered):
        raise ValueError('exact six registered submodels required')
    if total > cap:
        raise ValueError('child ceilings exceed cohort ceiling')
    if start >= end:
        raise ValueError('child authority validity windows do not overlap')
    return {'kind': KIND, 'status': 'VALIDATED_FRESH_COHORT_PLAN',
            'manifest_sha256': runtime._sha(manifest), 'execution_enabled': False,
            'creates_authority': False, 'global_ranking': False,
            'max_cost_microusd': cap, 'allocated_microusd': total,
            'unallocated_microusd': cap - total, 'maximum_calls': sum(r['max_calls'] for r in rows),
            'common_scope': common, 'units': rows,
            'limitations': ['No registry initialization, dispatch, scheduling or accounting replay.',
                'Only absent or initialized unused registries; prior exposure cannot be included or recycled.',
                'No automatic budget reallocation or global weights.',
                'Child execution preflight, current authority validity, live endpoints and request fit remain required.',
                'Ceiling is an operator-declared allocation, not proof of approval or permission to spend.',
                'Receipt is point-in-time; prior trial spend elsewhere is outside this fresh allocation, not zero.']}


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        result = preflight(runtime._read(args.manifest))
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({'status': 'INVALID_OR_BLOCKED_COHORT_PLAN', 'execution_enabled': False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
