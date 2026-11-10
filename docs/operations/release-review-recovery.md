# Explicit release-review recovery

Issue [55](https://github.com/michaelsena/turbo/issues/55) supports one narrow state:
an accepted primary and verifier, an exact compiled release preview, and one
unresolved release-review attempt recording HTTP 400 with no generation, served
model, usage or cost. It does not recover timeouts, model-quality failures,
escalated workflows, or arbitrary historical execution contracts.

The small qualification reached this state after spending $0.033487 in known
provider charges. Its ledger conservatively charged $0.161590 and holds $2.270
against the unresolved reviewer. The successor therefore has at most $2.568410
of exposure under the original $5 ceiling. These are different measures: neither
the held reservation nor conservative ledger charge is reported as provider spend.
The original three physical calls remain counted; the successor permits only one
exact replacement release call, stricter than the three calls otherwise remaining.

## Prepare and review before dispatch

Use `turbo.agents.batch_release_recovery.prepare_successor` with the predecessor
registry and authorization, exact workflow/input paths, replacement attempt ID,
operator identity and validity window. Preparation makes no provider call or claim.
It checks the accepted primary and verifier against the predecessor artifacts,
checks the failed release receipt and exact preview, and returns a proposed
successor authority and checkpoint. Inspect those results before authorizing the
replacement; implementation availability is not paid-run approval.

The successor keeps all role/model/provider/price policies unchanged. It binds the
checkpoint under `recovery/release-http400-v1`. `claim_successor` creates one
append-only predecessor claim; repeating the same claim is idempotent, while a
second successor is rejected. Neither call edits old journal events or releases
unknown exposure. Do not manually repair artifacts or construct an ordinary fresh
registry to reuse accepted research.

Pass the claim through the existing `run_batch_role(..., recovery_checkpoint=...)`
API. Only the exact replacement `release_reviewer` attempt is permitted. Upstream
provenance resolves to the original journal. A repeated completed attempt replays
without another request. A rejection, unresolved response or invalid review stops;
this is not an automatic retry or repair mechanism. There is no CLI shortcut.

## Preserve the reviewed compiler and graph

The preview remains byte-for-byte bound to its original compiler configuration and
execution commit. After an approving review, activation persistence must use that
original clean compiler checkout. The successor adapter checkout is not a substitute
for the reviewed execution commit. Validate the cumulative release, retaining the
original pilot markets, mappings and gaps, before publication. An accepted provider
response alone never activates a market.

## Error diagnostics

New HTTP/provider error receipts retain only a fixed vocabulary of provider codes,
parameter names, explicitly rejected schema keywords and provider-reported hints. Bounded parsing may inspect one nested
provider error envelope. Arbitrary messages, prompt echoes, credentials, metadata
and field paths are not persisted. The response hash remains available for exact
comparison. Hints are not proven causes and do not establish billing. Older errors
cannot be reconstructed from their hashes; the original HTTP400 cause remains
unknown. The endpoint capability catalog alone cannot prove a request compatible.

The older [HTTP402 procedure](payment-rejection-recovery.md) is unchanged and must
not be used for this HTTP400 state. Optional lossless model views are not supported
for either recovery path.

## Pinned model-view and citation continuation (Issue101)

The earlier plain-contract procedures above retain their original limits. The
`prepare_bound_successor` entry point additionally supports the exact clean service
runtime commit `f5fcbbd82c0fd5b847b26be96ac2a65522ef308a` and its registered lossless
model-view/citation policy. Pass `source_runtime`, the original registry/authority,
workflow/input paths, one new attempt ID, validity window/operator, and an explicit
`replacement_reviewer` role configuration. Only `openai/gpt-5.6-luna` with high reasoning
is supported by this increment; prompt/schema hashes, single-attempt limit and disabled
fallbacks must remain unchanged. Other role configurations are preserved.

Preparation verifies the original source in an isolated interpreter, reconstructs the
original failed request, replays accepted provider outputs and normalization traces,
and binds the parent journal tip and exact preview. It does not claim or dispatch.
The successor retains the unknown reservation and reduces its maximum cost by original
ledger charges plus that reservation; its call limit is one. Use `claim_successor` and
existing `run_batch_role(..., recovery_checkpoint=...)` after independent review,
explicit authority and measurement of the actual replacement request/endpoint. A
same-tree source checkout with a different commit is not a substitute for the pin.

After a settled approving replacement, call
`verify_bound_release_approval(registry, authority, checkpoint_path)`. This read-only
proof verifies the successor journal, raw provider artifact, exact upstream lineage,
and compiler approval. The old controller correctly stays STOPPED; never edit its
manifest/journal or report it approved. With this proof, existing lower-level closure
and guarded graph publication APIs may continue in a separate publication clone at
the exact reviewed execution commit. Preserve all historical input/preparation paths.
The new proof is not canonical publication, market eligibility, or an investment score.
