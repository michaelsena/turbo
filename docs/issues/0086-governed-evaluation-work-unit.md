# Issue 86: Governed submodel evaluation work unit

Status: historical 86a contract and packaging/request-planning record. The reviewed
governed eligibility and evaluation runtime has since been merged; see
[the current evaluation runtime](../operations/governed-evaluation-runtime.md) and
[the executive capability summary](../../README.md). Production execution still
requires accepted eligibility, registered factor policies, and bound authority.
The admission blocker and unimplemented capabilities below describe 86a only.
Issue: https://github.com/michaelsena/turbo/issues/86

This implements ADR 0004 and ADR 0012's evaluation layer, not a parallel pilot
universe. One work unit covers one registered submodel and a bounded cohort of
canonical market versions. It cannot claim a global ranking or reuse an authority
for another submodel. The isolated service-pilot implementation and its proposed
policy exceptions are not dependencies.

## Historical 86a admission and provenance

The immutable plan binds a validated canonical graph release receipt and exact
selected `market_version_id` values, graph source commit/tree, strategy version
and bytes, independently versioned eligibility projection/receipt, selected
factor definitions (anchors, weights, tolerance and adjustment policy), frozen
source snapshots with URL/retrieval time/hash, evidence claims/counterevidence and
gaps, evidence cutoff, prompts, schemas, adapter/transport/ledger code hashes,
registry path and the exact task-to-slot mapping. The plan excludes its own hash,
authority hash and derived attempt IDs. External authority binds the plan hash; an
immutable registry owner then binds plan hash, authority hash and stable attempt
IDs derived from authority hash plus semantic task. This avoids circular hashes.
Evidence and factors use canonical versions, never `pilot-market` identifiers.

Canonical presence alone is not eligibility. Admission must replay the original
strategy hard gates through a supported governed eligibility validator, checking
its compiler/input/event/provider provenance and exact graph/strategy bindings.
A caller-provided `passed` JSON, hash alone, or mutable approval flag is not proof.
Unknown or failed gates hold the market. No unionized-workforce deferral applies.
**At the 86a increment, the repository had no such eligibility publisher/validator. Therefore
86a production preflight returned `BLOCKED_ELIGIBILITY_IMPLEMENTATION`; no authority
claim, registry initialization, credential access or transport is permitted.**
Connecting a later eligibility implementation requires an explicit code change
and review. No CLI flag, environment variable or input field bypasses this gate.
Synthetic tests may exercise internal mechanics with explicitly synthetic inputs;
that test seam is not exposed by public execution APIs or the CLI.

## Tasks and accounting

| Semantic task | V2 accounting slot | Dependencies |
| --- | --- | --- |
| evaluator_a | primary | frozen admitted input only |
| evaluator_b | verifier | identical frozen input; never evaluator A output |
| adjudicator | adjudicator | A/B artifacts and deterministically selected material disagreements |
| comparator | release_reviewer | resolved scores of this submodel and frozen pair-selection policy |

V2 still requires six role configurations. `escalation_a` and `escalation_b`
receive inert configurations but are disabled by the adapter allowlist; neither
can appear as an executable semantic task. The four
labels above are accounting slots only; universe workflow semantics do not apply.
The existing V2 ledger and single-call OpenRouter transport remain unchanged.
One external authority binds exactly this plan and four task configurations,
maximum four physical calls, one attempt per task, and one total microUSD cap.
Unused adjudication capacity is not reassigned. Another submodel needs separate
explicit authority; this adapter never creates it or schedules six work units.

Each slot binds its fixed prompt template/schema and model/routing/output bounds.
The actual request additionally binds the frozen assignment and exact upstream
artifact hashes. Its conservative input bound is checked before reservation.
A/B use distinct invocation identities and isolated requests; both receive the
same pack with no access to each other's answers. Adjudicator and comparator are
separate tasks with explicit dependency views, not hidden extra evaluator calls.

## Durable execution and accepted output

Default plan/status is read-only. Explicit execution admits one eligible task,
revalidates all provenance under one work-unit lock and calls
`BatchExecutionV2.run` with its stable attempt ID. A registry owner binds the exact
work unit and authority. The callback uses `bounded_request_body` and
`invoke_openrouter_once`; no retries, fallbacks, or alternate authority are created.

Raw provider responses, canonical documents, usage/cost/model metadata, request
hashes and upstream hashes are immutable artifacts referenced by settled ledger
entries. Acceptance revalidates these artifacts against the journal; a manually
supplied evaluator JSON is never accepted. Settled replay restores the same view
without HTTP. Reserved/dispatched/unresolved/failed records stop visibly. Changed
inputs, authority, code or artifacts stop before dispatch and publication.

## Resolution and publication boundary

Every admitted market/factor receives a numeric score with fact/inference/
assumption labels, supporting claims, counterevidence, confidence, evidence quality,
downside and open gaps. The versioned factor policy specifies tolerance and exact
math; close answers use the registered mean rule, material disagreements require
an explicit provisional adjudication. Original evaluator answers remain intact.

The comparator owns only this submodel, receives deterministic close and selected
far pairs, and returns versioned comparison evidence and explicit score effects
within the registered bounds. There is no generalist override. A cohort without
valid comparison pairs records that condition rather than inventing a comparison.
A deterministic projection preserves raw/confidence/downside-adjusted scores,
originals, adjudication, comparisons, gaps and all input/output hashes. Completion
means a replay-validated submodel artifact, not canonical graph mutation, global
ranking, or GitHub publication. Global aggregation remains blocked until all
registered submodels and weights are present.

## Implementation boundary and tests

Owned files: `src/turbo/agents/evaluation_workflow.py`, focused tests, a read-only
preflight/status CLI if useful, and this contract. No ledger, provider, universe
compiler, strategy or README edits. First implementation may ship the production
admission blocker and testable mechanics before any live path becomes available;
it must report that limit honestly, never advertise end-to-end live readiness.

Focused checks cover missing/forged eligibility, stale graph/strategy/input hashes,
blind assignment equality, disabled-slot refusal, stable attempt restart without
transport, changed provider artifacts, unknown accounting stop, conditional
adjudication, comparator scope and no implicit global aggregation. Synthetic test
fixtures cannot become production eligibility via a flag. Independent review is
required before source implementation and again before integration. Root owns
full-suite execution and publication decisions.

## Historical increment (86a)

The module checks frozen plan/file/code bindings, exact four-task mapping, canonical
identifier syntax (not canonical existence), one-attempt role settings, exact
external authority bindings and deterministic owner/attempt identifiers. Internal
pure helpers construct blind A/B request views and bounded requests. They are not
acceptance APIs and confer no eligibility or provider provenance.

Run read-only packaging preflight with:

```sh
PYTHONPATH=src python3 scripts/run-evaluation-work-unit.py --input WORK_UNIT_DIR
```

Valid packaging reports `BLOCKED_ELIGIBILITY_IMPLEMENTATION` and exit 2. Invalid
packaging reports `INVALID_WORK_UNIT` and exit 2. The command never initializes a
registry, reads credentials, dispatches, accepts scores or publishes a projection.
There is no production execute CLI or test-bypass flag.

Still unimplemented in 86a: governed graph/eligibility admission, registry-owner creation,
provider dispatch/artifact recovery, conditional resolution, pair selection,
comparison validation and deterministic submodel publication. The preceding
sections define their contract, not a claim that they already exist. Their tests
(including journal restart and artifact mutation) remain required before enabling
execution. Seven current tests cover blocked production admission, fabricated
pass/pilot identifiers, binding mutation, blind requests, disabled slots, bounded
request admission, semantic dependency views and blocked CLI exit behavior.
