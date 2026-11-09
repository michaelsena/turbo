from __future__ import annotations

import gzip
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.system_context import compile_system_context


SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,199}")
RECEIPT_KINDS = {
    "source-run": ("data/runs", "run-receipt.json"),
    "family-schedule": ("data/family_schedules", "schedule-receipt.json"),
    "graph-release": ("data/market_graph/versions", "graph-receipt.json"),
    "activation": ("data/market_graph/activations", "activation-receipt.json"),
    "boundary-run": ("data/agent_runs", "run-receipt.json"),
    "independent-review": ("data/agent_reviews", "review.receipt.json"),
}
SENSITIVE_KEY_PARTS = (
    "api_key",
    "credential",
    "authorization",
    "private_reasoning",
    "raw_reasoning",
    "chain_of_thought",
    "secret",
)
READ_MODEL_VERSION = "1.0.0"


class SnapshotError(ValueError):
    """Raised when repository artifacts cannot form one verified read snapshot."""


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise SnapshotError(f"{path} must contain a JSON object")
    return value


def _gzip_object(path: Path) -> dict[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise SnapshotError(f"{path} must contain a JSON object")
    return value


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SnapshotError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _safe_identifier(value: str, label: str) -> str:
    if SAFE_ID.fullmatch(value) is None or value in {".", ".."}:
        raise SnapshotError(f"invalid {label}")
    return value


def _verified_artifact(
    directory: Path,
    name: str,
    expected_sha256: str,
    *,
    gzip_json: bool = False,
) -> dict[str, Any]:
    path = directory / name
    if _sha256_path(path) != expected_sha256:
        raise SnapshotError(f"artifact hash mismatch: {name}")
    return _gzip_object(path) if gzip_json else _object(path)


def _normalize_query(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _contains_query(values: Iterable[object], query: str) -> bool:
    if not query:
        return True
    return query in " ".join(str(value).casefold() for value in values)


def _page(
    items: Sequence[dict[str, Any]],
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if page < 1:
        raise SnapshotError("page must be at least 1")
    if page_size < 1 or page_size > 100:
        raise SnapshotError("page_size must be between 1 and 100")
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": list(items[start : start + page_size]),
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def _sanitize_receipt(value: Any, *, redactions: list[str], path: str = "$") -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.casefold()
            next_path = f"{path}.{key}"
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                redactions.append(next_path)
                continue
            clean[key] = _sanitize_receipt(item, redactions=redactions, path=next_path)
        return clean
    if isinstance(value, list):
        return [
            _sanitize_receipt(item, redactions=redactions, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


@dataclass(frozen=True)
class SnapshotVersion:
    source_run_id: str
    partition_id: str
    graph_version_id: str
    release_id: str
    as_of_utc: str
    fingerprint: str


class ReadSnapshot:
    """One immutable, version-compatible, hash-verified repository view."""

    def __init__(
        self,
        *,
        root: Path,
        context: dict[str, Any],
        source_receipt: dict[str, Any],
        schedule_receipt: dict[str, Any],
        graph_receipt: dict[str, Any],
        reconciliation: dict[str, Any],
        coverage: dict[str, Any],
        candidates: dict[str, Any],
        families: dict[str, Any],
        batches: dict[str, Any],
        projection: dict[str, Any],
    ) -> None:
        self.root = root
        self.context = context
        self.source_receipt = source_receipt
        self.schedule_receipt = schedule_receipt
        self.graph_receipt = graph_receipt
        self.reconciliation = reconciliation
        self.coverage = coverage
        self.candidate_ledger = candidates
        self.family_manifest = families
        self.batch_manifest = batches
        self.projection = projection
        self.version = SnapshotVersion(
            source_run_id=source_receipt["run_id"],
            partition_id=schedule_receipt["partition_id"],
            graph_version_id=graph_receipt["graph_version_id"],
            release_id=graph_receipt["release_id"],
            as_of_utc=max(
                str(schedule_receipt["as_of_utc"]), str(graph_receipt["as_of_utc"])
            ),
            fingerprint=canonical_sha256(
                {
                    "source_run_id": source_receipt["run_id"],
                    "source_hashes": source_receipt["output_hashes"],
                    "partition_id": schedule_receipt["partition_id"],
                    "schedule_hashes": schedule_receipt["output_hashes"],
                    "graph_version_id": graph_receipt["graph_version_id"],
                    "projection_sha256": graph_receipt["projection_sha256"],
                    "read_model_version": READ_MODEL_VERSION,
                }
            ),
        )
        self.identities = {
            item["identity_id"]: item for item in reconciliation["source_identities"]
        }
        self.source_records = {
            item["record_id"]: item for item in reconciliation["source_records"]
        }
        self.reconciliation_mappings = {
            item["normalized_identity_id"]: item
            for item in reconciliation["mappings"]
        }
        self.assignments = {
            item["identity_id"]: item for item in coverage["assignments"]
        }
        self.families = {item["family_id"]: item for item in families["families"]}
        self.candidates = {
            item["candidate_market_id"]: item for item in candidates["candidates"]
        }
        self.markets = {item["market_id"]: item for item in projection["markets"]}
        self.graph_mappings = list(projection["mappings"])
        self.batches = list(batches["batches"])
        self.family_batches = {
            family_id: batch
            for batch in self.batches
            for family_id in batch["family_ids"]
        }
        self.gaps: dict[str, dict[str, Any]] = {}
        for mapping in self.graph_mappings:
            for gap in mapping.get("research_gaps", []):
                self.gaps[gap["gap_id"]] = gap

    @property
    def etag(self) -> str:
        return f'"{self.version.fingerprint}"'

    def provenance(self) -> dict[str, str]:
        return {
            "source_run_id": self.version.source_run_id,
            "partition_id": self.version.partition_id,
            "graph_version_id": self.version.graph_version_id,
            "release_id": self.version.release_id,
            "as_of_utc": self.version.as_of_utc,
            "context_fingerprint": self.version.fingerprint,
            "read_model_version": READ_MODEL_VERSION,
        }

    def list_markets(
        self,
        *,
        query: str | None = None,
        activation_status: str | None = None,
        gap_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        normalized = _normalize_query(query)
        items: list[dict[str, Any]] = []
        for market in self.markets.values():
            if activation_status and market.get("activation_status") != activation_status:
                continue
            if gap_id and gap_id not in market.get("research_gap_ids", []):
                continue
            if not _contains_query(
                (
                    market["market_id"],
                    market["canonical_name"],
                    market["definition"],
                    *market.get("aliases", []),
                ),
                normalized,
            ):
                continue
            items.append(
                {
                    "market_id": market["market_id"],
                    "market_version_id": market["market_version_id"],
                    "canonical_name": market["canonical_name"],
                    "definition": market["definition"],
                    "activation_status": market.get("activation_status"),
                    "research_gap_ids": market.get("research_gap_ids", []),
                    "parent_market_id": market.get("parent_market_id"),
                }
            )
        items.sort(key=lambda item: (item["canonical_name"].casefold(), item["market_id"]))
        return _page(items, page=page, page_size=page_size)

    def market_detail(self, market_id: str) -> dict[str, Any]:
        market = self.markets.get(market_id)
        if market is None:
            raise KeyError(market_id)
        mappings = [
            mapping
            for mapping in self.graph_mappings
            if market_id in mapping["output_market_ids"]
        ]
        source_records = [
            self.source_records[record_id]
            for record_id in market.get("source_record_ids", [])
            if record_id in self.source_records
        ]
        return {
            **market,
            "mappings": mappings,
            "research_gaps": [
                self.gaps.get(gap_id, {"gap_id": gap_id, "status": "unresolved"})
                for gap_id in market.get("research_gap_ids", [])
            ],
            "source_records": source_records,
            "audit_chain": {
                "boundary_run_id": market.get("source_boundary_run_id"),
                "independent_review_id": market.get("source_review_id"),
                "release_id": self.version.release_id,
                "graph_version_id": self.version.graph_version_id,
            },
        }

    def list_mappings(
        self,
        *,
        identity_id: str | None = None,
        market_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        items = [
            mapping
            for mapping in self.graph_mappings
            if (not identity_id or mapping.get("identity_id") == identity_id)
            and (not market_id or market_id in mapping["output_market_ids"])
        ]
        items.sort(key=lambda item: item["event_id"])
        return _page(items, page=page, page_size=page_size)

    def list_families(
        self,
        *,
        query: str | None = None,
        family_kind: str | None = None,
        status: str | None = None,
        schedulable: bool | None = None,
        batch_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        normalized = _normalize_query(query)
        items: list[dict[str, Any]] = []
        for family in self.families.values():
            batch = self.family_batches.get(family["family_id"])
            if family_kind and family["family_kind"] != family_kind:
                continue
            if status and family["status"] != status:
                continue
            if schedulable is not None and family["schedulable"] is not schedulable:
                continue
            if batch_id and (batch is None or batch["batch_id"] != batch_id):
                continue
            label = self._family_label(family)
            if not _contains_query((family["family_id"], label), normalized):
                continue
            items.append(
                {
                    "family_id": family["family_id"],
                    "label": label,
                    "family_kind": family["family_kind"],
                    "status": family["status"],
                    "schedulable": family["schedulable"],
                    "counts": family["counts"],
                    "neutral_priority": family["neutral_priority"],
                    "batch_id": batch["batch_id"] if batch else None,
                    "batch_ordinal": batch["ordinal"] if batch else None,
                }
            )
        items.sort(
            key=lambda item: (
                tuple(item["neutral_priority"]["ordering_key"]),
                item["family_id"],
            )
        )
        return _page(items, page=page, page_size=page_size)

    def _family_label(self, family: Mapping[str, Any]) -> str:
        required = family.get("required_disposition_identity_ids", [])
        naics = next(
            (identity_id for identity_id in required if identity_id.startswith("identity:naics:")),
            None,
        )
        if naics and naics in self.identities:
            labels = self.identities[naics].get("analysis_labels") or self.identities[naics].get("labels")
            if labels:
                return str(labels[0])
        if family["family_kind"] == "unlinked_collection_coverage_challenge":
            return "Unlinked product coverage challenge"
        if family["family_kind"] == "unretrieved_prior_candidate_challenge":
            return "Unretrieved prior-market challengers"
        return family["family_id"]

    def family_detail(
        self,
        family_id: str,
        *,
        context_page: int = 1,
        context_page_size: int = 25,
    ) -> dict[str, Any]:
        family = self.families.get(family_id)
        if family is None:
            raise KeyError(family_id)
        required = [
            self.identity_summary(identity_id)
            for identity_id in family["required_disposition_identity_ids"]
        ]
        context = [
            self.identity_summary(identity_id)
            for identity_id in family["context_only_identity_ids"]
        ]
        context.sort(key=lambda item: item["identity_id"])
        candidates = [
            self.candidates[candidate_id]
            for candidate_id in family["required_prior_candidate_ids"]
            if candidate_id in self.candidates
        ]
        return {
            **family,
            "label": self._family_label(family),
            "required_identities": required,
            "context_identities": _page(
                context, page=context_page, page_size=context_page_size
            ),
            "required_candidates": candidates,
            "batch": self.family_batches.get(family_id),
            "ownership_notice": (
                "Administrative review ownership only. It is not evidence of market "
                "membership, attractiveness, Target eligibility, or economic primacy."
            ),
        }

    def list_batches(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        items = [batch for batch in self.batches if not status or batch["status"] == status]
        items.sort(key=lambda item: (item["ordinal"], item["batch_id"]))
        return _page(items, page=page, page_size=page_size)

    def identity_summary(self, identity_id: str) -> dict[str, Any]:
        identity = self.identities.get(identity_id)
        assignment = self.assignments.get(identity_id)
        if identity is None or assignment is None:
            raise KeyError(identity_id)
        return {
            "identity_id": identity_id,
            "identity_type": identity["identity_type"],
            "source_code": identity["source_code"],
            "labels": identity["labels"],
            "analysis_labels": identity["analysis_labels"],
            "label_conflict": identity["label_conflict"],
            "assignment": assignment,
        }

    def identity_detail(self, identity_id: str) -> dict[str, Any]:
        summary = self.identity_summary(identity_id)
        identity = self.identities[identity_id]
        return {
            **summary,
            "source_records": [
                self.source_records[record_id]
                for record_id in identity["source_record_ids"]
                if record_id in self.source_records
            ],
            "reconciliation_mapping": self.reconciliation_mappings[identity_id],
            "accepted_graph_mappings": [
                mapping
                for mapping in self.graph_mappings
                if mapping.get("identity_id") == identity_id
            ],
        }

    def list_candidates(
        self,
        *,
        query: str | None = None,
        coverage_status: str | None = None,
        family_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        normalized = _normalize_query(query)
        items = [
            candidate
            for candidate in self.candidates.values()
            if (not coverage_status or candidate["coverage_status"] == coverage_status)
            and (
                not family_id
                or family_id == candidate["primary_family_id"]
                or family_id in candidate["collision_family_ids"]
            )
            and _contains_query(
                (candidate["candidate_market_id"], candidate["name"]), normalized
            )
        ]
        items.sort(key=lambda item: (item["name"].casefold(), item["candidate_market_id"]))
        return _page(items, page=page, page_size=page_size)

    def search(self, query: str, *, limit: int = 30) -> list[dict[str, Any]]:
        normalized = _normalize_query(query)
        if len(normalized) < 2:
            raise SnapshotError("search query must contain at least 2 characters")
        if limit < 1 or limit > 100:
            raise SnapshotError("limit must be between 1 and 100")
        results: list[dict[str, Any]] = []
        for market in self.markets.values():
            if _contains_query((market["market_id"], market["canonical_name"]), normalized):
                results.append(
                    {
                        "kind": "market",
                        "id": market["market_id"],
                        "label": market["canonical_name"],
                        "href": f"/markets/{market['market_id']}",
                    }
                )
        for family in self.families.values():
            label = self._family_label(family)
            if _contains_query((family["family_id"], label), normalized):
                results.append(
                    {
                        "kind": "family",
                        "id": family["family_id"],
                        "label": label,
                        "href": f"/families/{family['family_id']}",
                    }
                )
        for identity in self.identities.values():
            if _contains_query(
                (
                    identity["identity_id"],
                    identity["source_code"],
                    *identity["labels"],
                    *identity["analysis_labels"],
                ),
                normalized,
            ):
                results.append(
                    {
                        "kind": "identity",
                        "id": identity["identity_id"],
                        "label": (identity["analysis_labels"] or identity["labels"])[0],
                        "href": f"/api/v1/identities/{identity['identity_id']}",
                    }
                )
        for candidate in self.candidates.values():
            if _contains_query(
                (candidate["candidate_market_id"], candidate["name"]), normalized
            ):
                results.append(
                    {
                        "kind": "candidate",
                        "id": candidate["candidate_market_id"],
                        "label": candidate["name"],
                        "href": (
                            "/api/v1/candidates?query="
                            + candidate["candidate_market_id"]
                        ),
                    }
                )
        results.sort(key=lambda item: (item["kind"], item["label"].casefold(), item["id"]))
        return results[:limit]

    def receipt(self, kind: str, receipt_id: str) -> dict[str, Any]:
        if kind not in RECEIPT_KINDS:
            raise KeyError(kind)
        _safe_identifier(receipt_id, "receipt ID")
        base, filename = RECEIPT_KINDS[kind]
        path = self.root / base / receipt_id / filename
        value = _object(path)
        redactions: list[str] = []
        sanitized = _sanitize_receipt(value, redactions=redactions)
        return {
            "kind": kind,
            "id": receipt_id,
            "receipt": sanitized,
            "redacted_paths": sorted(redactions),
        }


def _resolve_schedule(root: Path, partition_id: str) -> tuple[Path, dict[str, Any]]:
    _safe_identifier(partition_id, "partition ID")
    schedule_dir = root / "data" / "family_schedules" / partition_id
    receipt = _object(schedule_dir / "schedule-receipt.json")
    if receipt.get("partition_id") != partition_id:
        raise SnapshotError("partition directory and receipt disagree")
    for name, expected in receipt["output_hashes"].items():
        if _sha256_path(schedule_dir / name) != expected:
            raise SnapshotError(f"family-schedule artifact hash mismatch: {name}")
    return schedule_dir, receipt


def _resolve_graph(
    root: Path, graph_version_id: str
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    _safe_identifier(graph_version_id, "graph version ID")
    matches: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for receipt_path in sorted(
        (root / "data" / "market_graph" / "versions").glob("*/graph-receipt.json")
    ):
        receipt = _object(receipt_path)
        if receipt.get("graph_version_id") != graph_version_id:
            continue
        projection = _object(receipt_path.parent / "projection.json")
        if canonical_sha256(projection) != receipt.get("projection_sha256"):
            raise SnapshotError("graph release projection hash mismatch")
        matches.append((receipt_path.parent, receipt, projection))
    if len(matches) != 1:
        raise SnapshotError(
            f"graph version must resolve exactly once; found {len(matches)} matches"
        )
    return matches[0]


def load_snapshot(
    *,
    root: Path = ROOT,
    source_run_id: str | None = None,
    partition_id: str | None = None,
    graph_version_id: str | None = None,
) -> ReadSnapshot:
    latest = compile_system_context(root=root)
    source_run_id = source_run_id or latest["source_universe"]["run_id"]
    partition_id = partition_id or latest["family_schedule"]["partition_id"]
    graph_version_id = graph_version_id or latest["canonical_market_graph"][
        "graph_version_id"
    ]
    _safe_identifier(source_run_id, "source run ID")
    source_dir = root / "data" / "runs" / source_run_id
    source_receipt = _object(source_dir / "run-receipt.json")
    if source_receipt.get("run_id") != source_run_id:
        raise SnapshotError("source-run directory and receipt disagree")
    reconciliation = _verified_artifact(
        source_dir,
        "multisource-reconciliation.json.gz",
        source_receipt["output_hashes"]["multisource-reconciliation.json.gz"],
        gzip_json=True,
    )
    schedule_dir, schedule_receipt = _resolve_schedule(root, partition_id)
    graph_dir, graph_receipt, projection = _resolve_graph(root, graph_version_id)
    if {
        source_run_id,
        schedule_receipt["source_run_id"],
        graph_receipt["source_universe_run_id"],
    } != {source_run_id}:
        raise SnapshotError("source, schedule, and graph versions are incompatible")
    coverage = _gzip_object(schedule_dir / "coverage-ledger.json.gz")
    candidates = _gzip_object(schedule_dir / "candidate-collision-ledger.json.gz")
    families = _gzip_object(schedule_dir / "family-manifest.json.gz")
    batches = _object(schedule_dir / "batch-manifest.json")
    for artifact in (coverage, candidates, families, batches):
        if artifact.get("partition_id") != partition_id:
            raise SnapshotError("family-schedule artifact partition mismatch")
        if artifact.get("source_run_id") != source_run_id:
            raise SnapshotError("family-schedule artifact source-run mismatch")
    context = {
        **latest,
        "source_universe": {
            **latest["source_universe"],
            "run_id": source_run_id,
        },
        "family_schedule": {
            "status": schedule_receipt["status"],
            "partition_id": partition_id,
            "source_run_id": source_run_id,
            "as_of_utc": schedule_receipt["as_of_utc"],
            "counts": schedule_receipt["counts"],
            "model_invoked": schedule_receipt["model_invoked"],
        },
        "canonical_market_graph": {
            "status": "canonical_universe_construction_in_progress",
            "release_id": graph_receipt["release_id"],
            "graph_version_id": graph_version_id,
            "source_universe_run_id": source_run_id,
            "as_of_utc": graph_receipt["as_of_utc"],
            **graph_receipt["counts"],
            "open_research_gaps": len(
                {
                    gap_id
                    for market in projection["markets"]
                    for gap_id in market.get("research_gap_ids", [])
                }
            ),
        },
        "canonical_markets": len(projection["markets"]),
    }
    return ReadSnapshot(
        root=root,
        context=context,
        source_receipt=source_receipt,
        schedule_receipt=schedule_receipt,
        graph_receipt=graph_receipt,
        reconciliation=reconciliation,
        coverage=coverage,
        candidates=candidates,
        families=families,
        batches=batches,
        projection=projection,
    )


class SnapshotStore:
    """Thread-safe atomic cache that reloads only after pointers change and verify."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._latest: ReadSnapshot | None = None
        self._pointer_token: str | None = None
        self._versions: dict[tuple[str, str, str], ReadSnapshot] = {}

    def _current_pointer_token(self) -> str:
        digest = hashlib.sha256()
        for name in ("latest-run.json", "latest-family-schedule.json", "latest-graph.json"):
            path = self.root / "data" / "generated" / name
            digest.update(name.encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError as error:
                raise SnapshotError(f"cannot read current pointer {name}: {error}") from error
        return digest.hexdigest()

    def latest(self) -> ReadSnapshot:
        token = self._current_pointer_token()
        with self._lock:
            if self._latest is not None and token == self._pointer_token:
                return self._latest
            candidate = load_snapshot(root=self.root)
            self._latest = candidate
            self._pointer_token = token
            key = (
                candidate.version.source_run_id,
                candidate.version.partition_id,
                candidate.version.graph_version_id,
            )
            self._versions[key] = candidate
            return candidate

    def get(
        self,
        *,
        source_run_id: str | None = None,
        partition_id: str | None = None,
        graph_version_id: str | None = None,
    ) -> ReadSnapshot:
        if source_run_id is None and partition_id is None and graph_version_id is None:
            return self.latest()
        latest = self.latest()
        key = (
            source_run_id or latest.version.source_run_id,
            partition_id or latest.version.partition_id,
            graph_version_id or latest.version.graph_version_id,
        )
        with self._lock:
            cached = self._versions.get(key)
        if cached is not None:
            return cached
        candidate = load_snapshot(
            root=self.root,
            source_run_id=key[0],
            partition_id=key[1],
            graph_version_id=key[2],
        )
        with self._lock:
            self._versions[key] = candidate
        return candidate

    def versions(self) -> dict[str, Any]:
        latest = self.latest()
        source_runs: list[dict[str, Any]] = []
        for path in sorted((self.root / "data" / "runs").glob("*/run-receipt.json")):
            receipt = _object(path)
            source_runs.append(
                {
                    "run_id": receipt.get("run_id"),
                    "current": receipt.get("run_id") == latest.version.source_run_id,
                }
            )
        partitions: list[dict[str, Any]] = []
        for path in sorted(
            (self.root / "data" / "family_schedules").glob("*/schedule-receipt.json")
        ):
            receipt = _object(path)
            partitions.append(
                {
                    "partition_id": receipt.get("partition_id"),
                    "source_run_id": receipt.get("source_run_id"),
                    "as_of_utc": receipt.get("as_of_utc"),
                    "current": receipt.get("partition_id") == latest.version.partition_id,
                }
            )
        graphs: list[dict[str, Any]] = []
        for path in sorted(
            (self.root / "data" / "market_graph" / "versions").glob(
                "*/graph-receipt.json"
            )
        ):
            receipt = _object(path)
            graphs.append(
                {
                    "release_id": receipt.get("release_id"),
                    "graph_version_id": receipt.get("graph_version_id"),
                    "source_run_id": receipt.get("source_universe_run_id"),
                    "as_of_utc": receipt.get("as_of_utc"),
                    "current": receipt.get("graph_version_id")
                    == latest.version.graph_version_id,
                }
            )
        return {
            "source_runs": source_runs,
            "partitions": partitions,
            "graph_releases": graphs,
            "current": latest.provenance(),
        }
