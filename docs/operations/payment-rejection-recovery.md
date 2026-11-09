# Explicit payment-rejection recovery

Issue #51 adds an operator-controlled successor checkpoint for one narrow state:
one accepted primary followed by one unresolved verifier whose saved provider
artifact records HTTP 402, no served model or generation, and unknown usage/cost.
It does not recover ambiguous transport timeouts or other provider failures.

The original V2 implementation, authorization, journal and provider artifacts remain
unchanged. HTTP 402 is evidence of explicit rejection, but missing telemetry is not
proof of zero billing. Recovery retains the entire unknown reservation and carries
the known primary charge. Both physical calls also count against the original cap.
For the observed run, this leaves 19,328,356 microUSD of new exposure and four calls
under the original 26,000,000 microUSD/six-call ceiling. The 3,032,000 microUSD held
reservation is not a known charge. Model assignments, prices and role limits remain
unchanged. Routine verification/review may fit; the complete disagreement branch
needs five further calls and therefore cannot complete within the remaining four.
Never bypass required escalation to obtain closure.

`batch_recovery.prepare_successor` is read-only. It verifies the accepted primary
against the frozen workflow and recorded provider provenance, and returns a proposed
new V2 authorization plus checkpoint. These are not human approval. An operator must
approve the exact replacement attempt, validity window and unchanged model policy.
The authorization binds the checkpoint hash under `recovery/checkpoint-v1`.

`claim_successor` creates one append-only sidecar under the existing registry lock.
The claim binds the exact parent journal tip, rejected response artifact, accepted
primary artifact, carried exposure/calls, successor authorization, frozen paths and
replacement ID. Repeating the identical claim is idempotent; a second successor is
rejected. It does not rewrite any parent event or release the unknown reservation.

Call the existing `run_batch_role` API with `recovery_checkpoint=claim_path` and the
successor authorization. Primary provenance resolves to the preserved source
journal; newly generated stages resolve to the successor. Dispatching the primary
again, changing the replacement ID, tampering with a claimed checkpoint, or exceeding
the reduced limits fails closed. Repeating a settled replacement ID replays without
another HTTP request. The existing CLI does not yet expose this narrow recovery API;
do not omit the checkpoint or attempt to repair journals manually.

Funded account credits and a key's spending allowance are distinct. Check both
before a metered attempt, without logging credentials or account metadata to GitHub.
Recovery itself neither makes a provider call nor changes the graph. Independent
verification, exact release review and cumulative closure remain mandatory.
