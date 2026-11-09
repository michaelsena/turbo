# ADR 0008: Batch authorization and execution ledger

## Status

Implemented and locally verified in [PR #21](https://github.com/michaelsena/turbo/pull/21),
which remains unmerged. The [verification receipt](../operations/receipts/2026-11-09-batch-ledger-verification.json)
records exact replay and independent review. This increment exercises a fake transport only. It authorizes no live model
call, research spend, market decision, or graph activation.

## Context

A valid family evidence pack proves its inputs and scope. It does not grant permission
to dispatch a model request. Batch execution needs a separate, replayable record of
what may run, under which model/provider and price assumptions, how much capacity is
reserved, and what remains uncertain after an interruption.

A retry can cost money even if a previous call produced no usable result. A process
crash or transport timeout cannot prove that a remote provider did no work. Refunding
such a reservation or automatically dispatching again would make local budget checks
weaker than the actual exposure.

## Decision

1. Bind an authorization to 2–8 exact family preparations from one scheduled batch,
   retaining their manifest order and file hashes. Pin both execution-schema hashes. Preserve each family's identity
   and evidence-pack boundary inside the batch.
2. Record explicit validity bounds, model/provider and price bindings, call and cost
   caps, retry/repair allowances, and concurrency. B1 is one batch-primary task with
   exactly one active attempt. Concurrency 2 is rejected until a separate multi-task
   scheduler defines independent work and shared budgeting.
3. Represent cost as integer microdollars. Reserve the permitted worst-case amount
   before dispatch, with confirmed cost plus outstanding reservations plus the new
   reservation remaining within the authorization cap.
4. Serialize ledger transitions with a process-safe lock. A persisted transition,
   rather than an in-memory flag, governs whether an attempt may dispatch.
5. Allow one initial request followed by a linear retry/repair chain. An arbitrary
   new initial ID cannot reset the batch's retry allowance. Keep attempt identity and
   resume behavior idempotent: repeating a completed or dispatched attempt must not
   create another transport call.
6. A reservation whose lease expires before dispatch may release its funds, but its
   consumed call allowance remains. Retain ambiguous dispatch as an unresolved
   reservation. An expired lease or missing response is not evidence of zero cost.
   There is no automatic retry or refund of an ambiguous attempt.
7. Treat retry and repair as one bounded allowance. A new attempt must identify a
   failed, settled predecessor or a safely released undispatched predecessor. Each
   uses a fresh request ID, consumes a call and retry allowance, and reserves funds;
   the chain cannot fork. An output problem does not erase earlier cost or reset the authorization budget.
8. Replay durable authorization and ledger records to inspect scope, attempts,
   confirmed cost, outstanding reservation, and retry/repair use. Malformed or
   contradictory records must fail validation rather than be silently repaired. The
   hash chain does not prove completeness against a wholesale rewrite or deletion
   to a valid prefix; retain an independent receipt pinning the accepted output tip.

9. Require `budget_scope: single_journal_simulation` in the authorization and expose
   it in status. Budget and idempotency checks apply to one trusted journal only.
   Copying an authorization into a new directory starts separate counters; B1 does
   not provide global spend authority.

## Implementation boundary

Track B1 provides the authorization and ledger foundation with deterministic fake
transport exercises. The public command surface does not dispatch live models. No
provider credential is required, and no external response is treated as research.

Before any live adapter or paid canary, a later increment must add a shared
spent-authorization registry or deterministic governed execution namespace. This is
an open blocking requirement for live use. B1 must not serve as production
authorization.

A later increment must supply and review the actual model adapter, output contract,
selective verification, disagreement escalation, and provider-cost reconciliation.
Track C must add reviewed activation or no-graph-movement closure and cumulative
release integration. The metered canary requires a separate explicit authorization;
passing fake tests does not authorize it.

## Consequences

- Transport success, schema-valid model output, reviewed research, and accepted graph
  movement remain distinct states and authorities.
- Interrupted work may remain unresolved and retain budget indefinitely. This is
  intentional until reliable reconciliation is available.
- Concurrent workers targeting the same journal share durable budget state. Separate
  execution directories do not share counters, even with identical authorizations.
- An authorization is a bounded execution input, not a reusable blanket permission
  for another batch, model, provider, price assumption, or time window.
- Current market counts, accepted boundaries, gaps, Target eligibility, and scores
  remain unchanged by this increment.
