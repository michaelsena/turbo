"""Market eligibility is a separate, evidence-bound projection, never a score.

No dispatch occurs here. Production evaluation admission requires a successful
provider artifact verified by evaluation_execution, not caller-authored judgments.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator
from turbo.agents.batch_output import _strict_json
from turbo.agents.batch_authorization import utc_datetime
from turbo.universe.family_pack_v2 import _verified_graph
from turbo.universe.graph_release import validate_graph_release

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'schemas/governed-eligibility-output.schema.json'
EXPOSURES = ('healthcare_delivery', 'government_dependent_revenue',
             'heavy_equipment_ownership', 'significant_inventory',
             'insurance_or_credit_risk', 'unionized_workforces', 'reimbursement_exposure')
GATES = ('us_market_scope', 'acquisition_population_ev_range', 'buyability_feasibility', *EXPOSURES)
INSTRUCTIONS = (
    'Judge market-level strategic eligibility, not investment attractiveness or a company transaction. '
    'For every gate pass means compatible with the frozen strategy; fail means incompatible; '
    'unknown means insufficient support. For excluded exposure gates, pass means the operating '
    'market does not require that excluded exposure, never that the exposure is present. '
    'Evaluate United States scope, evidence for an acquisition population in the $10M-$50M '
    'enterprise-value range, and buyability feasibility under the hard 9x EBITDA ceiling '
    'and permitted permanent-holdco/build-and-exit ownership models. The preferred 7x-8x '
    'range is a preference, not an additional hard ceiling. Do not fabricate company prices, '
    'ownership, transactions, or due diligence; those remain mandatory deal conditions. '
    'All seven excluded exposures must be judged individually; union exposure has no exemption. '
    'Distinguish frozen source excerpts from labeled research claims. Cite market-owned '
    'source evidence, confront counterevidence, retain specific gaps and reduced confidence '
    'for inference or assumption, and do not convert unknown evidence into a pass. '
    'Return every exact market version and every required gate; do not add markets or scores.'
)

CODE = ('src/turbo/agents/governed_eligibility.py', SCHEMA,
        'src/turbo/universe/family_pack_v2.py', 'src/turbo/universe/graph_release.py',
        'src/turbo/agents/batch_output.py', 'src/turbo/agents/batch_authorization.py')


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contracts():
    return {name: _file_sha(ROOT / name) for name in CODE}


def eligibility_output_schema():
    return json.loads((ROOT / SCHEMA).read_text())


def _path(directory, name):
    if not isinstance(name, str):
        raise ValueError('artifact path must be a string')
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise ValueError('artifact path escapes work unit')
    path = Path(directory) / relative
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('missing or symlink artifact')
    if path.stat().st_size > 16_000_000:
        raise ValueError('artifact exceeds bound')
    return path


def _artifact(directory, plan, key):
    name = plan[key]
    path = _path(directory, name)
    if plan['files'].get(name) != _file_sha(path):
        raise ValueError('unbound or changed eligibility input')
    value = _strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('eligibility input must be an object')
    return value, _file_sha(path)


def _canonical_graph(descriptor):
    if set(descriptor) != {'root', 'pointer', 'config_path', 'config_sha256'}:
        raise ValueError('exact canonical graph descriptor required')
    root = Path(descriptor['root'])
    if not root.is_absolute() or str(root.resolve()) != str(root):
        raise ValueError('canonical repository root required')
    top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                         check=True, capture_output=True, text=True).stdout.strip()
    if Path(top).resolve() != root:
        raise ValueError('graph root is not Git top-level')
    pointer, receipt, projection = _verified_graph(root=root)
    if pointer != descriptor['pointer']:
        raise ValueError('canonical graph changed')
    config = _path(root, descriptor['config_path'])
    if _file_sha(config) != descriptor['config_sha256']:
        raise ValueError('graph configuration changed')
    # Do not accept a self-consistent invented pointer/receipt/projection triple.
    release = root / pointer['release_path']
    if not release.resolve().is_relative_to(root):
        raise ValueError('graph release escapes canonical root')
    replay = validate_graph_release(release, config, root=root)
    if not replay['valid']:
        raise ValueError('canonical graph cannot replay')
    return root, projection


def validate_eligibility_input(directory: Path, plan: dict) -> dict:
    """Bind published canonical versions, original strategy, and frozen evidence."""
    descriptor, graph_hash = _artifact(directory, plan, 'graph')
    root, projection = _canonical_graph(descriptor)
    strategy, strategy_hash = _artifact(directory, plan, 'strategy')
    original = _path(root, 'config/strategy.json')
    if strategy_hash != _file_sha(original):
        raise ValueError('strategy is not the exact canonical policy')
    if (set(strategy) != {'company_research_authorized', 'currency', 'evidence_boundaries',
                          'excluded_exposures', 'geography', 'ownership_models',
                          'purchase_multiple', 'target_enterprise_value', 'version'}
            or type(strategy.get('version')) is not int or strategy.get('version') != 1
            or strategy.get('company_research_authorized') is not False
            or strategy.get('currency') != 'USD'
            or strategy.get('evidence_boundaries') != {'allow_outreach': False, 'allow_paid_sources': False, 'allow_public_sources': True}
            or strategy.get('geography') != 'United States'
            or strategy.get('excluded_exposures') != list(EXPOSURES)
            or strategy.get('target_enterprise_value') != {'minimum': 10000000, 'maximum': 50000000}
            or strategy.get('purchase_multiple') != {'hard_ceiling_ebitda': 9.0,
                  'preferred_min_ebitda': 7.0, 'preferred_max_ebitda': 8.0}
            or strategy.get('ownership_models') != ['permanent_holdco', 'build_and_exit_platform']):
        raise ValueError('unsupported strategy; explicit compiler review required')
    ids = plan['market_version_ids']
    if (not isinstance(ids, list) or not ids or len(ids) > 100
            or any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids))):
        raise ValueError('exact distinct market versions required')
    catalog = {m['market_version_id']: m for m in projection['markets']}
    if any(i not in catalog for i in ids):
        raise ValueError('market version absent from accepted canonical graph')
    cutoff = utc_datetime(plan['evidence_cutoff'])
    if utc_datetime(projection['as_of']) > cutoff:
        raise ValueError('graph is later than evidence cutoff')
    evidence, evidence_hash = _artifact(directory, plan, 'evidence')
    if (set(evidence) != {'schema_version', 'items', 'claims', 'gaps'}
            or type(evidence['schema_version']) is not int or evidence['schema_version'] != 1):
        raise ValueError('unsupported eligibility evidence format')
    if not isinstance(evidence['items'], list) or len(evidence['items']) > 20000:
        raise ValueError('evidence list exceeds bound')
    evidence = copy.deepcopy(evidence)
    seen = set(); source_bytes = 0
    for row in evidence['items']:
        if set(row) != {'evidence_id', 'market_version_ids', 'source_path', 'source_sha256',
                        'source_url', 'retrieved_at', 'statement'}:
            raise ValueError('exact evidence fields required')
        eid = row['evidence_id']
        owners = row['market_version_ids']
        if (not isinstance(eid, str) or not eid.startswith('evidence:') or len(eid) > 256
                or eid in seen or not isinstance(owners, list) or not owners
                or any(not isinstance(x, str) for x in owners)
                or len(owners) != len(set(owners)) or not set(owners) <= set(ids)):
            raise ValueError('invalid evidence identity or market scope')
        seen.add(eid)
        if (not isinstance(row['statement'], str) or not row['statement'].strip()
                or len(row['statement']) > 12000 or not isinstance(row['source_url'], str)
                or not row['source_url'].startswith(('https://', 'http://'))
                or utc_datetime(row['retrieved_at']) > cutoff):
            raise ValueError('invalid evidence source or cutoff')
        source = _path(directory, row['source_path'])
        digest = _file_sha(source)
        if digest != row['source_sha256'] or plan['files'].get(row['source_path']) != digest:
            raise ValueError('evidence source bytes unbound or changed')
        text = source.read_bytes().decode('utf-8')
        if row['statement'] not in text:
            raise ValueError('source excerpt is not present in the frozen source')
        source_bytes += len(text.encode('utf-8'))
        if source_bytes > 64_000_000:
            raise ValueError('rendered evidence exceeds bound')
        row['source_text'] = text
    _validate_claims(evidence, ids)
    return {'market_version_ids': ids, 'graph_sha256': graph_hash,
            'strategy_sha256': strategy_hash, 'evidence_sha256': evidence_hash,
            'evidence_cutoff': plan['evidence_cutoff'], 'markets': [catalog[i] for i in ids],
            'strategy': strategy, 'evidence': evidence, 'gate_instructions': INSTRUCTIONS}


def _validate_claims(evidence, ids):
    """Research claims never masquerade as a raw source excerpt."""
    sources = {r['evidence_id']: r for r in evidence['items']}
    gaps = {}
    for key, limit in (('claims', 20000), ('gaps', 20000)):
        if not isinstance(evidence[key], list) or len(evidence[key]) > limit:
            raise ValueError('bounded claims and gaps required')
    def scope(row):
        owners = row['market_version_ids']
        if (not isinstance(owners, list) or not owners or any(not isinstance(x, str) for x in owners)
                or len(owners) != len(set(owners)) or not set(owners) <= set(ids)):
            raise ValueError('claim or gap outside exact market scope')
        return set(owners)
    for row in evidence['gaps']:
        if set(row) != {'gap_id', 'market_version_ids', 'question'}:
            raise ValueError('exact gap fields required')
        gid = row['gap_id']; scope(row)
        if (not isinstance(gid, str) or not gid.startswith('gap:') or len(gid) > 256 or gid in gaps
                or not isinstance(row['question'], str) or not row['question'].strip()
                or len(row['question']) > 12000):
            raise ValueError('invalid evidence gap')
        gaps[gid] = row
    seen = set()
    for row in evidence['claims']:
        if set(row) != {'claim_id', 'market_version_ids', 'label', 'statement', 'evidence_ids', 'gap_ids'}:
            raise ValueError('exact claim fields required')
        cid = row['claim_id']; owners = scope(row)
        if (not isinstance(cid, str) or not cid.startswith('claim:') or len(cid) > 256 or cid in seen
                or row['label'] not in ('fact', 'inference', 'assumption', 'unknown')
                or not isinstance(row['statement'], str) or not row['statement'].strip()
                or len(row['statement']) > 12000):
            raise ValueError('invalid labeled claim')
        seen.add(cid)
        for field, known in (('evidence_ids', sources), ('gap_ids', gaps)):
            refs = row[field]
            if (not isinstance(refs, list) or any(not isinstance(x, str) for x in refs)
                    or len(refs) != len(set(refs)) or any(x not in known for x in refs)
                    or any(not owners <= set(known[x]['market_version_ids']) for x in refs)):
                raise ValueError('unknown, duplicate, or other-market claim reference')
        if row['label'] == 'fact' and not row['evidence_ids']:
            raise ValueError('fact claim needs frozen source evidence')
        if row['label'] != 'fact' and not row['gap_ids']:
            raise ValueError('uncertain claim needs a retained gap')


def validate_eligibility_output(document: dict, validated_input: dict) -> None:
    _sha(document)  # Reject NaN/infinity even when called directly rather than through strict JSON.
    if type(document.get('schema_version')) is not int:
        raise ValueError('integer schema version required')
    errors = list(Draft202012Validator(eligibility_output_schema()).iter_errors(document))
    if errors:
        raise ValueError('invalid eligibility output schema')
    for key in ('graph_sha256', 'strategy_sha256', 'evidence_sha256', 'evidence_cutoff'):
        if document[key] != validated_input[key]:
            raise ValueError('eligibility output input binding mismatch')
    if [r['market_version_id'] for r in document['markets']] != validated_input['market_version_ids']:
        raise ValueError('eligibility must cover exact ordered canonical versions')
    evidence = {r['evidence_id']: r for r in validated_input['evidence']['items']}
    for market in document['markets']:
        mid = market['market_version_id']
        for gate in market['gates'].values():
            if not gate['rationale'].strip() or any(not gap.strip() for gap in gate['research_gaps']):
                raise ValueError('meaningful eligibility rationale and gaps required')
            supporting = set(gate['supporting_evidence_ids'])
            counter = set(gate['counterevidence_ids'])
            if supporting & counter or any(e not in evidence or mid not in evidence[e]['market_version_ids']
                                          for e in supporting | counter):
                raise ValueError('unknown, conflicting, or other-market eligibility evidence')
            if gate['status'] != 'unknown' and not supporting:
                raise ValueError('eligibility pass/fail requires market-owned evidence')
            if gate['status'] == 'unknown' or gate['evidence_label'] == 'unknown':
                if gate['status'] != 'unknown' or gate['evidence_label'] != 'unknown':
                    raise ValueError('unknown evidence cannot become an eligibility pass/fail')
            if gate['evidence_label'] != 'fact' and (not gate['research_gaps'] or gate['confidence'] >= 1):
                raise ValueError('uncertain eligibility requires reduced confidence and a retained gap')


def compile_eligibility(document: dict, validated_input: dict) -> dict:
    """Pure projection; callers cannot use it as provider-backed acceptance proof."""
    validate_eligibility_output(document, validated_input)
    rows = []
    for row in document['markets']:
        states = [g['status'] for g in row['gates'].values()]
        status = 'excluded' if 'fail' in states else 'hold' if 'unknown' in states else 'eligible'
        rows.append({**row, 'status': status})
    strategy = validated_input['strategy']
    result = {'schema_version': 1, 'kind': 'market-eligibility-projection-v1',
              **{k: document[k] for k in ('graph_sha256', 'strategy_sha256', 'evidence_sha256', 'evidence_cutoff')},
              'markets': rows,
              'deal_conditions': {'requires_company_due_diligence': True,
                                  'target_enterprise_value': strategy['target_enterprise_value'],
                                  'purchase_multiple': strategy['purchase_multiple'],
                                  'ownership_models': strategy['ownership_models']}}
    return {**result, 'eligibility_sha256': _sha(result)}


def validate_for_evaluation(directory: Path, plan: dict) -> dict:
    inputs = validate_eligibility_input(directory, plan)
    descriptor, _ = _artifact(directory, plan, 'eligibility')
    # Lazy import avoids a dependency cycle. The producer owns exact managed
    # provider/authority/journal/body verification, not this pure projection.
    from turbo.agents.evaluation_execution import validate_eligibility_provider
    document = validate_eligibility_provider(directory, descriptor)
    projection = compile_eligibility(document, inputs)
    if any(row['status'] != 'eligible' for row in projection['markets']):
        raise ValueError('held or excluded market cannot enter evaluation')
    return {k: projection[k] for k in ('eligibility_sha256', 'graph_sha256', 'strategy_sha256')} | {
        'market_version_ids': inputs['market_version_ids']}
