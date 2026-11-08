# Data contracts

Turbo separates durable objects so one convenient JSON blob never becomes an
unreviewable source of truth.

## Source snapshot

Immutable bytes plus dataset ID, publisher, canonical URL, retrieval UTC, SHA-256,
reuse status, and declared role. Validation fails when bytes differ from the manifest.

## Observation and claim

An observation is a narrow, directly located source statement. A claim is an
interpretation labeled `fact`, `inference`, `assumption`, or `unknown`, with supporting
and contradicting observations and directed version edges.

## Market and market version

`market_id` is stable identity. A market version contains boundary, buyer, job,
delivery model, workforce, economics, acquisition universe, Ambient AI workflow,
aliases, source mappings, and split/merge lineage.

## Factor definition, evaluator result, and score event

A factor definition contains anchors, evidence expectations, weight, confidence
policy, model policy, disagreement tolerance, and version. An evaluator result
preserves its frozen evidence pack, model/prompt/config versions, raw answer,
rationale, evidence, counterevidence, alternatives, and hash. A score event resolves
results into a factor score with confidence, evidence quality, downside, risk
adjustment, and adjudication.

## Evidence gap

An active work item with question, scope, retry state, ranking sensitivity,
uncertainty, probability of finding evidence, cost estimate, priority, attempts, and
terminal condition. Gaps never null out accepted scores.

## Run receipt

Contains immutable run ID, input/configuration hashes, code fingerprint, output
hashes, and validation results. Exact Git head and wall-clock local verification are
posted as GitHub issue/PR receipts so deterministic replay never dirties the worktree.

Formal JSON Schemas will precede external API stability. V1 dataclasses are an
executable prototype of these contracts.

