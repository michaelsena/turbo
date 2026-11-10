"""Strict versioned single-submodel score mechanics; no global ranking."""
import itertools
import hashlib
import json
import math

POLICY = {'close_resolution': 'arithmetic_mean', 'confidence_adjustment': 'raw_times_confidence_times_evidence_quality',
          'downside_adjustment': 'subtract_downside', 'aggregation': 'normalized_weighted_mean',
          'pair_selection': 'all_unordered_pairs', 'comparison_effect': 'bounded_additive_submodel'}


def number(value, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('numeric score outside registered bounds')


def policy(value, submodel):
    if (not isinstance(value,dict) or not isinstance(submodel,str) or not submodel.strip()
        or set(value) != {'submodel_version_id', 'factors', 'policy', 'comparison_max_delta'} or value['submodel_version_id'] != submodel):
        raise ValueError('registered factor policy required')
    if value['policy'] != POLICY: raise ValueError('unsupported explicit score policy')
    number(value['comparison_max_delta'], 0, 100)
    if not value['factors'] or len(value['factors']) > 100: raise ValueError('bounded factors required')
    ids = set()
    for f in value['factors']:
        if set(f) != {'factor_version_id','minimum','maximum','weight','tolerance','anchors','evidence_expectations','model_policy'}:
            raise ValueError('complete registered factor definition required')
        if not isinstance(f['factor_version_id'],str) or not f['factor_version_id'] or f['factor_version_id'] in ids: raise ValueError('duplicate factor')
        ids.add(f['factor_version_id'])
        number(f['minimum'],-100,100); number(f['maximum'],f['minimum']+0.000001,100)
        number(f['weight'],0.000001,100); number(f['tolerance'],0,f['maximum']-f['minimum'])
        anchors=f['anchors']
        if not isinstance(anchors,dict) or not 2<=len(anchors)<=100: raise ValueError('explicit bounded anchors required')
        positions=[]
        for key,description in anchors.items():
            if not isinstance(key,str) or not isinstance(description,str) or not description.strip() or len(description)>4000: raise ValueError('meaningful anchor descriptions required')
            try: position=float(key)
            except (ValueError,OverflowError): raise ValueError('numeric anchor positions required')
            number(position,f['minimum'],f['maximum']);positions.append(position)
        if len(positions)!=len(set(positions)) or f['minimum'] not in positions or f['maximum'] not in positions: raise ValueError('distinct minimum/maximum anchors required')
        expectations=f['evidence_expectations']
        if not isinstance(expectations,list) or not 1<=len(expectations)<=100 or any(not isinstance(x,str) or not x.strip() or len(x)>4000 for x in expectations): raise ValueError('nonblank evidence expectations required')
        model=f['model_policy']
        if not isinstance(model,dict) or set(model)!={'tasks'} or not isinstance(model['tasks'],dict) or set(model['tasks'])!={'evaluator_a','evaluator_b','adjudicator','comparator'}: raise ValueError('exact task model policy required')
        for cfg in model['tasks'].values():
            if not isinstance(cfg,dict) or set(cfg)!={'model','reasoning_effort'} or any(not isinstance(x,str) or not x.strip() or len(x)>256 for x in cfg.values()): raise ValueError('explicit model and effort required')
    return value


def comparison_pairs(markets,factors):
    return [{'pair_id':'comparison:'+hashlib.sha256(json.dumps([factors['submodel_version_id'],a,b],separators=(',',':')).encode()).hexdigest()[:24],
             'market_version_ids':[a,b]} for a,b in itertools.combinations(markets,2)]


def keys(markets, factors):
    return [(m,f['factor_version_id']) for m in markets for f in factors['factors']]


def validate(document, task, markets, factors, evidence, dependencies):
    expected = set(keys(markets,factors))
    if task == 'adjudicator': expected = set(map(tuple,dependencies['disagreements']))
    if task == 'comparator':
        if set(document) != {'pairs','adjustments'}: raise ValueError('comparison fields')
        expected_pairs=comparison_pairs(markets,factors)
        actual=[{'pair_id':r.get('pair_id'),'market_version_ids':r.get('market_version_ids')} for r in document['pairs']]
        if actual != expected_pairs: raise ValueError('exact comparison pairs required')
        by_id={r['pair_id']:r['market_version_ids'] for r in expected_pairs}
        for row in document['pairs']:
            rationale(row,evidence, {'pair_id','market_version_ids','preferred_market_version_id','confidence','rationale','claim_ids','counterevidence_ids','gap_ids'})
            if row['preferred_market_version_id'] is not None and row['preferred_market_version_id'] not in row['market_version_ids']: raise ValueError('comparison result outside pair')
            number(row['confidence'],0,1)
            refs=[*row['claim_ids'],*row['gap_ids']]
            evidence_scopes={r['claim_id']:r['market_version_ids'] for r in evidence['claims']} | {r['gap_id']:r['market_version_ids'] for r in evidence['gaps']}
            if any(not any(m in evidence_scopes[ref] for ref in refs) for m in row['market_version_ids']): raise ValueError('each comparison market needs evidence or explicit gap')
            if row['confidence']<1 and not row['gap_ids']: raise ValueError('uncertain comparison needs retained gap')
        if [r.get('market_version_id') for r in document['adjustments']] != markets: raise ValueError('comparison exact market scope')
        for row in document['adjustments']:
            if set(row) != {'market_version_id','delta','pair_ids','rationale'} or not isinstance(row['rationale'],str) or not row['rationale'].strip(): raise ValueError('comparison adjustment rationale')
            number(row['delta'],-factors['comparison_max_delta'],factors['comparison_max_delta'])
            refs=row['pair_ids']
            if not isinstance(refs,list) or len(refs)!=len(set(refs)) or any(ref not in by_id or row['market_version_id'] not in by_id[ref] for ref in refs): raise ValueError('comparison effect pair attribution')
            if row['delta'] != 0 and not refs: raise ValueError('score effect requires attributed comparison')
        if not expected_pairs and any(r['delta'] != 0 for r in document['adjustments']): raise ValueError('no pair permits no score effect')
        return
    if set(document) != {'scores'}: raise ValueError('score fields')
    rows = document['scores']; actual = [(r.get('market_version_id'),r.get('factor_version_id')) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected: raise ValueError('exact nonblank score grid required')
    definitions = {f['factor_version_id']:f for f in factors['factors']}
    for row in rows:
        rationale(row,evidence,{'market_version_id','factor_version_id','raw','confidence','evidence_quality','downside','label','rationale','claim_ids','counterevidence_ids','gap_ids','alternatives'})
        f = definitions[row['factor_version_id']]
        number(row['raw'],f['minimum'],f['maximum'])
        number(row['confidence'],0,1); number(row['evidence_quality'],0,1)
        number(row['downside'],0,f['maximum']-f['minimum'])
        if row['label'] not in ('fact','inference','assumption') or not isinstance(row['alternatives'],list): raise ValueError('score reasoning label/alternatives required')
        for alternative in row['alternatives']: number(alternative,f['minimum'],f['maximum'])


def rationale(row,evidence,fields):
    if set(row) != fields or not isinstance(row['rationale'],str) or not row['rationale'].strip(): raise ValueError('complete score rationale required')
    claims = {r['claim_id']: r for r in evidence['claims']}; gaps = {r['gap_id']: r for r in evidence['gaps']}
    scope = set(row.get('market_version_ids', [row.get('market_version_id')]))
    for field, known in [('claim_ids',claims),('counterevidence_ids',claims),('gap_ids',gaps)]:
        if not isinstance(row[field],list) or len(row[field]) != len(set(row[field])) or set(row[field])-set(known): raise ValueError('unknown or duplicate evidence reference')
        if any(not scope.intersection(known[ref]['market_version_ids']) for ref in row[field]): raise ValueError('other-market evidence reference')
    if row.get('label') == 'fact' and (not row['claim_ids'] or any(claims[ref]['label'] != 'fact' for ref in row['claim_ids'])): raise ValueError('fact score requires factual supporting claims')
    if set(row['claim_ids']) & set(row['counterevidence_ids']): raise ValueError('support/counterevidence overlap')
    if not row['claim_ids'] and not row['gap_ids']: raise ValueError('evidence or explicit gap required')
    if row.get('label') in ('inference', 'assumption') and (not row['gap_ids'] or row['confidence'] >= 1): raise ValueError('uncertain score requires gap and reduced confidence')


def disagreements(a,b,factors):
    ar={(r['market_version_id'],r['factor_version_id']):r for r in a['scores']}
    br={(r['market_version_id'],r['factor_version_id']):r for r in b['scores']}
    tolerance={f['factor_version_id']:f['tolerance'] for f in factors['factors']}
    return [list(k) for k in sorted(ar) if abs(ar[k]['raw']-br[k]['raw'])>tolerance[k[1]]]


def resolve(markets,factors,a,b,adjudication=None):
    material=set(map(tuple,disagreements(a,b,factors)))
    if material and adjudication is None: raise ValueError('material disagreement requires adjudication')
    indexed=[{(r['market_version_id'],r['factor_version_id']):r for r in d['scores']} for d in (a,b)]
    adj={(r['market_version_id'],r['factor_version_id']):r for r in (adjudication or {'scores':[]})['scores']}
    rows=[]
    for key in keys(markets,factors):
        originals=[v[key] for v in indexed]
        row={'market_version_id':key[0],'factor_version_id':key[1],'originals':originals,'adjudication':adj.get(key), 'provisional':key in material}
        for field in ('raw','confidence','evidence_quality','downside'):
            row[field]=adj[key][field] if key in material else sum(r[field] for r in originals)/2
        row['confidence_adjusted']=row['raw']*row['confidence']*row['evidence_quality']
        row['downside_adjusted']=row['confidence_adjusted']-row['downside']
        row['gap_ids']=sorted(set(g for r in [*originals,*([adj[key]] if key in material else [])] for g in r['gap_ids']))
        rows.append(row)
    weights={f['factor_version_id']:f['weight'] for f in factors['factors']}; total=sum(weights.values())
    aggregates=[{'market_version_id':m,**{field:sum(r[field]*weights[r['factor_version_id']] for r in rows if r['market_version_id']==m)/total for field in ('raw','confidence_adjusted','downside_adjusted')}} for m in markets]
    return {'scores':rows,'submodel_scores':aggregates,'policy':factors['policy'],'global_ranking':False}
