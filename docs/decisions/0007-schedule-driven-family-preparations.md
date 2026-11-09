# ADR 0007: Schedule-driven family preparations

## Status

Accepted for Issue #15 Track A.

## Decision

Every V2 family config is generated from exactly one hash-verified entry in the
corrected Issue #14 schedule. A config binds the schedule receipt and every schedule
artifact hash, the cumulative graph receipt and projection hashes, the exact required
identity set, the schedule-authored context shards, the exact required prior-candidate
set, expected counts, and fail-closed size limits.

The evidence pack compiler consumes the schedule's context-edge ledger. It does not
reconstruct relationship scope heuristically. Required identities receive complete
source and reconciliation cards. Context-only identities receive compact identity
cards and exact relationship-edge evidence, but do not become primary disposition
obligations. Existing graph mappings are included only as context.

Preparation is deterministic and model-free. `family-dry-run` compiles and validates
without persistence. `family-prepare` writes a content-addressed config, pack, and
receipt. `family-validate-preparation` regenerates all content from immutable inputs
and requires canonical file bytes, byte-equivalent JSON objects, and matching hashes.

The cumulative graph is accepted only when its pointer, immutable receipt, and
projection agree on release, graph version, source run, projection hash, and
recomputed counts. Any source artifact read by the pack must match both the source-run
receipt and the schedule receipt's frozen `source_hashes`; updating a mutable run
receipt cannot legitimize changed candidate or raw evidence. Standalone pack validation
regenerates the complete expected pack and compares every metadata, scope, count,
identity, source-record, mapping, candidate, relationship-edge, and graph-context
section.

No input may be silently truncated. Count, evidence-item, or canonical-byte limits
produce a typed failure before any model call. Later execution may split work only by
a separately versioned deterministic policy; it may not weaken this preparation.

## Consequences

- Schedule, universe, graph, and future model outputs remain distinct contracts.
- Context cannot accidentally become duplicate primary work.
- A changed schedule or graph invalidates stale configs instead of being absorbed.
- Dense families remain visible and fail closed if their evidence envelope exceeds a
  preregistered limit.
- This ADR authorizes no model call, spend, activation, Target filtering, evaluation,
  ranking, or company work.
