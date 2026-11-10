"""Offline fixture builder. Produces no execution authority and calls no model."""
import copy
import json
from pathlib import Path
import shutil
from turbo.agents import batch_workflow as workflow, batch_provider as provider
from turbo.agents import readable_request_candidate as readable, reviewer_qualification as qualification
from turbo.universe.batch_closure import prepare_batch_release
from turbo.pipeline_paths import ROOT

NEGATIVE_STATEMENT = ('The operating job of Industrial Sand Mining and Preparation is constructing '
    'water-resource projects, including dredging and land drainage performed as construction; '
    'industrial-grade sand extraction and preparation are outside this market.')


def build(destination, source_workflow, input_root, reviewer_config, *, preparation_dirs=None):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink(): raise ValueError('fixture destination must be new')
    source = Path(source_workflow).resolve(strict=True); input_root = Path(input_root).resolve(strict=True)
    positive = workflow.assignment(source, 'release_reviewer', input_root=input_root, preparation_dirs=preparation_dirs)
    positive_preview = qualification.read(source/'release-preview.json')
    if positive_preview['preview_sha256'] != 'a2af41b94b6ee59b2f04e88a57cfede8faa6d4aa204f6bb391cd0298c675b438':
        raise ValueError('qualification requires the exact accepted small preview')
    accepted = qualification.read(source/'release_reviewer.json')['document']
    schema = provider.role_schema('release_reviewer', input_root=input_root)
    qualification.validate_output(accepted, schema, positive)
    if accepted['verdict'] != 'approve': raise ValueError('positive source was not accepted')
    config = {key: copy.deepcopy(reviewer_config[key]) for key in qualification.SETTINGS}
    if config['allow_fallbacks'] is not False: raise ValueError('qualification forbids fallbacks')
    primary = qualification.read(source/'primary.json')['document']; changed = copy.deepcopy(primary)
    family = changed['payload']['families'][0]; market = family['proposed_markets'][0]
    if family['family_id'] != 'family:naics-2022:212322' or market['canonical_name'] != 'Industrial Sand Mining and Preparation':
        raise ValueError('semantic-negative target changed')
    dimension = market['dimensions']['job']; original = dimension['statement']
    dimension['statement'] = NEGATIVE_STATEMENT
    destination.mkdir(); destination = destination.resolve()
    negative_dir = destination/'negative-workflow'; negative_dir.mkdir()
    for filename in ('plan.json', 'context.json'): shutil.copyfile(source/filename, negative_dir/filename)
    (negative_dir/'.lock').touch()
    plan = qualification.read(source/'plan.json')
    envelope = workflow.submit(negative_dir, 'primary', plan['actors']['primary'], changed, input_root=input_root, preparation_dirs=preparation_dirs)
    verifier = qualification.read(source/'verifier.json')['document']
    verifier['input_hashes']['primary'] = envelope['submission_sha256']
    workflow.submit(negative_dir, 'verifier', plan['actors']['verifier'], verifier, input_root=input_root, preparation_dirs=preparation_dirs)
    prepare_batch_release(negative_dir, positive_preview['preview']['config'], root=ROOT,
                          input_root=input_root, preparation_dirs=preparation_dirs)
    negative = workflow.assignment(negative_dir, 'release_reviewer', input_root=input_root, preparation_dirs=preparation_dirs)
    files = {}
    def save(name, value):
        path = destination/name; path.write_bytes(provider._bytes(value)+b'\n'); files[name] = qualification.file_sha(path)
    rubric = {'kind': qualification.KIND, 'version': 1,
        'positive': {'expected_verdict': 'approve', 'preview_sha256': positive_preview['preview_sha256'],
                     'unexpected_findings': 'Require independent evidence-based adjudication, not automatic failure.'},
        'negative': {'expected_verdict': 'reject', 'family_id': family['family_id'], 'proposal_id': market['proposal_id'],
            'changed_path': '/payload/families/0/proposed_markets/0/dimensions/job/statement',
            'original_statement': original, 'replacement_statement': NEGATIVE_STATEMENT,
            'expected_finding': 'Material operating-identity contradiction: construction/dredging for drainage is excluded; evidence supports industrial sand extraction/preparation.',
            'evidence_ids': dimension['supporting_evidence_ids'],
            'synthetic_verifier_agreement': 'Original agreement assessments retained deliberately; hash rebound, no new verifier judgment claimed.'},
        'decision': 'Independent blinded semantic assessment required. Four cells do not prove broad quality equivalence or generalized savings. No automatic production enablement.'}
    save('rubric.json', rubric); save('schema.json', schema)
    cells = {}
    for cell, slot in qualification.CELLS.items():
        fixture, representation = cell.split('-')
        task = {'assignment': positive if fixture == 'positive' else negative,
                'prompt': provider.role_prompt(input_root=input_root, reviewer_view=readable.FORMAT if representation == 'references' else None)}
        wire, _ = qualification.request_for(task, representation, config, schema, cell=cell)
        save(cell+'-task.json', task); save(cell+'-request.json', wire)
        cells[cell] = {'ledger_slot': slot, 'task': cell+'-task.json', 'request': cell+'-request.json'}
    for artifact in negative_dir.glob('*.json'):
        files[artifact.relative_to(destination).as_posix()] = qualification.file_sha(artifact)
    manifest = {'kind': qualification.KIND, 'cells': cells, 'files': files, 'config': config,
        'schema': 'schema.json', 'rubric': 'rubric.json', 'code': qualification.contracts(),
        'source': {'workflow': str(source), 'input_root': str(input_root),
                   'source_files': {p.name: qualification.file_sha(p) for p in source.glob('*.json')},
                   'positive_preview_sha256': positive_preview['preview_sha256'],
                   'negative_preview_sha256': negative['release_preview']['preview_sha256'],
                   'negative_origin': 'synthetic qualification only; never accepted research'}}
    (destination/'manifest.json').write_bytes(provider._bytes(manifest)+b'\n')
    return qualification.preflight(destination)
