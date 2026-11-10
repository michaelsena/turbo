"""Explicit publication continuation; immutable intent and exact artifact replay."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import subprocess

from turbo.agents import batch_controller as controller, batch_execution_v2 as ledger
from turbo.universe import batch_closure as closure, graph_release as graph
from turbo.agents.boundary_harness import canonical_sha256


def _hash_file(path):
    ledger._regular(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(root, value):
    path = controller._paths(root / value)
    if not path.is_relative_to(root) or path == root:
        raise ValueError('publication path escapes root')
    return path


def _options(m):
    return {'root': Path(m['root']), **controller._options(m)}


def _binding(m, name, value=None):
    local = Path(m['controller_dir']) / (name + '.json')
    external = Path(m['registry_dir']) / ('controller-' + name + '-' + m['authorization_sha256'] + '.json')
    if value is not None:
        if local.exists() or external.exists():
            if _binding(m, name) != value:
                raise ValueError('publication immutable binding changed')
        else:
            ledger._write(local, value)
            ledger._write(external, {'manifest_sha256': m['manifest_sha256'], 'sha256': ledger._hash(value)})
    if not local.exists() and not external.exists():
        return None
    stored = ledger._read(local)
    if ledger._read(external) != {'manifest_sha256': m['manifest_sha256'], 'sha256': ledger._hash(stored)}:
        raise ValueError('publication binding changed or partial')
    return stored


def _approved(m):
    journal = controller._journal(Path(m['registry_dir']), m['authorization'])
    for aid, row in journal['requests'].items():
        if row['status'] != 'succeeded' or m['attempt_ids'].get(row['role']) != aid:
            raise ValueError('publication requires exact successful provider attempts')
    controller._verify_submissions(m, journal['requests'])
    stage, wrapper, reviewer = closure._approved(Path(m['workflow_dir']), **_options(m))
    bound = controller._release_binding(m)
    if bound is None or bound['config'] != wrapper['preview']['config']:
        raise ValueError('publication review differs from bound semantic config')
    return stage, wrapper, reviewer


def _graph_options(m):
    # Each historical batch must replay its own recorded frozen paths. Applying
    # this controller's current frozen inputs to older approvals would rebase them.
    return {'root': Path(m['root'])}


def _checked_graph(m, release_dir, config_path):
    controller._paths(release_dir)
    ledger._regular(release_dir / 'graph-receipt.json')
    ledger._regular(release_dir / 'projection.json')
    result = graph.validate_graph_release(release_dir, config_path, **_graph_options(m))
    if result.get('valid') is not True:
        raise ValueError('publication graph replay failed')
    receipt = ledger._read(release_dir / 'graph-receipt.json')
    return {'schema_version': 1, 'release_id': receipt['release_id'],
            'graph_version_id': receipt['graph_version_id'],
            'source_universe_run_id': receipt['source_universe_run_id'],
            'release_path': str(release_dir.relative_to(Path(m['root']))),
            'receipt_sha256': canonical_sha256(receipt),
            'projection_sha256': receipt['projection_sha256']}


def _intent(m, config):
    from turbo.universe.graph_publication import _canonical
    _canonical(Path(m['root']))
    if set(config) != {'schema_version', 'output_root', 'base_graph_config', 'release_name'} or config['schema_version'] != 1:
        raise ValueError('invalid publication config')
    root = Path(m['root']); output = _relative(root, config['output_root'])
    if output.exists() or output.is_symlink():
        raise ValueError('publication output must be new')
    if not graph._git_worktree_clean(root):
        raise ValueError('publication intent requires clean reviewed execution checkout')
    _, wrapper, reviewer = _approved(m)
    if graph._git_head(root) != wrapper['preview']['config']['execution_commit']:
        raise ValueError('publication intent requires exact reviewed execution commit')
    base = ledger._read(root / 'data/generated/latest-graph.json')
    if ledger._hash(base) != m['base_pointer_sha256']:
        raise ValueError('publication canonical base changed')
    base_config_path = _relative(root, config['base_graph_config'])
    if _checked_graph(m, _relative(root, base['release_path']), base_config_path) != base:
        raise ValueError('publication base graph pointer mismatch')
    compiled_config = copy.deepcopy(ledger._read(base_config_path))
    preview = wrapper['preview']; movement = bool(preview['movements'])
    activation = None
    if movement:
        activation = closure._activation(Path(m['workflow_dir']), **_options(m))
        receipt = activation['receipt']
        activation_dir = output / 'activations' / receipt['activation_id']
        compiled_config['activations'].append({'kind': 'batch',
            'activation_dir': str(activation_dir.relative_to(root)),
            'activation_config': str((activation_dir / 'activation-config.json').relative_to(root)),
            **{key: receipt[key] for key in ('activation_id', 'activation_config_sha256', 'events_sha256', 'projection_sha256')}})
        compiled_config['release_name'] = config['release_name']
        compiled_config['as_of_utc'] = preview['config']['recorded_at_utc']
    intent = {'schema_version': 1, 'manifest_sha256': m['manifest_sha256'],
        'implementation_sha256': _hash_file(Path(__file__)),
        'promotion_implementation_sha256': _hash_file(Path(__file__).parents[1] / 'universe/graph_publication.py'), 'config': copy.deepcopy(config),
        'base_pointer': base, 'base_config_sha256': _hash_file(base_config_path),
        'preview_sha256': wrapper['preview_sha256'], 'review_sha256': reviewer['submission_sha256'],
        'movement': movement, 'activation': activation, 'graph_config': compiled_config,
        'reviewed_execution_commit': preview['config']['execution_commit']}
    return _binding(m, 'publication-intent', intent)


def _verify_intent(m, intent):
    if not intent['movement'] and graph._git_head(Path(m['root'])) != intent['reviewed_execution_commit']:
        raise ValueError('no-movement publication requires original reviewed execution commit')
    if intent['manifest_sha256'] != m['manifest_sha256'] or intent['implementation_sha256'] != _hash_file(Path(__file__)):
        raise ValueError('publication identity or implementation changed')
    if intent['promotion_implementation_sha256'] != _hash_file(Path(__file__).parents[1] / 'universe/graph_publication.py'):
        raise ValueError('publication promotion implementation changed')
    _, wrapper, reviewer = _approved(m)
    if wrapper['preview_sha256'] != intent['preview_sha256'] or reviewer['submission_sha256'] != intent['review_sha256']:
        raise ValueError('publication exact review changed')
    if _hash_file(_relative(Path(m['root']), intent['config']['base_graph_config'])) != intent['base_config_sha256']:
        raise ValueError('publication base configuration changed')


def _activation_dir(m, intent):
    return _relative(Path(m['root']), intent['config']['output_root']) / 'activations' / intent['activation']['receipt']['activation_id']


def _activation_valid(m, intent):
    directory = controller._paths(_activation_dir(m, intent))
    ledger._regular(directory / 'activation-config.json')
    checked = closure.validate_batch_activation(directory, directory / 'activation-config.json', **_options(m))
    if checked.get('valid') is not True:
        raise ValueError('publication activation replay failed')
    expected = intent['activation']
    for name, key in (('events.json', 'events'), ('projection.json', 'projection'), ('activation-receipt.json', 'receipt')):
        if ledger._read(directory / name) != expected[key]:
            raise ValueError('publication activation changed')
    if set(p.name for p in directory.iterdir()) != {'events.json', 'projection.json', 'activation-receipt.json', 'activation-config.json'}:
        raise ValueError('unexpected publication activation files')


def _source(m, intent, graph_config_path):
    root = Path(m['root']); original = intent['reviewed_execution_commit']
    if not graph._git_worktree_clean(root):
        return None
    current = graph._git_head(root)
    expected = {str(graph_config_path.relative_to(root))}
    expected.update(str(p.relative_to(root)) for p in _activation_dir(m, intent).iterdir())
    changed = subprocess.check_output(['git', '-C', str(root), 'diff', '--name-only', original, current], text=True).splitlines()
    if set(changed) != expected:
        raise ValueError('publication source commit must contain only exact activation and graph config additions')
    for name in expected:
        subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch', '--', name], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    value = {'commit': current, 'files': {name: _hash_file(root / name) for name in sorted(expected)}}
    return _binding(m, 'publication-source', value)


def _worktree_changes(root, allowed_untracked, *, pointer_may_change):
    tracked = subprocess.check_output(['git', '-C', str(root), 'diff', '--name-only', '-z', 'HEAD'], text=False).split(b'\0')
    allowed_tracked = {'data/generated/latest-graph.json'} if pointer_may_change else set()
    if any(name.decode() not in allowed_tracked for name in tracked if name):
        raise ValueError('publication source tracked files changed')
    untracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard', '-z'], text=False).split(b'\0')
    allowed = {str(path.relative_to(root)) for path in allowed_untracked}
    if any(name.decode() not in allowed for name in untracked if name):
        raise ValueError('publication has undeclared untracked files')


def _source_valid(m, source):
    root = Path(m['root'])
    if graph._git_head(root) != source['commit']:
        raise ValueError('publication source commit changed')
    tracked = subprocess.check_output(['git', '-C', str(root), 'diff', '--name-only', '-z', 'HEAD']).split(b'\0')
    if any(name.decode() != 'data/generated/latest-graph.json' for name in tracked if name):
        raise ValueError('publication source tracked files changed')
    for name, digest in source['files'].items():
        if _hash_file(_relative(root, name)) != digest:
            raise ValueError('publication source artifact changed')


def _closure(m, output, graph_dir=None, graph_config=None, *, create=False):
    options = {'root': Path(m['root']), 'graph_release_dir': graph_dir, 'graph_release_config': graph_config}
    # Both current and historical workflows must retain their recorded paths.
    # Explicit current overrides were checked above, but cannot be propagated
    # globally into cumulative replay without rebasing older approvals.
    proof = closure._closure_proof(Path(m['workflow_dir']), **options)
    directory = controller._paths(output / 'closures' / ('batch-closure-' + canonical_sha256(proof)[:20]))
    if not directory.exists() and create:
        closure.finalize_batch_closure(Path(m['workflow_dir']), output_root=output / 'closures', **options)
    if not directory.exists():
        return directory, None
    if set(p.name for p in directory.iterdir()) != {'closure.json'}:
        raise ValueError('unexpected publication closure files')
    ledger._regular(directory / 'closure.json')
    checked = closure.validate_batch_closure(directory, Path(m['workflow_dir']), **options)
    if checked.get('valid') is not True:
        raise ValueError('publication closure replay failed')
    return directory, proof


def _graph_identity(m, intent, source, config_path):
    compiled = graph.compile_graph_release(config_path, execution_commit=source['commit'], **_graph_options(m))
    receipt = graph._receipt(compiled)
    output = _relative(Path(m['root']), intent['config']['output_root'])
    directory = controller._paths(output / 'versions' / compiled['release_id'])
    pointer = {'schema_version': 1, 'release_id': receipt['release_id'],
        'graph_version_id': receipt['graph_version_id'], 'source_universe_run_id': receipt['source_universe_run_id'],
        'release_path': str(directory.relative_to(Path(m['root']))),
        'receipt_sha256': canonical_sha256(receipt), 'projection_sha256': receipt['projection_sha256']}
    return directory, pointer


def _durable_files(root, files):
    directories = set()
    for path in files:
        path = controller._paths(path); ledger._regular(path)
        with path.open('rb') as stream:
            os.fsync(stream.fileno())
        directory = path.parent
        while directory.is_relative_to(root):
            directories.add(directory)
            if directory == root:
                break
            directory = directory.parent
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        ledger._sync(directory)


def inspect(m):
    """Read-only publication state; never repairs or moves a pointer."""
    intent = _binding(m, 'publication-intent')
    if intent is None:
        return None
    _verify_intent(m, intent)
    root = Path(m['root']); output = _relative(root, intent['config']['output_root'])
    current = ledger._read(root / 'data/generated/latest-graph.json')
    expected = intent['base_pointer']
    source = _binding(m, 'publication-source')
    graph_dir = None; config_path = None
    if intent['movement']:
        activation_dir = _activation_dir(m, intent)
        if not activation_dir.exists():
            if current != expected:
                raise ValueError('publication base changed before activation')
            return {'state': 'PUBLICATION_INTENT_BOUND'}
        _activation_valid(m, intent)
        config_path = output / 'graph-config.json'
        if not config_path.exists():
            if current != expected:
                raise ValueError('publication base changed before graph config')
            return {'state': 'PUBLICATION_ACTIVATION_STAGED'}
        if ledger._read(config_path) != intent['graph_config']:
            raise ValueError('publication graph configuration changed')
        if source is None:
            if current != expected:
                raise ValueError('publication base changed before source commit')
            return {'state': 'WAITING_PUBLICATION_SOURCE_COMMIT', 'source_paths': [
                str(activation_dir.relative_to(root)), str(config_path.relative_to(root))]}
        _source_valid(m, source)
        graph_dir, expected = _graph_identity(m, intent, source, config_path)
        if current not in (intent['base_pointer'], expected):
            raise ValueError('publication canonical base changed')
        if not graph_dir.exists():
            if current != intent['base_pointer']:
                raise ValueError('publication pointer precedes persisted graph')
            _worktree_changes(root, set(), pointer_may_change=False)
            return {'state': 'PUBLICATION_SOURCE_BOUND'}
        if _checked_graph(m, graph_dir, config_path) != expected:
            raise ValueError('publication persisted graph identity changed')
        if set(p.name for p in graph_dir.iterdir()) != {'projection.json', 'graph-receipt.json'}:
            raise ValueError('unexpected publication graph files')
    else:
        if current != expected:
            raise ValueError('publication no-movement base changed')
        if _checked_graph(m, _relative(root, expected['release_path']), _relative(root, intent['config']['base_graph_config'])) != expected:
            raise ValueError('publication existing graph changed')
    closure_dir, proof = _closure(m, output, graph_dir, config_path)
    allowed = {closure_dir / 'closure.json'}
    if graph_dir is not None:
        allowed.update({graph_dir / 'projection.json', graph_dir / 'graph-receipt.json'})
    _worktree_changes(root, allowed, pointer_may_change=intent['movement'])
    if proof is None:
        if intent['movement'] and current == expected:
            raise ValueError('publication pointer moved without validated closure')
        return {'state': 'PUBLICATION_GRAPH_STAGED' if intent['movement'] else 'PUBLICATION_INTENT_BOUND'}
    if current != expected:
        return {'state': 'PUBLICATION_READY_TO_PROMOTE'}
    receipt = {'schema_version': 1, 'manifest_sha256': m['manifest_sha256'],
        'intent_sha256': ledger._hash(intent), 'preview_sha256': intent['preview_sha256'],
        'review_sha256': intent['review_sha256'], 'pointer': expected,
        'closure_dir': str(closure_dir), 'closure_sha256': canonical_sha256(proof),
        'graph_moved': intent['movement'], 'canonical_published': bool(intent['movement']),
        'closure_validated': True, 'source_commit': source['commit'] if source else intent['reviewed_execution_commit']}
    existing = _binding(m, 'publication-completion')
    if existing is not None and existing != receipt:
        raise ValueError('publication completion receipt changed')
    return {'state': 'COMPLETE' if existing else 'PUBLICATION_VALIDATED_PENDING_RECEIPT', 'receipt': receipt}


def publish(directory, *, config_path=None):
    """Explicit continuation; no model transport, automatic commit or next batch."""
    directory = controller._paths(directory)
    with ledger._lock(directory / '.lock'):
        m = controller._load(directory)
        intent = _binding(m, 'publication-intent')
        if intent is None:
            if config_path is None:
                return {'state': 'WAITING_PUBLICATION_CONFIG'}
            intent = _intent(m, ledger._read(controller._paths(config_path)))
        elif config_path is not None and ledger._read(controller._paths(config_path)) != intent['config']:
            raise ValueError('publication config already bound')
        _verify_intent(m, intent)
        root = Path(m['root']); output = _relative(root, intent['config']['output_root'])
        for _ in range(8):
            state = inspect(m)
            kind = state['state']
            if kind == 'COMPLETE':
                return state
            if kind == 'PUBLICATION_VALIDATED_PENDING_RECEIPT':
                _durable_files(root, [Path(state['receipt']['closure_dir']) / 'closure.json'])
                _binding(m, 'publication-completion', state['receipt'])
                continue
            if kind == 'PUBLICATION_INTENT_BOUND' and intent['movement']:
                closure.persist_batch_activation(Path(m['workflow_dir']), output_root=output / 'activations', **_options(m))
                continue
            if kind == 'PUBLICATION_ACTIVATION_STAGED':
                ledger._write(output / 'graph-config.json', intent['graph_config'])
                continue
            if kind == 'WAITING_PUBLICATION_SOURCE_COMMIT':
                source = _source(m, intent, output / 'graph-config.json')
                if source is None:
                    return state
                continue
            if kind == 'PUBLICATION_SOURCE_BOUND':
                graph.run_graph_release(output / 'graph-config.json', output_root=output / 'versions',
                    pointer_path=directory / 'staged-graph-pointer.json', **_graph_options(m))
                continue
            if kind in ('PUBLICATION_GRAPH_STAGED', 'PUBLICATION_INTENT_BOUND'):
                source = _binding(m, 'publication-source')
                graph_dir = _graph_identity(m, intent, source, output / 'graph-config.json')[0] if intent['movement'] else None
                _closure(m, output, graph_dir, output / 'graph-config.json' if intent['movement'] else None, create=True)
                continue
            if kind == 'PUBLICATION_READY_TO_PROMOTE':
                from turbo.universe.graph_publication import promote_pointer
                source = _binding(m, 'publication-source')
                _, target = _graph_identity(m, intent, source, output / 'graph-config.json')
                def validate():
                    checked = inspect(m)
                    if checked['state'] not in ('PUBLICATION_READY_TO_PROMOTE', 'PUBLICATION_VALIDATED_PENDING_RECEIPT', 'COMPLETE'):
                        raise ValueError('publication no longer ready for guarded promotion')
                    graph_dir, _ = _graph_identity(m, intent, source, output / 'graph-config.json')
                    closure_dir, _ = _closure(m, output, graph_dir, output / 'graph-config.json')
                    files = [root / name for name in source['files']]
                    files += [graph_dir / 'graph-receipt.json', graph_dir / 'projection.json', closure_dir / 'closure.json']
                    _durable_files(root, files)
                promote_pointer(root=root, pointer_path=root / 'data/generated/latest-graph.json',
                    expected_pointer=intent['base_pointer'], new_pointer=target, validate=validate)
                continue
            raise ValueError('unknown publication transition')
        raise ValueError('publication transition bound exceeded')
