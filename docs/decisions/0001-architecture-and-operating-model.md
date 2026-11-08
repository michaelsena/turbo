# ADR 0001: Architecture and operating model

- Status: accepted for bootstrap
- Date: 2026-11-08

## Decision

Turbo will use a versioned Market Graph, immutable source snapshots, append-only
research memory, complete confidence-weighted scoring, independent specialist
evaluation with mandatory adjudication, and GitHub-native issue/branch/PR governance.
All validation and testing will run locally rather than in hosted CI.

## Why

A ranked list is useful only if the universe is credible, scores are comparable,
uncertainty is visible, and future researchers can reconstruct how the result changed.
The no-blank rule lets the engine produce immediate results while the append-only
gap loop prevents provisional inference from masquerading as settled fact.

## Consequences

- More data-model and provenance work is required up front.
- The first scores will be complete but intentionally low confidence.
- The app must expose lineage and uncertainty, not only rank.
- Local audit receipts become required because hosted CI is intentionally absent.

