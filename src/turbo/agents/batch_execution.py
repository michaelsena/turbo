"""Local, conservative execution journal for simulation-only batch transports.

The caller supplies a fake transport. There is no production provider adapter here.
The journal is fail-closed after ambiguous dispatch, including truncated writes.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.batch_authorization import (
    canonical_bytes, max_reservation_microusd, utc_datetime, utc_now,
    validate_authorization, validate_authorization_document, validate_schema,
)
from turbo.pipeline_paths import ROOT

ACTIVE = {"reserved", "dispatched", "unresolved"}


def _fields(data: dict[str, Any], fields: set[str]) -> None:
    if set(data) != fields:
        raise ValueError("event payload fields mismatch")


def _identifier(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", value):
        raise ValueError("invalid request or worker identifier")


def _response_cost(response: Any, auth: dict[str, Any]) -> int:
    if not isinstance(response, dict) or set(response) != {"outcome", "output", "usage"}:
        raise ValueError("response requires outcome, output and usage")
    if not isinstance(response["outcome"], str) or response["outcome"] not in {"succeeded", "failed"} or not isinstance(response["output"], dict):
        raise ValueError("invalid response outcome or output")
    usage = response["usage"]
    if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"}:
        raise ValueError("missing or malformed usage")
    for kind in ("input", "output"):
        count = usage[kind + "_tokens"]
        if type(count) is not int or not 0 <= count <= auth["max_" + kind + "_tokens"]:
            raise ValueError("usage exceeds reservation or is not a nonnegative integer")
    def reject_floats(value: Any) -> None:
        if isinstance(value, float):
            raise ValueError("simulation response must not contain floating-point values")
        if isinstance(value, dict):
            for item in value.values(): reject_floats(item)
        elif isinstance(value, list):
            for item in value: reject_floats(item)
    reject_floats(response)
    canonical_bytes(response)  # Reject NaN and non-JSON values before recording anything.
    return (usage["input_tokens"] * auth["pricing"]["input_microusd_per_token"]
            + usage["output_tokens"] * auth["pricing"]["output_microusd_per_token"])


def replay_events(events: list[dict[str, Any]], authorization: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    """Replay all arithmetic and transitions, not merely the self-declared hashes."""
    auth = authorization
    validate_authorization_document(auth, root=root)
    requests: dict[str, dict[str, Any]] = {}
    state: dict[str, Any] = {"requests": requests, "committed_microusd": 0,
        "outstanding_microusd": 0, "calls_reserved": 0, "retries_reserved": 0,
        "active_requests": 0, "events_count": 0, "last_event_sha256": None,
        "authorization_sha256": canonical_sha256(auth), "mode": "simulation_only",
        "budget_scope": "single_journal_simulation", "model_invoked": False}
    previous_time = None
    if not events:
        raise ValueError("execution journal has no opened event")
    for index, event in enumerate(events):
        validate_schema(event, "batch-execution-event.schema.json", root)
        unsigned = {key: value for key, value in event.items() if key != "sha256"}
        now = utc_datetime(event["at_utc"])
        if (event["sequence"] != index or event["previous_sha256"] != state["last_event_sha256"]
                or event["authorization_sha256"] != state["authorization_sha256"]
                or event["sha256"] != canonical_sha256(unsigned)):
            raise ValueError("event hash chain or authorization mismatch")
        if previous_time is not None and now < previous_time:
            raise ValueError("event time moves backwards")
        previous_time = now
        kind, data = event["kind"], event["data"]
        if index == 0:
            if kind != "opened" or data:
                raise ValueError("first event must open the journal")
        elif kind == "opened":
            raise ValueError("duplicate opened event")
        elif kind == "reserved":
            _fields(data, {"request_id", "worker_id", "retry_of", "lease_until_utc", "reserved_microusd"})
            request_id, worker_id = data["request_id"], data["worker_id"]
            _identifier(request_id); _identifier(worker_id)
            if request_id in requests:
                raise ValueError("duplicate request reservation")
            if not utc_datetime(auth["valid_from_utc"]) <= now < utc_datetime(auth["expires_at_utc"]):
                raise ValueError("reservation outside authorization interval")
            if utc_datetime(data["lease_until_utc"]) != now + timedelta(seconds=auth["lease_seconds"]):
                raise ValueError("incorrect lease deadline")
            amount = max_reservation_microusd(auth)
            if type(data["reserved_microusd"]) is not int or data["reserved_microusd"] != amount:
                raise ValueError("reservation amount mismatch")
            retry_of = data["retry_of"]
            if retry_of is not None:
                _identifier(retry_of)
                predecessor = requests.get(retry_of)
                if predecessor is None or predecessor["status"] not in {"failed", "released"}:
                    raise ValueError("retry requires a settled failed or safely released predecessor")
                if any(row["retry_of"] == retry_of for row in requests.values()):
                    raise ValueError("retry chain cannot fork")
                if state["retries_reserved"] >= auth["max_retries"]:
                    raise ValueError("retry allowance exhausted")
            elif requests:
                raise ValueError("a batch has one initial request; subsequent attempts require retry_of")
            if state["calls_reserved"] >= auth["max_calls"]:
                raise ValueError("call allowance exhausted")
            if state["active_requests"] >= auth["max_concurrency"]:
                raise ValueError("concurrency allowance exhausted")
            if state["committed_microusd"] + state["outstanding_microusd"] + amount > auth["max_cost_microusd"]:
                raise ValueError("cost allowance exhausted")
            requests[request_id] = {**copy.deepcopy(data), "status": "reserved"}
            state["calls_reserved"] += 1
            state["retries_reserved"] += int(retry_of is not None)
        else:
            if kind == "dispatched":
                _fields(data, {"request_id", "worker_id"})
            elif kind == "settled":
                _fields(data, {"request_id", "worker_id", "response", "cost_microusd"})
            elif kind in {"released", "unresolved"}:
                _fields(data, {"request_id", "reason"})
                if not isinstance(data["reason"], str) or data["reason"] not in {"lease_expired", "transport_exception", "invalid_response"}:
                    raise ValueError("invalid recovery reason")
            else:
                raise ValueError("unknown event kind")
            _identifier(data["request_id"])
            request = requests.get(data["request_id"])
            if request is None:
                raise ValueError("event references an unknown request")
            if "worker_id" in data and data["worker_id"] != request["worker_id"]:
                raise ValueError("worker does not own this lease")
            if kind == "dispatched":
                if request["status"] != "reserved" or now >= utc_datetime(request["lease_until_utc"]):
                    raise ValueError("dispatch requires an unexpired reserved lease")
                if not utc_datetime(auth["valid_from_utc"]) <= now < utc_datetime(auth["expires_at_utc"]):
                    raise ValueError("dispatch outside authorization interval")
                request["status"] = "dispatched"
            elif kind == "settled":
                if request["status"] not in {"dispatched", "unresolved"}:
                    raise ValueError("settlement requires dispatch")
                cost = _response_cost(data["response"], auth)
                if type(data["cost_microusd"]) is not int or cost != data["cost_microusd"]:
                    raise ValueError("settlement cost mismatch")
                request.update(status=data["response"]["outcome"], response=copy.deepcopy(data["response"]), cost_microusd=cost)
                state["committed_microusd"] += cost
            elif kind == "released":
                if request["status"] != "reserved" or data["reason"] != "lease_expired" or now < utc_datetime(request["lease_until_utc"]):
                    raise ValueError("only an expired undispatched reservation can be released")
                request["status"] = "released"
            elif kind == "unresolved":
                if request["status"] != "dispatched":
                    raise ValueError("only a dispatched attempt can become unresolved")
                if data["reason"] == "lease_expired" and now < utc_datetime(request["lease_until_utc"]):
                    raise ValueError("lease has not expired")
                request["status"] = "unresolved"
        state["outstanding_microusd"] = sum(r["reserved_microusd"] for r in requests.values() if r["status"] in ACTIVE)
        state["active_requests"] = sum(r["status"] in ACTIVE for r in requests.values())
        if state["committed_microusd"] + state["outstanding_microusd"] > auth["max_cost_microusd"]:
            raise ValueError("replayed budget exceeds authorization")
        state["last_event_sha256"] = event["sha256"]
        state["events_count"] = index + 1
    return state


def _read(directory: Path, root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        raw_auth = (directory / "authorization.json").read_bytes()
        auth = json.loads(raw_auth)
        if raw_auth != canonical_bytes(auth):
            raise ValueError("authorization file is not canonical")
        raw = (directory / "events.jsonl").read_bytes()
        lines = raw.splitlines(keepends=True)
        events = [json.loads(line) for line in lines]
        if any(line != canonical_bytes(event) for line, event in zip(lines, events)):
            raise ValueError("journal has noncanonical or incomplete bytes")
        replay_events(events, auth, root=root)
        return auth, events
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as error:
        raise ValueError("execution journal cannot replay") from error


def inspect_execution(directory: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Read-only historical journal validation; does not verify preparation files."""
    directory = Path(directory)
    # Read using the existing lock without creating or modifying a path.
    try:
        with (directory / ".lock").open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            auth, events = _read(directory, root)
            return replay_events(events, auth, root=root)
    except OSError as error:
        raise ValueError("execution lock is unavailable") from error


