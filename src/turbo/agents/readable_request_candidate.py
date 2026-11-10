"""Opt-in readable reviewer representation; quality qualification remains required."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

FORMAT = 'readable-backward-references-v1-candidate'
INSTRUCTIONS = ('This is the complete assignment, with exact repeated objects or lists referenced '
    'by their earlier JSON Pointer location. Read document normally; an object containing only '
    'the reference_key means the entire original value at that earlier location, relative to '
    'document. Pointer / escapes as ~1 and ~ as ~0. First occurrences retain their original '
    'field names and complete values. Resolve every reference wherever used; none is omitted '
    'evidence. Return the original output schema and literal original IDs, never reference objects.')
MAX_BYTES = 64 * 1024 * 1024
CONTRACT_KEY = 'reviewer-view/' + FORMAT
SOURCE_PATH = 'src/turbo/agents/readable_request_candidate.py'
POLICY = {'format': FORMAT, 'role': 'release_reviewer', 'minimum_bytes': 256,
          'max_decoded_bytes': MAX_BYTES, 'reference_order': 'sorted_keys_backward_literal_containers',
          'instructions_sha256': hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()}
POLICY_SHA256 = hashlib.sha256(json.dumps(POLICY, sort_keys=True, separators=(',', ':')).encode()).hexdigest()



def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('only string JSON keys are supported')
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)
    elif value is not None and type(value) not in (str, bool, int, float):
        raise ValueError('only JSON values are supported')


def encode(value: Any, *, minimum_bytes: int = 256) -> dict:
    """Keep first occurrences inline and reference only byte-saving exact repeats."""
    if type(minimum_bytes) is not int or minimum_bytes < 1:
        raise ValueError('minimum_bytes must be a positive integer')
    keys = set(_keys(value))
    raw = canonical(value)
    if len(raw) > MAX_BYTES:
        raise ValueError('assignment exceeds candidate byte limit')
    index = 0
    while '$same_as_' + str(index) in keys:
        index += 1
    marker = '$same_as_' + str(index)
    seen = {}

    def visit(item, path):
        if isinstance(item, (dict, list)):
            original = canonical(item)
            if len(original) >= minimum_bytes:
                prior = seen.get(original)
                reference = {marker: prior}
                if prior is not None and len(canonical(reference)) < len(original):
                    return reference
            result = ({key: visit(child, _pointer(path, key)) for key, child in sorted(item.items())}
                      if isinstance(item, dict) else
                      [visit(child, _pointer(path, i)) for i, child in enumerate(item)])
            if len(original) >= minimum_bytes:
                seen.setdefault(original, path)
            return result
        return item

    result = {'format': FORMAT, 'instructions': INSTRUCTIONS, 'reference_key': marker,
              'original_sha256': hashlib.sha256(raw).hexdigest(), 'document': visit(value, '')}
    if canonical(decode(result)) != raw:
        raise ValueError('candidate failed exact roundtrip')
    return result


def decode(view: dict, *, max_output_bytes: int = MAX_BYTES) -> Any:
    """Strict bounded inverse: references may target only earlier literal containers."""
    required = {'format', 'instructions', 'reference_key', 'original_sha256', 'document'}
    if (not isinstance(view, dict) or set(view) != required or view['format'] != FORMAT
            or view['instructions'] != INSTRUCTIONS or type(max_output_bytes) is not int
            or max_output_bytes < 1):
        raise ValueError('invalid readable candidate wrapper')
    marker = view['reference_key']
    if (not isinstance(marker, str) or not re.fullmatch(r'\$same_as_[0-9]+', marker)
            or not isinstance(view['original_sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', view['original_sha256'])):
        raise ValueError('invalid candidate marker or digest')
    _ = set(_keys(view['document']))
    previous = {}
    used = 0

    def reserve(size):
        nonlocal used
        used += size
        if used > max_output_bytes:
            raise ValueError('decoded assignment exceeds byte limit')

    def visit(item, path):
        if isinstance(item, dict) and marker in item:
            target = item[marker]
            if set(item) != {marker} or not isinstance(target, str) or target not in previous:
                raise ValueError('reference must name an earlier literal container')
            original, size = previous[target]
            reserve(size)
            return copy.deepcopy(original), size
        if isinstance(item, (dict, list)):
            shell = (2 + max(0, len(item) - 1) +
                     sum(len(canonical(key)) + 1 for key in item)) if isinstance(item, dict) else (2 + max(0, len(item) - 1))
            reserve(shell)
            children = [(key, visit(child, _pointer(path, key))) for key, child in
                        (sorted(item.items()) if isinstance(item, dict) else enumerate(item))]
            result = ({key: child for key, (child, _) in children} if isinstance(item, dict)
                      else [child for _, (child, _) in children])
            size = shell + sum(size for _, (_, size) in children)
            previous[path] = (result, size)
            return result, size
        size = len(canonical(item))
        reserve(size)
        return item, size

    result, _ = visit(view['document'], '')
    if hashlib.sha256(canonical(result)).hexdigest() != view['original_sha256']:
        raise ValueError('decoded assignment digest mismatch')
    return result
