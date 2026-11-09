# Issue 15: Batch-native family research

## Governing universe workflow

The chairman explicitly reaffirmed this issue's later batch plan for universe
construction. Use one batch primary, selective independent verification for
preregistered risk/QA triggers, conditional two-blind escalation for material
ambiguity, and adjudication when independently valid results materially disagree.
Mandatory independent review of exact planned graph movements precedes deterministic
activation or reviewed no-movement closure and cumulative publication. Packing
families into calls does not remove per-family coverage, lineage, or review gates.

The original Issue 12 two-blind/mandatory-adjudicator pilot and the later market
scoring/comparator protocol have different scopes. The six exploratory manual
hypotheses remain provisional drafts, not accepted results. See
[ADR 0012](../decisions/0012-research-workflow-scope.md) and
[Issue 39](https://github.com/michaelsena/turbo/issues/39) for implementation.

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

- Track B1: merged authorization and execution-ledger foundation, exercised with
  fake transport only; its scope and acceptance are described below.
- Track B2: trusted local registry for managed authorization consumption; simulation
  only, merged and locally verified.
- Track B3: implemented in PR #25; all 237 Python tests, 22 focused checks, synthetic
  replay, and independent review passed. Merged at `73bf1f8`.
- Track B4: artifact-backed managed simulation integration in Issue #33 is verified
  in merged [PR 35](https://github.com/michaelsena/turbo/pull/35); see the
  [B4 receipt](../operations/receipts/2026-11-09-batch-research-verification.json).
- Current Issue #39 increment: V2 shared-role accounting, one-attempt provider
  adapter, and primary/verifier integration. Controlled-transport acceptance remains
  pending; no paid calls or new market activations are claimed.
- Later integration: escalation/adjudication/release dispatch and a complete
  independently reviewed provider-backed run.
- Track C: progress events, closure receipts, cross-family conflict checks, and
  cumulative graph-release integration.
- Metered canary: only after exact local replay, independent review, and separate
  chairman spend authorization.

## Second independent-review correction

The second review found evidence omissions despite successful integrity checks.
Preparations now include required NAICS Manual definitions, examples, cross-references,
coordinate fragments, and index entries with their original snapshot/page locators.
Official index absence is explicit. A separate source binding verifies the complete
source-run receipt and artifact bytes; it adds the Manual artifact without rewriting
the historical schedule or its frozen inputs.

Retrieved prior candidates owned by another family are retained as context-only cards
with labels and source records. They never enter this family's required dispositions.
All semantic and candidate evidence participates in item/byte gates and exact replay.
Configs and packs bind every Turbo Python source file and both executable V2 schemas.
Any implementation/schema change creates a new preparation identity; replay of an old
preparation requires its original checkout. Model prompt binding remains a runner
responsibility because Track A invokes no model.

A concurrent re-audit also identified malformed nested JSON types escaping as Python
exceptions. Pack and persisted-preparation validation now checks executable schemas
before nested field access and returns structured errors for these inputs. Regression
cases cover malformed metadata, scope, counts, and family IDs.


## Track B1: authorization and execution-ledger foundation

This increment tests execution control before enabling real model calls. It binds an
exact prepared family batch to explicit time, model/provider, price, call, cost,
retry/repair, and concurrency limits. The 2–8 prepared families must come from one
scheduled batch and retain manifest order. Integer microdollar reservations are
persisted before dispatch under a process-safe lock. Replaying an attempt is idempotent.
B1 permits one batch-primary task with one initial request and a linear retry/repair
chain. `max_concurrency` is exactly 1; concurrency 2 and independent task scheduling
are deferred rather than allowing new initial IDs to bypass retry limits.
A subsequent attempt must reference a failed, settled or safely released undispatched
predecessor; it consumes both call and retry allowances, and the chain cannot fork.
Confirmed cost and outstanding reservations jointly consume the authorized budget.
Ambiguous dispatch retains its reservation and cannot be automatically retried or
refunded merely because a worker or lease expired.

Authorization and status explicitly declare
`budget_scope: single_journal_simulation`. Budgets and idempotency apply within one
trusted journal; copying authorization to another directory does not share counters.
A shared spent-authorization registry or deterministic governed execution namespace
is a blocking requirement before any live adapter or paid canary. B1 is not
production spend authority.

The transport used by this increment is fake. There is no live execution command,
provider credential, new source evidence, market conclusion, or activation. A fake
successful response is not a validated boundary decision. Code/schema/output review
and exact-head local tests are required before accepting the infrastructure; separate
spend authorization and later adapter/output/closure work precede a metered canary.

The CLI exposes `batch-dry-run <authorization> <preparation_dirs...>`,
`batch-status <execution_dir>`, and
`batch-validate-execution <execution_dir> <preparation_dirs...>`. These are validation
and inspection commands; none dispatches a transport.

See [ADR 0008](../decisions/0008-batch-authorization-execution-ledger.md) for the decision
and the [runbook](../operations/runbook.md) for the implemented inspection commands.

## Track B1 verification

[PR #21](https://github.com/michaelsena/turbo/pull/21) implements the scoped
single-journal simulation foundation, merged at
`247b8c25822147c36f8eae0aece16d3214db4095`. The
[verification receipt](../operations/receipts/2026-11-09-batch-ledger-verification.json)
records 190 passing Python tests (28 focused), exact two-family simulation replay,
independent review, code/input/output hashes, and unchanged research state.
No live provider call or production spend authority is included.

## Track B2: trusted local registry

B2 binds each canonical authorization digest to one claimed execution journal within
one explicitly trusted local registry. Managed clients resolve that journal rather
than supplying arbitrary output directories. Reopening the same authorization must
retain its attempts and consumption; a missing claimed journal must fail closed.

This does not coordinate different registries or prevent new unsigned authorizations,
and it cannot establish continuity after deletion of the entire trusted state.
Standalone B1 remains per-journal. Real providers, spending authority, and research
execution remain outside B2; production authorization and state governance require
separate review before any paid canary. See
[ADR 0009](../decisions/0009-trusted-local-execution-registry.md).

## Track B2 verification

[PR #23](https://github.com/michaelsena/turbo/pull/23) merged at
`639c3216ac5d3e3baf28fcffbeac8af5bf8e478d`. Its
[verification receipt](../operations/receipts/2026-11-09-shared-registry-verification.json)
records 215 passing Python tests (25 focused registry checks), independent review,
and a two-family simulation in which two managed clients share one journal and
cannot reset its cost/call state. The public-wrapper binding regression is covered.
No real provider call, approval authentication, or research activation is included.

## Track B3: standalone output validation

[PR #25](https://github.com/michaelsena/turbo/pull/25) implements B3. All 237 Python
tests passed in 675.858 seconds, including 22 focused checks that separately passed
in 71.554 seconds. Independent review found no blocking issues. Synthetic replay
covered one required identity and 58 candidates with explicit unresolved gaps and
no graph mutation. The PR merged at `73bf1f8`. The
[verification receipt](../operations/receipts/2026-11-09-batch-output-verification.json)
records exact tested commits, hashes, runtime, and limitations.

B3 adds a structural contract over verified V2 family preparations, preserving
required identity/candidate coverage and family-specific frozen evidence references.
The request and invocation IDs, prompt/schema bindings, context, and output limit
identify what a submitted document must answer. Context is regenerated during
validation rather than trusting a caller-edited coverage list.

This increment exercises synthetic outputs only. Structural validity and bounded
confidence do not establish factual correctness, calibration, or a reviewable
research conclusion without substantive quality review. B3 itself does not wire the contract
into B1/B2 settlement: B1's fake response envelope rejects floats, while B3 permits
finite confidence values. B4 addresses the simulation artifact bridge below; real
providers, research review, and activation remain separate work. See [ADR 0010](../decisions/0010-batch-output-contract.md) and
the [runbook](../operations/runbook.md#batch-output-contract-inspection-track-b3).

## Track B4: immutable output artifacts and managed settlement

[Issue 33](https://github.com/michaelsena/turbo/issues/33) connects B3 validation to
managed simulation execution without changing B1/B2 schemas. Full confidence-bearing
responses and validation receipts live in immutable artifacts; compact hash-bound
references enter the integer-only ledger. Repeated or restarted managed attempts
must not dispatch again.

Known valid bounded usage is charged even for structurally invalid output. Unknown
or invalid usage, ambiguous transport, and uncertain persistence retain reservations
without automatic retry or refund. Replay checks artifact ownership, bytes, input
and context bindings, verdict, and journal references. Structural validity is not
substantive evidence review or research acceptance.

[PR 35](https://github.com/michaelsena/turbo/pull/35) is merged; its pinned verification recorded:
23 focused and 282 full-suite tests pass; independent review found no P0/P1/P2
issues. The synthetic canary charged 20 microUSD for invalid coverage and 24 for a
valid retry, retained zero outstanding reservation, and replayed without another
callback or file change. The canonical graph remained unchanged. See the
[verification receipt](../operations/receipts/2026-11-09-batch-research-verification.json).
No real provider, live execution CLI, score, graph activation, or frontend change
is included. See
[ADR 0011](../decisions/0011-batch-output-artifacts.md).

## Governed provider integration: first increment

[PR 40](https://github.com/michaelsena/turbo/pull/40) connects primary and verifier
roles to a V2 shared authorization journal and one-attempt OpenRouter adapter.
All 357 Python tests pass, including the 40 focused provider/accounting/integration
checks; independent review has no outstanding P0/P1/P2 findings. Repository
validation and documentation links pass. See the
[exact verification receipt](../operations/receipts/2026-11-09-batch-provider-verification.json).

No real provider call or graph activation occurred. Escalation, adjudicator, and
release-review provider dispatch remain blocked pending their integration. The
offline workflow/closure APIs do not establish an end-to-end metered canary.
Issue 39 and this parent remain open.
