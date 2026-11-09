"""Optional reversible JSON model view. No evidence selection or output rewriting."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from typing import Any

VERSION = 'lossless-model-view-v1'
CONTRACT_KEY = 'model-view/' + VERSION
INSTRUCTIONS = '''# Lossless assignment encoding v1
The Frozen assignment below is a reversible representation of the COMPLETE original
assignment, not a summary. Its schema_version is 1. schemas is a list of ordered
object-key lists. strings is a dictionary of exact original string values.
Decode recursively: a JSON object {"o":[i,v0,...]} means an original object whose
keys are schemas[i] and whose corresponding values are recursively decoded v0,... .
A JSON object {"s":i} means the literal original string strings[i]. Ordinary arrays
remain arrays; primitives remain unchanged. Only the context field of this wrapper
is the encoded assignment; schemas and strings are literal dictionaries. All original
objects (including objects with keys o or s) are encoded with o, so markers are
unambiguous. Resolve dictionary entries wherever needed to read the original data.
Evidence IDs and hexadecimal hashes remain literal. All sources, candidate conflicts,
coverage subjects, exclusions, and research gaps are retained. Return the ORIGINAL
canonical role document and full original identity/candidate/evidence IDs, never
encoded objects, dictionary references, or schema indices. The response schema and
all evidence requirements remain unchanged.
'''
POLICY = {'schema_version': 1, 'name': VERSION, 'minimum_string_length': 24,
          'minimum_occurrences': 3, 'preserve_evidence_ids_and_hex_hashes': True,
          'instructions_sha256': hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()}
POLICY_SHA256 = hashlib.sha256(json.dumps(POLICY, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _literal(value: str) -> bool:
    return value.startswith('evidence:') or (len(value) == 64 and all(c in '0123456789abcdef' for c in value))


def encode(value: Any) -> dict:
    """Deterministic table/dictionary encoding; every original JSON value survives."""
    # Enforce JSON domain and finite numeric values before any transformation.
    json.dumps(value, allow_nan=False)
    schemas: list[list[str]] = []
    ids: dict[tuple[str, ...], int] = {}
    counts: Counter[str] = Counter()

    def table(item):
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError('model view requires string object keys')
            keys = tuple(sorted(item))
            if keys not in ids:
                ids[keys] = len(schemas); schemas.append(list(keys))
            return {'o': [ids[keys], *[table(item[k]) for k in keys]]}
        if isinstance(item, list): return [table(v) for v in item]
        if isinstance(item, str) and len(item) >= 24 and not _literal(item): counts[item] += 1
        if item is not None and type(item) not in (str, int, float, bool):
            raise ValueError('model view requires JSON values')
        return item

    body = table(value)
    strings = sorted(s for s, n in counts.items() if n >= 3 and (len(s) - 12) * (n - 1) > len(s))
    refs = {s: i for i, s in enumerate(strings)}

    def compact(item):
        if isinstance(item, dict): return {k: compact(v) for k, v in item.items()}
        if isinstance(item, list): return [compact(v) for v in item]
        return {'s': refs[item]} if isinstance(item, str) and item in refs else item

    result = {'schema_version': 1, 'schemas': schemas, 'strings': strings, 'context': compact(body)}
    if decode(result) != value: raise ValueError('model view roundtrip mismatch')
    return result


def decode(view: dict) -> Any:
    """Strict inverse used locally for deterministic losslessness checks."""
    if (not isinstance(view, dict) or set(view) != {'schema_version', 'schemas', 'strings', 'context'}
            or type(view['schema_version']) is not int or view['schema_version'] != 1):
        raise ValueError('invalid model view')
    schemas, strings = view['schemas'], view['strings']
    if (not isinstance(schemas, list) or not isinstance(strings, list)
            or any(not isinstance(s, str) for s in strings)
            or any(not isinstance(keys, list) or any(not isinstance(k, str) for k in keys)
                   or len(set(keys)) != len(keys) for keys in schemas)):
        raise ValueError('invalid model view dictionaries')

    def index(i, values):
        if type(i) is not int or not 0 <= i < len(values): raise ValueError('invalid model view index')
        return values[i]

    def expand(item):
        if isinstance(item, list): return [expand(v) for v in item]
        if isinstance(item, dict):
            if set(item) == {'s'}: return index(item['s'], strings)
            if set(item) != {'o'} or not isinstance(item['o'], list) or not item['o']:
                raise ValueError('invalid model view marker')
            i, *values = item['o']; keys = index(i, schemas)
            if len(values) != len(keys): raise ValueError('invalid model view row length')
            return {k: expand(v) for k, v in zip(keys, values)}
        if item is not None and type(item) not in (str, int, float, bool):
            raise ValueError('invalid model view primitive')
        return item
    result = expand(view['context'])
    json.dumps(result, allow_nan=False)
    return result