def validate_execution(directory: Path, preparation_dirs: Iterable[Path], *, root: Path = ROOT) -> dict[str, Any]:
    state = inspect_execution(directory, root=root)
    auth = json.loads((Path(directory) / "authorization.json").read_text())
    validate_authorization(auth, preparation_dirs, root=root, enforce_time=False)
    return {"valid": True, "errors": [], **state, "preparations_verified": True}


class BatchExecution:
    def __init__(self, directory: Path, authorization: dict[str, Any], preparation_dirs: Iterable[Path], *, root: Path = ROOT, clock: Callable[[], str] = utc_now):
        self.directory, self.root = Path(directory), Path(root)
        self.authorization = copy.deepcopy(authorization)
        self.preparation_dirs = [Path(p) for p in preparation_dirs]
        self.clock = clock
        validate_authorization(self.authorization, self.preparation_dirs, root=self.root, enforce_time=False)
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._lock():
            path = self.directory / "authorization.json"
            if path.exists():
                auth, _ = _read(self.directory, self.root)
                if auth != self.authorization:
                    raise ValueError("execution authorization cannot change")
            else:
                if (self.directory / "events.jsonl").exists():
                    raise ValueError("orphan journal cannot be reinitialized")
                with path.open("xb") as handle:
                    handle.write(canonical_bytes(self.authorization)); handle.flush(); os.fsync(handle.fileno())
                self._append([], "opened", {}, self.clock())
                descriptor = os.open(self.directory, os.O_RDONLY)
                try: os.fsync(descriptor)
                finally: os.close(descriptor)

    @contextmanager
    def _lock(self):
        with (self.directory / ".lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    def _load(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        auth, events = _read(self.directory, self.root)
        if auth != self.authorization:
            raise ValueError("execution authorization cannot change")
        return events, replay_events(events, auth, root=self.root)

    def _append(self, events: list[dict[str, Any]], kind: str, data: dict[str, Any], now: str) -> dict[str, Any]:
        event = {"schema_version": 1, "sequence": len(events), "at_utc": now,
                 "authorization_sha256": canonical_sha256(self.authorization),
                 "previous_sha256": events[-1]["sha256"] if events else None,
                 "kind": kind, "data": data}
        event["sha256"] = canonical_sha256(event)
        result = replay_events([*events, event], self.authorization, root=self.root)
        with (self.directory / "events.jsonl").open("ab") as handle:
            handle.write(canonical_bytes(event)); handle.flush(); os.fsync(handle.fileno())
        return result

    def status(self) -> dict[str, Any]:
        return inspect_execution(self.directory, root=self.root)

    def validate(self) -> dict[str, Any]:
        return validate_execution(self.directory, self.preparation_dirs, root=self.root)

    def reserve(self, request_id: str, worker_id: str, retry_of: str | None = None) -> dict[str, Any]:
        validate_authorization(self.authorization, self.preparation_dirs, root=self.root, now=self.clock())
        with self._lock():
            events, state = self._load()
            if request_id in state["requests"]:
                existing = state["requests"][request_id]
                if existing["worker_id"] == worker_id and existing["retry_of"] == retry_of:
                    return existing
                raise ValueError("request ID already belongs to a different attempt")
            now = self.clock()
            lease_until = (utc_datetime(now) + timedelta(seconds=self.authorization["lease_seconds"])).isoformat().replace("+00:00", "Z")
            result = self._append(events, "reserved", dict(request_id=request_id, worker_id=worker_id,
                retry_of=retry_of, lease_until_utc=lease_until,
                reserved_microusd=max_reservation_microusd(self.authorization)), now)
            return result["requests"][request_id]

    def dispatch(self, request_id: str, worker_id: str, transport: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        validate_authorization(self.authorization, self.preparation_dirs, root=self.root, now=self.clock())
        with self._lock():
            events, state = self._load()
            request = state["requests"].get(request_id)
            if request is None or request["worker_id"] != worker_id:
                raise ValueError("request or worker mismatch")
            if request["status"] != "reserved":
                return request  # Resume never re-sends a dispatched or terminal attempt.
            # Read verified exact bytes into the envelope before durable dispatch intent.
            families = []
            for binding, path in zip(self.authorization["families"], self.preparation_dirs):
                import hashlib
                raw = (path / "family-evidence-pack-v2.json").read_bytes()
                if hashlib.sha256(raw).hexdigest() != binding["pack_file_sha256"]:
                    raise ValueError("pack changed before dispatch")
                families.append({"family_id": binding["family_id"], "preparation_id": binding["preparation_id"], "pack": json.loads(raw)})
            envelope = {"request_id": request_id, "authorization_sha256": canonical_sha256(self.authorization),
                        "provider": "simulation", "model": self.authorization["model"], "role": "batch_primary",
                        "prompt_sha256": self.authorization["prompt_sha256"], "families": families,
                        "max_input_tokens": self.authorization["max_input_tokens"],
                        "max_output_tokens": self.authorization["max_output_tokens"]}
            self._append(events, "dispatched", {"request_id": request_id, "worker_id": worker_id}, self.clock())
        try:
            response = transport(envelope)
        except Exception:
            return self._unresolved(request_id, "transport_exception")
        try:
            _response_cost(response, self.authorization)
        except (ValueError, TypeError, OverflowError):
            return self._unresolved(request_id, "invalid_response")
        return self.settle(request_id, worker_id, response)

    def _unresolved(self, request_id: str, reason: str) -> dict[str, Any]:
        with self._lock():
            events, state = self._load()
            request = state["requests"][request_id]
            if request["status"] != "dispatched":
                return request
            return self._append(events, "unresolved", {"request_id": request_id, "reason": reason}, self.clock())["requests"][request_id]

    def settle(self, request_id: str, worker_id: str, response: dict[str, Any]) -> dict[str, Any]:
        cost = _response_cost(response, self.authorization)
        with self._lock():
            events, state = self._load()
            request = state["requests"].get(request_id)
            if request is None or request["worker_id"] != worker_id:
                raise ValueError("request or worker mismatch")
            if request["status"] in {"succeeded", "failed"}:
                if request["response"] != response:
                    raise ValueError("conflicting duplicate response")
                return request
            return self._append(events, "settled", dict(request_id=request_id, worker_id=worker_id,
                response=copy.deepcopy(response), cost_microusd=cost), self.clock())["requests"][request_id]

    def recover_expired(self) -> dict[str, Any]:
        with self._lock():
            events, state = self._load()
            now = self.clock()
            for request_id, request in list(state["requests"].items()):
                if request["status"] in {"reserved", "dispatched"} and utc_datetime(now) >= utc_datetime(request["lease_until_utc"]):
                    kind = "released" if request["status"] == "reserved" else "unresolved"
                    self._append(events, kind, {"request_id": request_id, "reason": "lease_expired"}, now)
                    events, state = self._load()
            return state
