# ADR 0009: Trusted local execution registry

## Status

Proposed for Issue #15 Track B2. This extends the simulation foundation in
[ADR 0008](0008-batch-authorization-execution-ledger.md). Acceptance requires local
replay and independent review; B1 verification does not establish B2 acceptance.

## Context

B1 enforces budget and idempotency within one journal. Copying the same authorization
into another directory creates independent counters. Managed clients need one stable
place to find an authorization's existing journal, rather than choosing a fresh
execution directory and resetting its apparent consumption.

## Decision

Use one explicitly initialized, trusted local registry. Within that registry, the
canonical authorization digest identifies one durable claim and one canonical
execution journal. A managed client does not choose an arbitrary output directory.
Repeated access to the same authorization resumes its existing consumption and
attempt history. A claim whose journal is missing must fail closed; missing durable
state is not evidence of an unused authorization.

Registry identity binds a UUID, its resolved root path, and the registry schema and
implementation hashes. Initialization requires a new directory under an existing
parent, exclusively creates that directory, and writes registry metadata last.
Claim creation and inspection use same-host POSIX file locks. Persist the claim before creating the journal, then write an immutable ready
receipt after the initial journal is durable. Existing claims with missing ready
receipts or missing/partial journals fail closed; there is no automatic recreation,
adoption of an unclaimed journal, or refund. Recovery policy for such interrupted
initialization remains future work.

Release the registry lock before invoking B1 operations or fake transport. B1's
per-journal locks serialize attempts and reservations. The registry exposes no
claim deletion or rebinding API. Fixed registry paths reject symlinks.

Keep B1's standalone journal API available with its original per-journal scope.
Registry-managed execution is a separate simulation control, not a retroactive
extension of standalone journals or a production spending authorization.

## Trust boundary

The guarantee covers clients using the same trusted local registry. It does not
combine counters across different registries, prevent someone from minting another
unsigned authorization, or survive an operator deleting or replacing the entire
trusted state. Privileged filesystem mutation during an operation is also outside
the boundary. Registry identity and durable claims make the local boundary explicit;
they do not establish an external authority or tamper-proof spending history.

Real provider integration and a paid canary remain blocked on a reviewed production
authorization and trusted-state governance design, as well as the remaining adapter,
output-validation, reconciliation, and research-review contracts. No model call,
research spend, score, or market activation is authorized by this decision.

## Consequences

- Repeated managed clients share one authorization's journal within one registry.
- Missing claimed state, including an incomplete initialization, requires
  investigation rather than automatic replacement; manual recovery is not yet
  implemented.
- Standalone B1 callers retain their documented ability to create separate journals.
- Existing evidence, accepted markets, open gaps, Target eligibility, and scores stay
  unchanged; this increment tests execution control with fake transport only.
