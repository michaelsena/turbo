"""Guarded pointer promotion, kept outside historically hashed graph compilers.

Supported canonical writers (CLI and controller) share this lock. The original
compiler-level run_graph_release remains a low-level staging primitive; callers
must supply a private pointer and use this module to promote canonical pointers.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from turbo.pipeline_paths import ROOT
from turbo.universe import graph_release


def _path(path):
    path = Path(path).absolute()
    if path != path.resolve():
        raise ValueError('pointer publication requires resolved non-symlink paths')
    return path


def _canonical(root, pointer_path=None):
    root = _path(root)
    top = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip()
    if _path(top) != root:
        raise ValueError('publication root must be exact Git top-level')
    canonical = root / 'data/generated/latest-graph.json'
    pointer = _path(pointer_path or canonical)
    if pointer != canonical:
        raise ValueError('publication requires canonical graph pointer')
    return root, pointer


def _read(path):
    if path.is_symlink():
        raise ValueError('symlink graph pointer')
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('graph pointer must be a regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('graph pointer must be an object')
    return value


def _sync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked(root, pointer):
    git_dir = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--absolute-git-dir'], text=True).strip()
    lock_root = _path(Path(git_dir) / 'turbo-publication-locks')
    lock_root.mkdir(exist_ok=True)
    lock_path = lock_root / (hashlib.sha256(str(pointer).encode()).hexdigest() + '.lock')
    if lock_path.is_symlink():
        raise ValueError('symlink graph publication lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def promote_pointer(*, root, pointer_path, expected_pointer, new_pointer, validate):
    """Validate under the shared lock, compare exact base, then durably replace.

An exact repeated target is a validated no-op. Any other current pointer stops.
The callback must validate graph/closure/source bindings without moving pointers.
"""
    root, pointer = _canonical(root, pointer_path)
    with _locked(root, pointer):
        current = _read(pointer)
        if current not in (expected_pointer, new_pointer):
            raise ValueError('canonical graph base changed before promotion')
        validate()
        # Catch changes by unsupported writers during validation as well.
        if _read(pointer) != current:
            raise ValueError('canonical graph pointer changed during validation')
        if current == new_pointer:
            return {'promoted': False, 'pointer': new_pointer}
        pointer.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.graph-pointer-', dir=pointer.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write((json.dumps(new_pointer, indent=2, sort_keys=True) + '\n').encode())
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, pointer)
            _sync(pointer.parent)
        finally:
            if temp.exists():
                temp.unlink()
        if _read(pointer) != new_pointer:
            raise ValueError('canonical graph pointer changed after promotion')
        return {'promoted': True, 'pointer': new_pointer}


def run_graph_release(config_path, *, output_root=None, pointer_path=None, root=ROOT,
                      input_root=None, preparation_dirs=None):
    """CLI writer: unchanged compilation to private staging, guarded promotion."""
    root, pointer = _canonical(root, pointer_path)
    expected = _read(pointer)
    options = {'root': root, 'input_root': input_root, 'preparation_dirs': preparation_dirs}
    # Staging outside the worktree preserves the compiler's existing clean gate.
    with tempfile.TemporaryDirectory(prefix='turbo-graph-stage-') as temporary:
        staged = Path(temporary) / 'pointer.json'
        result = graph_release.run_graph_release(config_path, output_root=output_root,
            pointer_path=staged, **options)
        target = _read(staged)
        def validate():
            if graph_release._git_head(root) != result['execution_commit']:
                raise ValueError('graph publication source commit changed')
            checked = graph_release.validate_graph_release(Path(result['release_dir']), config_path, **options)
            if checked.get('valid') is not True:
                raise ValueError('staged graph cannot replay before promotion')
            receipt = graph_release._load_object(Path(result['release_dir']) / 'graph-receipt.json')
            exact = {'schema_version': 1, 'release_id': receipt['release_id'],
                'graph_version_id': receipt['graph_version_id'], 'source_universe_run_id': receipt['source_universe_run_id'],
                'release_path': str(Path(result['release_dir']).relative_to(root)),
                'receipt_sha256': graph_release.canonical_sha256(receipt), 'projection_sha256': receipt['projection_sha256']}
            if target != exact:
                raise ValueError('staged graph pointer binding changed')
            release_dir = _path(Path(result['release_dir']))
            for name in ('projection.json', 'graph-receipt.json'):
                path = _path(release_dir / name)
                with path.open('rb') as stream:
                    os.fsync(stream.fileno())
            _sync(release_dir); _sync(release_dir.parent)
        promote_pointer(root=root, pointer_path=pointer, expected_pointer=expected,
                        new_pointer=target, validate=validate)
        return result
