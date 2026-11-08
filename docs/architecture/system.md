# System architecture

Turbo is an event-oriented research system with six logical layers.

1. **Source registry** preserves immutable public-source captures and exact locators.
2. **Universe builder** ingests taxonomies and datasets into a versioned Market Graph.
3. **Research memory** stores observations, claims, questions, decisions, lessons,
   and directed supersession/contradiction edges.
4. **Scoring engine** runs specialist evaluations, adjudication, aggregation,
   confidence adjustment, and pairwise calibration.
5. **Scheduler** selects high-value evidence gaps, stale scores, challengers, and
   comparison matches without mixing their queues.
6. **API and web app** expose as-of graphs, scores, evidence, changes, and audit receipts.

## Core durable identities

- `source_snapshot_id`: immutable bytes plus publisher/URL/time/hash.
- `source_record_id`: a row or object inside one snapshot.
- `market_id`: stable identity for a canonical operating market.
- `market_version_id`: one definition of that market at one graph version.
- `factor_version_id`: exact factor definition, anchors, weights, and policy.
- `evaluation_id`: one market-factor result from one evaluator and model version.
- `score_event_id`: resolved factor or aggregate score at a point in history.
- `run_id`: exact inputs, code commit, configuration, outputs, and receipts.

## Graph versioning

Each accepted source, mapping, split, merge, exclusion, claim, and score resolution is
an append-only event. A graph version is the deterministic projection of all accepted
events through a cutoff. Stable market IDs survive ordinary score changes. Splits and
merges create successor market IDs with explicit edges; prior versions remain queryable.

The API will support both `latest` and explicit `as_of`/`graph_version` requests.

## Agent-native execution

Every autonomous loop consumes explicit work items and emits schema-valid events.
Agents discover no hidden authority from prose or chat. Scheduler leases, idempotency
keys, retry counts, evidence cutoffs, model/prompt versions, validation results, and
human gates are durable fields. A failed agent leaves the last accepted score active
and creates an inspectable exception or retry item.

The same records render into a concise public explanation and a detailed audit view.
This keeps the system understandable to the chairman and an interviewer without
forking the truth into a presentation database and a hidden research database.

## Determinism and model work

Research models may be nondeterministic; accepted artifacts may not be. Prompts,
inputs, output schema, model identity, raw response hash, parsed result, adjudication,
and acceptance decision are recorded. Replaying a historical run verifies its durable
projection even if a new research call would answer differently.

## Boundaries

- No paid sources or outreach.
- No confidential, personal, health, or protected-status data.
- No company work is part of the market-universe bootstrap.
- All validation and tests run locally; no GitHub Actions or paid hosted CI.

