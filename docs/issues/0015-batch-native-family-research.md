# Issue 15: Batch-native family research

## Outcome

Issue #15 turns the corrected Issue #14 schedule into replayable family research
inputs, then later adds authorized batch execution, selective verification,
adjudication, independent release review, and deterministic closure.

## Track A: deterministic preparation

Track A contains no model calls. It:

1. verifies the latest schedule pointer, canonical schedule receipt hash, and every
   schedule artifact byte hash;
2. verifies the cumulative graph pointer, receipt, and projection;
3. resolves one requested family to exactly one schedulable manifest entry;
4. generates a V2 config with exact required identities, context shards, required
   candidates, hashes, counts, prohibitions, and limits;
5. compiles a frozen V2 evidence pack from the immutable source run, coverage ledger,
   collision ledger, context-edge ledger, and current graph;
6. validates count, item, canonical-byte, lineage, role-separation, and content hashes;
7. optionally persists a content-addressed preparation and replays it exactly.

Independent review of the first Track A increment identified four fail-open risks.
The corrected implementation now also requires graph pointer/receipt/projection
agreement and recomputed graph counts; requires consumed source artifacts to match the
schedule's immutable source hashes in addition to the source-run receipt; regenerates
and compares every pack section during standalone validation; and rejects semantically
identical persisted JSON whose file bytes are not canonical. Regression tests mutate
graph lineage, graph counts, candidate evidence, raw evidence, context sets, card
collections, edge membership, pack counts, graph context, and file formatting.

The pack includes full source/mapping evidence only for required identities. Context
identities retain labels and exact relationship edges for orientation. This is an
intentional contract boundary: context is not a second primary disposition queue.

The corrected schedule partition is
`family-partition:60517981ab96e7f243c7033e`, sourced from
`run-2ea0f00db84148de663f`.

## Commands

```text
turbo family-dry-run <family-id>
turbo family-prepare <family-id> [--output-root <directory>]
turbo family-validate-preparation <preparation-directory>
```

`family-dry-run` is the safe default. None of these commands invokes a model.

## Fail-closed gates

- pointer, receipt, artifact, source-run, or graph hash mismatch;
- family absent, completed, or administrative-only;
- required, context, candidate, or context-edge set/count drift;
- required/context overlap or duplicate IDs;
- evidence-item or canonical pack-byte limit exceeded;
- persisted config, pack, receipt, or content address fails replay.
- graph pointer, receipt, projection, source run, version, hash, or counts disagree;
- source-run hashes disagree with the schedule's frozen source hashes;
- any regenerated pack section differs, even when a tampered self-hash is recomputed;
- any persisted config, pack, or receipt is not canonical JSON bytes.

There is no silent truncation, inferred substitution, activation, or graph mutation.

## Remaining tracks

- Track B: explicit authorization, leases, cost accounting, resumable execution, and
  bounded concurrency.
- Track C: progress events, closure receipts, cross-family conflict checks, and
  cumulative graph-release integration.
- Metered canary: only after exact local replay, independent review, and separate
  chairman spend authorization.
