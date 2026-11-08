# Data contracts

Turbo separates durable objects so one convenient JSON blob never becomes an
unreviewable source of truth.

## Source snapshot

Immutable bytes plus dataset ID, publisher, canonical URL, retrieval UTC, SHA-256,
reuse status, and declared role. Validation fails when bytes differ from the manifest.

## Source record

A stable row or object within one immutable snapshot:

- source-record ID, snapshot ID, source system, and unique row/object locator
- raw code, raw label, raw definition, hierarchy path, and source parent IDs
- row role such as industry, product, service, task, aggregate, residual, survey
  control, or unknown
- immutable source relationships and semantic flags

Retrieval normalization is never authoritative. Raw exclusions, negations, regulated
distinctions, customer scope, geography, and residual wording remain preserved.

## Normalized source identity

A typed NAICS or NAPCS code identity is distinct from every immutable row or
observation that mentions it. Identity nodes use their own namespace and link to one
or more source-record IDs. Official hierarchy, concordance, and industry-product
relationships connect identity nodes. Pair-level relationship edges retain every
contributing source observation separately, including snapshot ID, row number,
dimensions, and a unique locator. Source-row IDs, normalized identities,
candidate-market hypotheses, and canonical-market IDs are never interchangeable.

## Observation and claim

An observation is a narrow, directly located source statement. A claim is an
interpretation labeled `fact`, `inference`, `assumption`, or `unknown`, with supporting
and contradicting observations and directed version edges.

## Market and market version

The market ID is an opaque stable identity and is never derived from a label, NAICS
code, or list position. A market version contains:

- canonical name, definition, boundary, parent, aliases, and explicit exclusions
- buyer, buyer role, budget owner, purchase trigger, and job-to-be-done
- deliverable, delivery model, work location, workforce, and revenue model
- capital, inventory, regulation, economics, and risk
- acquisition universe and operating playbook
- Ambient AI workflow and bounded context sources
- source mappings, split/merge lineage, evidence labels, and confidence by dimension

Dimension-level confidence is required because buyer identity may be well supported
while acquisition-universe equivalence remains uncertain.

## Mapping relationship

Normalized source identities and their supporting source records relate to markets
through typed, many-to-many edges:

- equivalent-label candidate
- broader-than-market / narrower-than-market
- industry-containing-market
- product-sold-by-market
- task-performed-by-market
- partial overlap
- residual bucket
- duplicate source record
- non-market product
- out of scope for canonicalization
- unresolved

NAICS usually supplies industry-containing-market edges. NAPCS usually supplies
product-sold-by-market edges. Neither source becomes a market one-for-one.

## Reconciliation event and graph version

Accepted decisions are append-only create, map, split, merge, rename, reparent,
exclude-source-record, reject-candidate, or supersede-decision events. Each event
preserves inputs, outputs, typed relationship, seven operating-identity results,
supporting and contrary records, alternatives, proposer, independent review,
adjudication, cutoff, and supersession.

Candidate-market hypotheses have a dedicated typed input field. Event supersession
withdraws or replaces a decision; rename and reparent events instead supersede the
current `market_version_id` without deactivating the event that originally created
the stable market identity.

A graph version is the deterministic projection of accepted events through a cutoff.
Its identity includes the ordered-event hash plus governed source, configuration, and
code hashes. Corrections add a superseding event; they never rewrite the prior event.
Split and merge events retire their predecessor market IDs from the effective graph
while preserving them and their successor lineage in history. Mappings to retired
markets move to an explicitly historical collection rather than dangling in the
effective graph.

Every accepted market version installed by an active event remains subject to
referential validation even if a later split or merge retires it. Retirement changes
effective state; it does not erase historical validation obligations.


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

Formal JSON Schemas and executable projection tests precede external API stability.

