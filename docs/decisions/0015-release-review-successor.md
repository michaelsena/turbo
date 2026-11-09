# ADR 0015: Preserve verified research after release-review HTTP400

Status: implemented for review under issue #55; no replacement paid call authorized
by this code change.

A small plain qualification passed primary and selective verification, but its
release reviewer returned HTTP400 without usage or cost. Re-running research would
waste accepted results; overwriting the journal or resetting its cap would destroy
accounting. The existing HTTP402 recovery covers a different state and remains
unchanged.

Add a separate, explicitly claimed successor for a pinned predecessor contract:
exactly accepted primary and verifier, exact compiler preview, and an unresolved
HTTP400 release receipt without generation metadata. Import both upstream provenances and bind
the preview; subtract conservative committed charges and the full unknown exposure.
Carry all prior physical calls and allow one exact replacement reviewer only.
Keep role and routing policies unchanged. Reject timeout recovery, forks, tampering,
upstream redispatch, encoded recovery and arbitrary predecessor implementations.

Preserve the original reviewed compiler commit for activation. A successor review
can approve the same preview; it cannot silently replace it or publish new events.
The existing release gates and cumulative replay remain mandatory.

Retain bounded, fixed-vocabulary error diagnostics for future HTTP/provider
failures. Do not persist arbitrary response messages or infer zero billing. This
improves diagnosis without claiming to have identified or fixed the original400
cause. A new request remains an explicit operator decision after review.
