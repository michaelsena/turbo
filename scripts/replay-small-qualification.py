#!/usr/bin/env python3
"""Verify a published pilot; explicit restoration only copies immutable bytes."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

INPUT_COMMIT = 'e9e7c4c93bfb601bac4a0368cde20fda40044321'
DEFAULT_MANIFEST = 'data/research_pilots/small-qualification-20261109/publication-manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_symlinks(path):
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError('symlink is not permitted: ' + str(candidate))


def relative_path(root, value):
    path = Path(value)
    if path.is_absolute() or not path.parts or any(p in ('.', '..') for p in path.parts):
        raise ValueError('expected a repository-relative path')
    result = root / path
    no_symlinks(result)
    return result


def regular_files(directory):
    no_symlinks(directory)
    if not directory.is_dir():
        raise ValueError('missing artifact directory: ' + str(directory))
    result = []
    for path in directory.rglob('*'):
        no_symlinks(path)
        if path.is_file():
            result.append(path)
        elif not path.is_dir():
            raise ValueError('nonregular artifact: ' + str(path))
    return result


def load_manifest(root, path):
    no_symlinks(path)
    manifest = json.loads(path.read_text())
    if manifest.get('schema_version') != 1 or manifest.get('input_commit') != INPUT_COMMIT:
        raise ValueError('unsupported publication manifest or frozen input commit')
    files = manifest['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('manifest requires exact file hashes')
    for name, expected in files.items():
        source = relative_path(root, name)
        if not source.is_file() or digest(source) != expected:
            raise ValueError('artifact hash mismatch: ' + name)
    for name in [manifest['workflow_dir'], *manifest['preparation_dirs'], manifest['release_dir'], manifest['closure_dir']]:
        for source in regular_files(relative_path(root, name)):
            if source.relative_to(root).as_posix() not in files:
                raise ValueError('unlisted artifact: ' + str(source))
    config_path = relative_path(root, manifest['graph_config'])
    if config_path.relative_to(root).as_posix() not in files:
        raise ValueError('graph config is not hash bound')
    config = json.loads(config_path.read_text())
    workflow = Path(manifest['workflow_locator'])
    if not workflow.is_absolute() or workflow != workflow.resolve():
        raise ValueError('workflow locator must be a canonical absolute path')
    found = False
    for activation in config['activations']:
        activation_config = relative_path(root, activation['activation_config'])
        if activation_config.relative_to(root).as_posix() not in files:
            raise ValueError('activation config is not hash bound')
        value = json.loads(activation_config.read_text())
        if 'workflow_dir' in value:
            if value['workflow_dir'] != str(workflow):
                raise ValueError('activation workflow locator mismatch')
            found = True
    if not found:
        raise ValueError('no workflow activation in graph config')
    return manifest


def restore_plan(source, target, *, restore):
    """Check every collision before creating anything; never overwrite a file."""
    no_symlinks(target)
    if target.exists() and not target.is_dir():
        raise ValueError('workflow target is not a directory')
    expected = {p.relative_to(source): p for p in regular_files(source)}
    if target.exists():
        for existing in regular_files(target):
            rel = existing.relative_to(target)
            if rel == Path('.lock') and existing.stat().st_size == 0:
                continue
            if rel not in expected or digest(existing) != digest(expected[rel]):
                raise ValueError('existing workflow file differs: ' + str(existing))
    missing = []
    for rel, original in expected.items():
        destination = target / rel
        no_symlinks(destination)
        for parent in destination.parents:
            if parent.exists() and not parent.is_dir():
                raise ValueError('workflow parent is not a directory')
        if destination.exists():
            if not destination.is_file() or digest(destination) != digest(original):
                raise ValueError('existing workflow file differs: ' + str(destination))
        else:
            missing.append((original, destination))
    lock = target / '.lock'
    no_symlinks(lock)
    if lock.exists() and (not lock.is_file() or lock.stat().st_size):
        raise ValueError('workflow lock must be an empty regular file')
    if not lock.exists() and not restore:
        raise ValueError('workflow lock missing; explicit --restore is required')
    if missing and not restore:
        raise ValueError('workflow is absent or incomplete; explicit --restore is required')
    return missing


def copy_missing(plan):
    for original, destination in plan:
        no_symlinks(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as output, original.open('rb') as source:
            shutil.copyfileobj(source, output)
        if digest(destination) != digest(original):
            raise ValueError('restored artifact hash mismatch')


def git(root, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(root), *args], text=True, stderr=subprocess.PIPE).strip()


def input_objects(root, manifest):
    capsule_path = relative_path(root, manifest['input_objects'])
    if manifest['files'].get(manifest['input_objects']) != digest(capsule_path):
        raise ValueError('input object capsule is not hash bound')
    capsule = json.loads(capsule_path.read_text())
    if (capsule.get('schema_version') != 1 or capsule.get('input_commit') != INPUT_COMMIT
            or capsule.get('input_tree') != manifest['input_tree']):
        raise ValueError('input object capsule binding mismatch')
    objects = []
    seen = set()
    for item in capsule['objects']:
        kind = item['type']
        if kind not in ('commit', 'tree', 'blob'):
            raise ValueError('unsupported input object type')
        raw = base64.b64decode(item['base64'], validate=True)
        actual = hashlib.sha1((kind + ' ' + str(len(raw)) + '\0').encode() + raw).hexdigest()
        if actual != item['sha1'] or actual in seen:
            raise ValueError('input object SHA1 mismatch or duplicate')
        seen.add(actual)
        objects.append((kind, actual, raw))
    if INPUT_COMMIT not in seen:
        raise ValueError('input capsule must contain the pinned commit')
    return objects


def frozen_input(root, path, manifest, *, restore):
    no_symlinks(path)
    if not path.exists():
        if not restore:
            raise ValueError('frozen input checkout missing; explicit --restore is required')
        objects = input_objects(root, manifest)
        subprocess.run(['git', 'clone', '--local', '--no-hardlinks', '--no-checkout', str(root), str(path)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for kind, expected, raw in objects:
            actual = subprocess.check_output(['git', '-C', str(path), 'hash-object', '-w', '-t', kind, '--stdin'],
                                             input=raw, stderr=subprocess.PIPE).decode().strip()
            if actual != expected:
                raise ValueError('imported input object SHA1 mismatch')
        subprocess.run(['git', '-C', str(path), 'checkout', '--detach', INPUT_COMMIT],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if (Path(git(path, 'rev-parse', '--show-toplevel')).resolve() != path
            or git(path, 'rev-parse', 'HEAD') != INPUT_COMMIT
            or git(path, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('input root must be an unchanged checkout of the pinned commit')
    if manifest.get('input_tree') and git(path, 'rev-parse', 'HEAD^{tree}') != manifest['input_tree']:
        raise ValueError('frozen input tree mismatch')


def external_path(path):
    path = path.absolute()
    # /tmp is a platform alias on macOS; no user-created link is accepted.
    if path.is_relative_to('/tmp'):
        path = Path('/tmp').resolve() / path.relative_to('/tmp')
    no_symlinks(path)
    return path.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(root, relative_path(root, args.manifest))
    target = Path(manifest['workflow_locator'])
    if args.restore and args.runtime_root is None:
        raise ValueError('--restore requires explicit --runtime-root')
    if args.runtime_root is not None and external_path(args.runtime_root) != target.parent:
        raise ValueError('runtime root must match the published activation workflow parent')
    input_root = external_path(args.input_root)
    plan = restore_plan(relative_path(root, manifest['workflow_dir']), target, restore=args.restore)
    frozen_input(root, input_root, manifest, restore=args.restore)
    if args.restore:
        copy_missing(plan)
        lock = target / '.lock'
        no_symlinks(lock)
        if not lock.exists():
            lock.touch(exist_ok=False)
    sys.path.insert(0, str(root / 'src'))
    from turbo.universe.graph_release import validate_graph_release
    from turbo.universe.batch_closure import validate_batch_closure
    common = dict(root=root, input_root=input_root,
                  preparation_dirs=[relative_path(root, p) for p in manifest['preparation_dirs']])
    release = relative_path(root, manifest['release_dir'])
    config = relative_path(root, manifest['graph_config'])
    graph = validate_graph_release(release, config, **common)
    closure = validate_batch_closure(relative_path(root, manifest['closure_dir']), target,
                                     graph_release_dir=release, graph_release_config=config, **common)
    print(json.dumps({'valid': graph['valid'] and closure['valid'], 'graph': graph, 'closure': closure,
                      'restored_files': len(plan) if args.restore else 0}, indent=2))
    return 0 if graph['valid'] and closure['valid'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
