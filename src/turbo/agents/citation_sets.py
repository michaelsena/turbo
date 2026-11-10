"""Opt-in, lossless set-citation normalization for fresh managed requests only."""
import copy
import hashlib
import json

VERSION = 'citation-sets-v1'
CONTRACT_KEY = 'output/citation-sets-v1'
SOURCE_PATH = 'src/turbo/agents/citation_sets.py'
FIELDS = ('supporting_evidence_ids', 'counterevidence_ids')
DIMENSIONS = ('buyer', 'job', 'delivery', 'workforce', 'economics_risk',
              'acquisition_universe', 'ambient_ai_workflow')
PATHS = tuple(('payload', 'families', '*', group, '*') + suffix + (field,)
              for group, suffixes in (
                  ('proposed_markets', [()] + [('dimensions', d) for d in DIMENSIONS]),
                  ('identity_dispositions', [()]), ('candidate_dispositions', [()]),
                  ('research_gaps', [()]))
              for suffix in suffixes for field in FIELDS)

def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()

POLICY_SHA256 = _hash({'version': VERSION, 'paths': PATHS,
    'operation': 'remove-exact-string-repeats-preserving-first-order'})
INSTRUCTIONS = ('\n# Citation set response contract\n'
    'citation-sets-v1 accepts repeated identical evidence IDs only in declared B3 '
    'supporting_evidence_ids/counterevidence_ids set arrays. The host records their '
    'order-preserving deduplication; all canonical semantic validation remains mandatory.\n')

def _resolve(schema, root):
    if '$ref' in schema:
        ref = schema['$ref']
        if not ref.startswith('#/$defs/') or '/' in ref[len('#/$defs/'):]:
            raise ValueError('unsupported citation schema reference')
        return root['$defs'][ref[len('#/$defs/'):]]
    return schema

def _nodes(schema):
    # No payload means no eligible paths, including verifier/release attestations.
    if 'payload' not in schema.get('properties', {}):
        return []
    nodes = []
    for path in PATHS:
        node = schema
        for part in path:
            node = _resolve(node, schema)
            node = node['items'] if part == '*' else node['properties'][part]
        node = _resolve(node, schema)
        if (node.get('type') != 'array' or node.get('uniqueItems') is not True
                or node.get('items') != {'type': 'string', 'pattern': '^evidence:[0-9a-f]{64}$'}):
            raise ValueError('citation policy canonical schema changed')
        nodes.append(node)
    return nodes

def provider_schema(canonical):
    result = copy.deepcopy(canonical)
    for node in _nodes(result):
        node.pop('uniqueItems', None)
    return result

def normalize(document, canonical):
    _nodes(canonical)  # Fail closed on schema drift before changing any document.
    result = copy.deepcopy(document)
    changes = []
    def visit(value, remaining, pointer):
        part, *tail = remaining
        if part == '*':
            if isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, tail, pointer + '/' + str(index))
        elif isinstance(value, dict) and part in value:
            target = value[part]
            if tail:
                visit(target, tail, pointer + '/' + part)
            elif isinstance(target, list) and all(isinstance(x, str) for x in target):
                seen = set(); unique = []; removed = []
                for index, item in enumerate(target):
                    if item in seen: removed.append(index)
                    else: seen.add(item); unique.append(item)
                if removed:
                    value[part] = unique
                    changes.append({'path': pointer + '/' + part, 'removed_indices': removed})
    for path in PATHS:
        visit(result, path, '')
    return result, {'version': VERSION, 'policy_sha256': POLICY_SHA256,
                    'canonical_sha256': _hash(result), 'changes': changes}
