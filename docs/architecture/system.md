# System architecture

Turbo is an event-oriented research system with seven logical layers.

1. **Source registry** preserves immutable public-source captures and exact locators.
2. **Universe builder** ingests taxonomies and datasets into a versioned Market Graph.
3. **Target-universe filter** applies strategy eligibility gates without scoring
   market attractiveness or erasing canonical markets.
4. **Research memory** stores observations, claims, questions, decisions, lessons,
   and directed supersession/contradiction edges.
5. **Scoring engine** runs specialist evaluations, adjudication, submodel-owned
   pairwise calibration, global weighted aggregation, and confidence adjustment.
6. **Scheduler** selects high-value evidence gaps, stale scores, challengers, and
   comparison matches without mixing their queues.
7. **API and web app** expose as-of graphs, scores, evidence, changes, and audit receipts.

The projections are ordered but independent: canonical universe → target universe →
evaluation. Attractiveness cannot decide whether a market exists; filtering cannot
erase a canonical market; scoring cannot mutate a market boundary. A discovered
boundary defect must return through a separate append-only universe proposal.

The source-universe run, operating-family schedule, canonical graph release, Target
projection, and evaluation projection also have separate receipts and pointers.
`turbo context` verifies and composes them; it does not treat a source-run-local count
or the most recently written activation directory as current system truth.

The first read product keeps the same boundary. A Python read model composes one
hash-verified source/schedule/graph tuple in memory and exposes deterministic FastAPI
resources. The React/TypeScript/Vite client consumes only that API; it cannot scan
artifact directories or recreate research decisions. FastAPI also serves the compiled
SPA locally, so there is no second backend, write surface, or application database.
Snapshot provenance binds exact receipt and artifact hashes plus a versioned
read-model contract. HTTP ETags bind the complete selected response representation.
Atomic reload occurs only after changed pointers and all referenced receipts and
artifacts validate. One shared FastAPI dependency applies an explicit source-run,
partition, and graph tuple to every snapshot-backed route. The UI selector consumes
the backend's verified compatible-tuple catalog and propagates the three IDs through
queries and navigation without recreating version compatibility in the client.

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

The API supports both verified current pointers and explicit immutable
source-run/partition/graph tuples. Incompatible joins fail closed.

An activation is deliberately local to one reviewed family. Publication therefore
uses a cumulative graph-release config that enumerates exact activation directories,
configs, and hashes. The release compiler replays all of them, requires one source-
universe lineage, unions accepted events, rejects duplicate event IDs, and projects
one graph through an explicit UTC cutoff. A mutable pointer contains only the release
identity, path, and verification hashes; it never replaces immutable graph truth.

## Operating-family scheduling

Scheduling is a deterministic universe-construction subsystem, not a research model.
Each six-digit NAICS identity anchors a family. Shared collection products retain all
official family appearances but receive one stable administrative owner by rendezvous
hashing. Aggregate NAICS and trilateral NAPCS nodes are context-only. Unlinked
collection products and prior candidates with no retrieval collision enter explicit
coverage-challenge families. The completed 561110 pilot is a pinned regression
override.

The planner publishes separate ledgers for identity coverage, source relationship
context, and prior-candidate collisions, plus a family manifest and batch manifest.
Every candidate owner must be reviewable; context-only families may provide collision
evidence but cannot own work. Batch order uses only source-reconciliation burden and
coverage risk. Administrative ownership must never be consumed as an accepted market
mapping, semantic primacy, strategy fit, or score.

## Agent-native execution

Every autonomous loop consumes explicit work items and emits schema-valid events.
Agents discover no hidden authority from prose or chat. Scheduler leases, idempotency
keys, retry counts, evidence cutoffs, model/prompt versions, validation results, and
human gates are durable fields. A failed agent leaves the last accepted score active
and creates an inspectable exception or retry item.

The first operating-boundary harness implements that contract without binding the
architecture to one model vendor. A deterministic compiler selects a bounded family
from a hash-verified universe run and produces a canonical pack hash. Two specialists
run concurrently in separate ephemeral, empty, read-only sessions and cannot see one
another's work. Their outputs must satisfy one strict schema plus closed-world checks
for complete identity and candidate disposition, known evidence, known proposals,
valid provisional-gap links, and distinct invocation identities. Only then may the
adjudicator run. Its receipt binds the exact hashes of both specialist outputs.

The provider-neutral runner dispatches each role from versioned configuration. The
primary metered path uses OpenRouter with one explicit model slug, strict structured
output routing, and local validation; the isolated Codex CLI remains a fallback path.
Cross-model auto-routing is not used. Same-model provider fallback is allowed and the
reported provider is retained when available.

The runner retains final structured JSON and small receipts containing requested and
served model, served provider when reported, reasoning effort, prompt/schema/pack and
request/response hashes, UTC bounds, latency, attempts, generation ID, token/cost
usage when reported, validation status, and output hash. Raw private reasoning and
credentials are deliberately not durable research records. Model assignments remain
versioned configuration and are selected later through role-specific frozen-case
evaluations.

The same records render into a concise public explanation and a detailed audit view.
This keeps the system understandable to the chairman and an interviewer without
forking the truth into a presentation database and a hidden research database.

## Comparison topology

Pairwise comparison is a domain operation. Every submodel has its own comparator and
comparison queue. Comparison events can adjust only that submodel's market scores and
must preserve the pair, selection reason, evidence cutoff, factor contributions,
confidence, and score delta. The global projection is a deterministic weighted view
plus sensitivity and stability diagnostics; it does not add generalist judgment.

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

