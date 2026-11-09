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
Partial explicit URL selections remain explicit until backend validation. The selected
source receipt supplies historical source context; it is never relabeled latest data.
Snapshot loading rehashes all declared source artifacts, checks schedule-pinned source
hashes, and requires graph publication/version/count coherence. Failures produce a
sanitized response; the Audit view displays the selected response provenance.

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

The executed Issue 12 operating-boundary pilot implements that contract without binding the
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

The scaled universe process is separately governed by Issue 15: primary batch pass,
selective verification, conditional blind escalation/disagreement adjudication, and
mandatory independent graph-release review before deterministic closure. The pilot
is not its default call topology. Later ranking evaluators/comparators are another
scope; see [ADR 0012](../decisions/0012-research-workflow-scope.md).

## Batch execution foundation

Track B1 adds a separate authorization and durable execution ledger above prepared
family packs. It binds exact batch scope and execution limits, reserves worst-case
cost before a dispatch transition, serializes concurrent updates with a process-safe
lock, and makes attempt resumption idempotent. Costs use integer microdollars;
ambiguous dispatch retains its reservation without automatic refund or retry.

This foundation is exercised through fake transport only. It neither replaces the
existing pilot runner nor exposes a new live model command. Real adapters, validated
batch outputs, selective verification, adjudication, cost reconciliation, and reviewed
family closure remain separate work. An execution event is not a market-graph event.
Authorization and status declare `budget_scope: single_journal_simulation`. Budget
and idempotency controls apply to one trusted journal; a copied authorization in
another directory has separate counters. Shared spent-authorization tracking or a
deterministic governed namespace must precede any live adapter or paid canary.
See [ADR 0008](../decisions/0008-batch-authorization-execution-ledger.md).

Track B2 adds a managed path through one explicitly trusted local registry. The
registry binds each canonical authorization digest to a canonical journal, so repeat
managed clients cannot select fresh counters for that authorization. A missing
claimed journal fails closed. Standalone B1 remains per-journal. Different registries,
new unsigned authorizations, and deletion of all trusted state are outside this local
guarantee. B2 remains simulation-only; see
[ADR 0009](../decisions/0009-trusted-local-execution-registry.md).

Track B3 adds a standalone output-validation context over verified preparations.
Request/invocation identity, schema and prompt hashes, evidence references, and
coverage obligations bind each synthetic output to its intended batch. Validation
checks structure and references; it does not establish factual truth or calibrated
confidence. B3 itself does not connect to B1 settlement or a provider adapter, and
it creates no accepted market event. See
[ADR 0010](../decisions/0010-batch-output-contract.md).

Track B4 bridges these contracts through immutable response and validation artifacts.
Confidence-bearing content stays outside B1's integer-only response envelope; the
managed journal settles compact artifact references. An effective execution-contract
digest pins the prompt, output schema, and byte caps in the authorization before
claim and dispatch; the B3 context retains its raw prompt hash. Known valid bounded usage is
charged even when structural output validation fails. Ambiguous transport, usage,
or persistence retains its reservation without automatic retry. This integration
uses fake transport only, creates no accepted research, and leaves B1/B2 schemas
unchanged. See [ADR 0011](../decisions/0011-batch-output-artifacts.md).

Issue 39's first provider integration is a separate V2 shared-role execution journal
plus one-attempt OpenRouter adapter and `batch_provider` bridge. Only primary and
verifier can dispatch; escalation, adjudication, and release dispatch remain blocked.
The existing offline workflow/closure APIs and legacy single-family runner retain
their separate scope. Controlled-transport testing does not establish paid-run or
production readiness, and no new market activation is claimed.

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

