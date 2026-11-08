# ADR 0003: Typed market identity graph and durable derived artifacts

- Status: accepted
- Date: 2026-11-08

## Decision

Turbo will keep four distinct layers in the universe pipeline:

1. immutable source rows and observations;
2. normalized identities for the objects named by those sources;
3. candidate-market hypotheses proposed for review; and
4. accepted, versioned canonical markets.

All relationships must resolve between normalized identities. Pair-level edges retain
every contributing source observation with its governed snapshot and unique row-level
locator. A canonical market can change only through an
accepted graph event. Event supersession and market-version supersession are separate:
the former changes which instructions are active, while the latter preserves the
history of the market state those instructions produced.

Large derived run artifacts will use deterministic gzip-compressed JSON. Compression
metadata and platform bytes are normalized so identical inputs and code produce the
same artifact hash across replay environments. The uncompressed JSON data model and
validation rules remain canonical; compression is only a durable storage envelope.

## Why

Source classifications, normalized economic concepts, candidate boundaries, and
accepted markets are related but not interchangeable. Conflating them allowed missing
relationship endpoints, ambiguous lineage, and premature market decisions to appear
valid. Separating event history from market-version history also makes corrections and
withdrawals replayable without rewriting the past.

The complete referentially closed identity graph is substantially larger than the
bootstrap summaries. Deterministic compression keeps versioned run receipts practical
without sacrificing exact replay or content-addressed auditing.

## Consequences

- Source records may point to normalized identities but never become markets by
  implication.
- Repeated source observations do not multiply the decision queue: reconciliation
  emits one review mapping per normalized identity with all supporting records.
- Candidate hypotheses remain review inputs until an accepted graph event creates or
  changes a canonical market.
- Unknown snapshot, source-record, identity, or relationship references fail local
  validation.
- Retired-market mappings remain visible as history but cannot affect the current
  projection.
- Schema validation, referential checks, replay tests, and exact artifact hashes are
  required for every published run.
- Consumers must transparently decompress `.json.gz` run artifacts before reading the
  same JSON contracts.
