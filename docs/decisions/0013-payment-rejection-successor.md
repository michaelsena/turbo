# ADR 0013: Preserve research through an explicit payment-rejection successor

Status: implemented and merged in PR #53. Issue #51.

The live verifier received HTTP 402 after a successful primary. V2 correctly held
unknown exposure but had no recovery transition. Editing its immutable authority
or journal would invalidate replay, and a new ordinary authority could not reuse
the primary because upstream provenance was bound to the old journal.

Keep V2 byte-for-byte unchanged. Add a separately pinned recovery contract with a
single-successor claim and an immutable predecessor checkpoint. Import only the
verified accepted primary's provenance; do not fabricate a new primary invocation.
Subtract both predecessor calls, known charges and the full unknown reservation
from the successor's limits. Treat the explicit HTTP 402 as eligibility evidence,
not evidence of zero cost. Permit one exact operator-authorized verifier replacement,
not an automatic retry loop or general unresolved-attempt override.

This deliberately supports one known predecessor execution contract plus the current
contract. Arbitrary historical versions require a separately reviewed migration.
All source artifacts remain available to their original replay implementation.
Forked recovery, post-claim metadata changes and budget resets are rejected.

The cost of preserving the original physical-call ceiling is that a full escalation
branch may not fit after a rejected attempt. Stop explicitly rather than skip stages
or silently enlarge the authorization. No generic budget-amendment framework is added.
