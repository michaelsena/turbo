# ADR 0010: Standalone batch-output contract

## Status

Implemented for Issue #15 Track B3 in [PR #25](https://github.com/michaelsena/turbo/pull/25),
merged at `73bf1f8`. Local tests, synthetic replay, and independent review passed.
See the [verification receipt](../operations/receipts/2026-11-09-batch-output-verification.json).
This increment validates synthetic output structure only; it makes no provider call
and does not accept research, alter scores, or activate market boundaries.

## Context

A durable execution journal proves attempts and simulated consumption. It does not
establish that a response covers every required family obligation, cites available
evidence, preserves unresolved gaps, or supplies a reviewable boundary proposal.
Batching must not let one family's context substitute for another family's required
coverage or make structural validity look like an accepted research conclusion.

## Decision

Build an output-validation context from verified V2 family preparations. Bind the
request, prompt, schema, and context so an output cannot silently substitute another
batch. Keep required identities and candidates distinct from contextual material.
Require each required obligation exactly once, with evidence references restricted
to the corresponding family's frozen inputs.

Keep `fact`, `inference`, `assumption`, and `unknown` explicit, alongside finite
confidence values from zero through one and explicit gaps for unresolved work.
Boundary proposals describe all seven operating-identity dimensions and use valid
cross-references. These are structural checks: a well-formed proposal still requires
substantive evidence review and the existing governance path before acceptance.

## Integration boundary

This contract is standalone. B1 rejects floating-point values anywhere in its fake
response envelope, including output; confidence values in this new contract are not
automatically compatible with that envelope. No execution-settlement wiring or
provider adapter was introduced in B3. [ADR 0011](0011-batch-output-artifacts.md)
defines the subsequent simulation artifact bridge. Later integration must explicitly reconcile
these contracts and verify their behavior before enabling any paid canary.

Synthetic examples test contract acceptance and rejection, not research quality.
Model selection, real dispatch, output adjudication, selective independent review,
provider reconciliation, and reviewed family activation or no-movement closure
remain separate work. Current research counts and scores remain unchanged.
