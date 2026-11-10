"""Read-only admission of explicitly frozen family-local operating evidence.

A checksum proves the selected bytes, not the truth of their claims. No fetches,
source ownership changes, or acceptance decisions occur here.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator

MAX_MANIFEST_BYTES = 2_000_000
MAX_SOURCE_BYTES = 2_000_000
MAX_TOTAL_SOURCE_BYTES = 8_000_000


def _file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('supplement paths must be repository-relative without traversal')
    target = root.resolve() / path
    if target.resolve() != target or not target.is_file():
        raise ValueError('supplement file is missing or uses a symlink')
    target.resolve().relative_to(root.resolve())
    return target


def _read(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError('supplement exceeds byte limit')
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('supplement exceeds byte limit')
    return raw


def _unique(rows: list[dict], key: str) -> set[str]:
    ids = [row[key] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate supplemental ' + key)
    return set(ids)


def load_supplement(root: Path, binding: dict, *, family_id: str,
                    source_run_id: str, subject_ids: set[str]) -> dict:
    if (not isinstance(binding, dict) or set(binding) != {'manifest_path', 'manifest_sha256'}
            or not all(isinstance(v, str) for v in binding.values())):
        raise ValueError('invalid supplement binding')
    raw = _read(_file(root, binding['manifest_path']), MAX_MANIFEST_BYTES)
    if hashlib.sha256(raw).hexdigest() != binding['manifest_sha256']:
        raise ValueError('supplement manifest hash mismatch')
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate supplemental JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('non-finite supplemental JSON number')

    manifest = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int:
        raise ValueError('supplement schema version requires an integer')
    schema = json.loads((root / 'schemas/family-supplement-v1.schema.json').read_text())
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    if errors:
        raise ValueError('invalid supplemental manifest: ' + errors[0].message)
    if manifest['family_id'] != family_id or manifest['source_run_id'] != source_run_id:
        raise ValueError('supplement family/source-run binding mismatch')
    sources = _unique(manifest['sources'], 'source_id')
    _unique(manifest['claims'], 'claim_id')
    gaps = _unique(manifest['gaps'], 'gap_id')
    for row in manifest['sources'] + manifest['claims'] + manifest['gaps']:
        if not row['subject_ids'] or set(row['subject_ids']) - subject_ids:
            raise ValueError('supplement names an empty or unselected subject scope')
    source_subjects = {r['source_id']: set(r['subject_ids']) for r in manifest['sources']}
    gap_subjects = {r['gap_id']: set(r['subject_ids']) for r in manifest['gaps']}
    for claim in manifest['claims']:
        if set(claim['source_ids']) - sources or set(claim['gap_ids']) - gaps:
            raise ValueError('supplement claim references unknown source/gap')
        if claim['kind'] in ('fact', 'inference') and not claim['source_ids']:
            raise ValueError('factual/inferred supplement claim requires a source')
        if claim['kind'] in ('assumption', 'unknown') and not claim['gap_ids']:
            raise ValueError('assumption/unknown supplement claim requires a gap')
        for subject in claim['subject_ids']:
            if claim['source_ids'] and not any(subject in source_subjects[s] for s in claim['source_ids']):
                raise ValueError('claim source does not bind its subject')
            if claim['gap_ids'] and not any(subject in gap_subjects[g] for g in claim['gap_ids']):
                raise ValueError('claim gap does not bind its subject')
    rendered = []
    total = 0
    for source in manifest['sources']:
        url = urlsplit(source['url'])
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            raise ValueError('supplement requires an absolute public-source URL without credentials')
        try:
            instant = datetime.fromisoformat(source['retrieved_at_utc'].replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('invalid supplement retrieval UTC') from error
        if instant.tzinfo is None or instant.utcoffset() != timezone.utc.utcoffset(instant):
            raise ValueError('supplement retrieval timestamp must explicitly be UTC')
        content = _read(_file(root, source['path']), MAX_SOURCE_BYTES)
        total += len(content)
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('supplement source total exceeds limit')
        if hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError('supplement source bytes hash mismatch')
        text = content.decode('utf-8')
        if not text.strip():
            raise ValueError('supplement source is empty')
        rendered.append({**source, 'text': text, 'interpretation_boundary':
            'Frozen source representation, not an accepted market decision. Claims are separate; '
            'excerpt_with_paraphrase includes researcher interpretation and is not verbatim source text.'})
    return {'supplemental_sources': rendered,
            'supplemental_claims': [{**claim, 'interpretation_boundary':
                'Unreviewed researcher assertion. kind is the researcher evidence label, not '
                'compiler-certified truth; check the linked frozen sources before accepting it.'}
                for claim in manifest['claims']],
            'supplemental_gaps': manifest['gaps']}


def binding_for(root: Path, manifest_path: Path) -> dict:
    if manifest_path.is_absolute():
        relative = str(manifest_path.relative_to(root.resolve()))
    else:
        relative = str(manifest_path)
    raw = _read(_file(root, relative), MAX_MANIFEST_BYTES)
    return {'manifest_path': relative, 'manifest_sha256': hashlib.sha256(raw).hexdigest()}
