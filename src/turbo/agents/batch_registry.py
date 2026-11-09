"""One explicitly initialized, trusted local registry for simulation journals.

Managed clients reuse the same canonical journal for the same authorization bytes.
This is neither a grant-signing system nor a budget shared across independent
registries. The trusted operator must retain this directory intact at its bound
path. No API deletes claims, repairs partial initialization, or resets a journal.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

from turbo.agents.batch_authorization import (
    canonical_bytes, utc_datetime, utc_now, validate_authorization, validate_schema,
)
from turbo.agents.batch_execution import BatchExecution, inspect_execution, validate_execution
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT

SCHEMA = "batch-registry.schema.json"
IMPLEMENTATION = "src/turbo/agents/batch_registry.py"
DIGEST = re.compile(r"[0-9a-f]{64}")


def _regular(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError("required registry file is missing") from error
    if not stat.S_ISREG(mode):
        raise ValueError("registry files must be regular files, not symlinks")


def _directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError("required registry directory is missing") from error
    if not stat.S_ISDIR(mode):
        raise ValueError("registry directories must not be symlinks")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new(path: Path, document: dict[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(canonical_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _read_document(path: Path, root: Path, kind: str) -> dict[str, Any]:
    _regular(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        if raw != canonical_bytes(value):
            raise ValueError("registry document bytes are not canonical")
        validate_schema(value, SCHEMA, root)
        if value["kind"] != kind:
            raise ValueError("registry document kind mismatch")
        return value
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as error:
        raise ValueError("registry document cannot replay") from error


def _resolved_registry(path: Path) -> Path:
    path = Path(path)
    # Parent aliases such as macOS /tmp -> /private/tmp normalize to one lock.
    # The user-selected registry itself cannot be a symlink.
    if path.is_symlink():
        raise ValueError("registry root must not be a symlink")
    try:
        result = path.resolve(strict=True)
    except OSError as error:
        raise ValueError("registry must be explicitly initialized first") from error
    _directory(result)
    return result


def initialize_registry(
    directory: Path, *, root: Path = ROOT, clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """Create a new registry. Existing or partial directories are never adopted."""
    directory, root = Path(directory), Path(root)
    if directory.exists() or directory.is_symlink():
        raise ValueError("registry initialization requires a new directory")
    try:
        parent = directory.parent.resolve(strict=True)
    except OSError as error:
        raise ValueError("registry parent must already exist") from error
    _directory(parent)
    destination = parent / directory.name
    now = clock()
    utc_datetime(now)
    metadata = {
        "schema_version": 1, "kind": "registry", "mode": "simulation_only",
        "registry_id": "batch-registry:" + uuid.uuid4().hex,
        "registry_path": str(destination), "created_at_utc": now,
        "schema_sha256": hashlib.sha256((root / "schemas" / SCHEMA).read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256((root / IMPLEMENTATION).read_bytes()).hexdigest(),
    }
    validate_schema(metadata, SCHEMA, root)
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise ValueError("registry already exists") from error
    _fsync_directory(parent)
    # Metadata comes last. Any interrupted initialization remains unusable.
    with (destination / ".lock").open("xb") as handle:
        handle.flush(); os.fsync(handle.fileno())
    (destination / "claims").mkdir()
    (destination / "journals").mkdir()
    _fsync_directory(destination)
    _write_new(destination / "registry.json", metadata)
    return metadata


class BatchRegistry:
    """Open an existing registry; creation is a separate explicit operation."""
    def __init__(self, directory: Path, *, root: Path = ROOT):
        self.directory, self.root = _resolved_registry(Path(directory)), Path(root)
        self._metadata = self._load_metadata()

    def _load_metadata(self) -> dict[str, Any]:
        _directory(self.directory)
        _directory(self.directory / "claims")
        _directory(self.directory / "journals")
        _regular(self.directory / ".lock")
        metadata = _read_document(self.directory / "registry.json", self.root, "registry")
        if metadata["registry_path"] != str(self.directory):
            raise ValueError("registry is not at its bound path")
        if metadata["schema_sha256"] != hashlib.sha256((self.root / "schemas" / SCHEMA).read_bytes()).hexdigest():
            raise ValueError("registry schema hash mismatch")
        if metadata["implementation_sha256"] != hashlib.sha256((self.root / IMPLEMENTATION).read_bytes()).hexdigest():
            raise ValueError("registry implementation hash mismatch")
        utc_datetime(metadata["created_at_utc"])
        return metadata

    @contextmanager
    def _locked(self, *, exclusive: bool = False):
        # Missing locks fail closed rather than splitting locking across new inodes.
        _regular(self.directory / ".lock")
        with (self.directory / ".lock").open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            metadata = self._load_metadata()
            if metadata != self._metadata:
                raise ValueError("registry identity cannot change")
            yield metadata

    def _paths(self, digest: str) -> tuple[Path, Path, Path]:
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise ValueError("invalid authorization digest")
        return (self.directory / "claims" / (digest + ".json"),
                self.directory / "claims" / (digest + ".ready.json"),
                self.directory / "journals" / digest)

    def _binding(self, digest: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        claim_path, ready_path, journal = self._paths(digest)
        claim = _read_document(claim_path, self.root, "claim")
        ready = _read_document(ready_path, self.root, "ready")
        metadata = self._metadata
        for document in (claim, ready):
            if (document["registry_id"] != metadata["registry_id"]
                    or document["registry_sha256"] != canonical_sha256(metadata)
                    or document["authorization_sha256"] != digest):
                raise ValueError("claim is not bound to this registry and authorization")
        if claim["journal_path"] != "journals/" + digest:
            raise ValueError("claim journal path is not canonical")
        if ready["claim_sha256"] != canonical_sha256(claim):
            raise ValueError("ready receipt claim hash mismatch")
        utc_datetime(claim["claimed_at_utc"])
        if utc_datetime(ready["ready_at_utc"]) < utc_datetime(claim["claimed_at_utc"]):
            raise ValueError("ready receipt predates claim")
        _directory(journal)
        for name in ("authorization.json", "events.jsonl", ".lock"):
            _regular(journal / name)
        state = inspect_execution(journal, root=self.root)
        if state["authorization_sha256"] != digest:
            raise ValueError("journal authorization differs from claim")
        # inspect_execution has already checked every event and canonical byte.
        with (journal / "events.jsonl").open("rb") as handle:
            opened = json.loads(handle.readline())
        if ready["opened_event_sha256"] != opened["sha256"]:
            raise ValueError("ready receipt does not bind this journal opening")
        return claim, ready, state

    def open(
        self, authorization: dict[str, Any], preparation_dirs: Iterable[Path], *,
        clock: Callable[[], str] = utc_now,
    ) -> ManagedBatchExecution:
        """Claim or reuse the only managed journal for these authorization bytes."""
        auth = copy.deepcopy(authorization)
        preparations = [Path(path) for path in preparation_dirs]
        validate_authorization(auth, preparations, root=self.root, enforce_time=False)
        digest = canonical_sha256(auth)
        claim_path, ready_path, journal = self._paths(digest)
        with self._locked(exclusive=True):
            if claim_path.exists() or claim_path.is_symlink():
                self._binding(digest)  # Partial claims must never reach constructor.
                # All journal files already exist: never recreate a claimed journal.
                execution = BatchExecution(journal, auth, preparations, root=self.root, clock=clock)
            else:
                if ready_path.exists() or ready_path.is_symlink() or journal.exists() or journal.is_symlink():
                    raise ValueError("unclaimed existing journal or ready receipt cannot be adopted")
                now = clock()
                utc_datetime(now)
                claim = {"schema_version": 1, "kind": "claim", "mode": "simulation_only",
                    "registry_id": self._metadata["registry_id"],
                    "registry_sha256": canonical_sha256(self._metadata),
                    "authorization_sha256": digest, "journal_path": "journals/" + digest,
                    "claimed_at_utc": now}
                validate_schema(claim, SCHEMA, self.root)
                _write_new(claim_path, claim)  # Durable claim precedes any journal bytes.
                execution = BatchExecution(journal, auth, preparations, root=self.root, clock=clock)
                _fsync_directory(journal.parent)
                state = execution.status()
                ready = {"schema_version": 1, "kind": "ready", "mode": "simulation_only",
                    "registry_id": self._metadata["registry_id"],
                    "registry_sha256": canonical_sha256(self._metadata),
                    "authorization_sha256": digest, "claim_sha256": canonical_sha256(claim),
                    "opened_event_sha256": state["last_event_sha256"], "ready_at_utc": clock()}
                validate_schema(ready, SCHEMA, self.root)
                if utc_datetime(ready["ready_at_utc"]) < utc_datetime(now):
                    raise ValueError("ready receipt predates claim")
                _write_new(ready_path, ready)
                self._binding(digest)
        return ManagedBatchExecution(self, digest, execution)

    def status(self) -> dict[str, Any]:
        with self._locked():
            claims = self.directory / "claims"
            names = {path.name for path in claims.iterdir()}
            digests = sorted(name[:-5] for name in names if re.fullmatch(r"[0-9a-f]{64}\.json", name))
            expected_names = {name for digest in digests for name in (digest + ".json", digest + ".ready.json")}
            if names != expected_names:
                raise ValueError("registry contains partial or unexpected claim files")
            journal_names = {path.name for path in (self.directory / "journals").iterdir()}
            if journal_names != set(digests):
                raise ValueError("registry contains missing or unclaimed journals")
            entries = []
            for digest in digests:
                _, _, state = self._binding(digest)
                entries.append({"authorization_sha256": digest, "journal_path": "journals/" + digest,
                    "calls_reserved": state["calls_reserved"], "committed_microusd": state["committed_microusd"],
                    "outstanding_microusd": state["outstanding_microusd"], "events_count": state["events_count"]})
            return {"registry_id": self._metadata["registry_id"], "registry_sha256": canonical_sha256(self._metadata),
                "registry_path": str(self.directory), "mode": "simulation_only",
                "managed_budget_scope": "single_registry_exact_authorization", "claims": entries,
                "model_invoked": False}


class ManagedBatchExecution:
    """A managed client has no destination-directory parameter or reset operation."""
    def __init__(self, registry: BatchRegistry, digest: str, execution: BatchExecution):
        self._registry, self._digest, self._execution = registry, digest, execution

    def _check(self) -> None:
        _, _, expected_journal = self._registry._paths(self._digest)
        try:
            actual_journal = Path(self._execution.directory).resolve(strict=True)
            actual_root = Path(self._execution.root).resolve(strict=True)
            expected_root = self._registry.root.resolve(strict=True)
        except OSError as error:
            raise ValueError("managed execution paths are missing") from error
        if actual_journal != expected_journal:
            raise ValueError("managed execution must use its canonical registry journal")
        if canonical_sha256(self._execution.authorization) != self._digest:
            raise ValueError("managed execution authorization differs from its registry claim")
        if actual_root != expected_root:
            raise ValueError("managed execution repository differs from its registry")
        with self._registry._locked():
            self._registry._binding(self._digest)
        # Claims are immutable after ready. The B1 journal has its own lock.
        # Never hold the registry lock across a transport callback.

    def _decorate(self, value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "registry_id": self._registry._metadata["registry_id"],
                "managed_budget_scope": "single_registry_exact_authorization",
                "journal_path": "journals/" + self._digest}

    def status(self) -> dict[str, Any]:
        self._check()
        return self._decorate(self._execution.status())

    def validate(self) -> dict[str, Any]:
        self._check()
        return self._decorate(self._execution.validate())

    def reserve(self, request_id: str, worker_id: str, retry_of: str | None = None) -> dict[str, Any]:
        self._check()
        return self._execution.reserve(request_id, worker_id, retry_of)

    def dispatch(self, request_id: str, worker_id: str, transport: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        self._check()
        return self._execution.dispatch(request_id, worker_id, transport)

    def settle(self, request_id: str, worker_id: str, response: dict[str, Any]) -> dict[str, Any]:
        self._check()
        return self._execution.settle(request_id, worker_id, response)

    def recover_expired(self) -> dict[str, Any]:
        self._check()
        return self._decorate(self._execution.recover_expired())


def inspect_registry(directory: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Read-only validation; never initializes or repairs a missing registry."""
    return BatchRegistry(directory, root=root).status()


def validate_registry_execution(
    directory: Path, authorization_sha256: str, preparation_dirs: Iterable[Path], *, root: Path = ROOT,
) -> dict[str, Any]:
    """Read-only complete replay of an existing managed journal and its inputs."""
    registry = BatchRegistry(directory, root=root)
    with registry._locked():
        registry._binding(authorization_sha256)
        _, _, journal = registry._paths(authorization_sha256)
        result = validate_execution(journal, preparation_dirs, root=root)
        return {**result, "registry_id": registry._metadata["registry_id"],
                "managed_budget_scope": "single_registry_exact_authorization",
                "journal_path": "journals/" + authorization_sha256}
