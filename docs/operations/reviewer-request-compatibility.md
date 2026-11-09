# Google release-review schema compatibility

Issue [57](https://github.com/michaelsena/turbo/issues/57) addresses the repeated
HTTP400 rejection after successful primary and selective verification.

## Diagnosis and controlled check

The raw provider error was only `Request contains an invalid argument.` The saved
error hash was identical across the original and replacement requests. A separately
logged, small diagnostic with the original reviewer schema reproduced HTTP400.
A second diagnostic kept the prompt, model, route, reasoning and output limit the
same, removing only `properties.findings.maxItems`. It reached HTTP200 and generated
tokens. Its deliberately small output budget truncated the response: this proves
request compatibility for that probe, not an accepted review or research result.
Neither probe submitted a workflow role, approved a preview, or activated a market.
The [compatibility receipt](receipts/2026-11-09-reviewer-schema-compatibility.json)
records both provider-schema hashes; the implemented adapter exactly reproduces
the schema that reached HTTP200.

The findings array allowed 20,000 objects. Google's structured-output documentation
explains that large array limits can make the constrained-output grammar too complex
and produce HTTP400. `maxItems` is supported, but its numerical bound can still make
a particular schema impractical to compile. This distinction matters: the field is
not universally unsupported.

Sources:
- [Google structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Google Cloud schema considerations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output)

## Narrow request adaptation

`openrouter_role_schema` applies the existing provider portability conversion, then
omits only `properties.findings.maxItems` for Google `release_reviewer` calls.
Admission and transport use the same function. The recorded provider-schema hash
binds the actual sent schema. Other roles, non-Google models, nested object shapes,
required hashes, strings and remaining constraints keep their existing behavior.

The canonical role schema and its authorization hash are unchanged. Turbo validates
the returned document against that full schema, including the original 20,000-item
limit, before workflow acceptance. Changing the provider grammar cannot approve a
wrong preview, bypass substantive checks, or remove evidence gaps.

## Continuation and accounting

A corrected review needs fresh, explicit authority that accounts for the original
run, failed successor and both diagnostic attempts. The old journals and their
reservations remain immutable. The second diagnostic reports usage and cost, but its
ledger callback supplied an invalid artifact-reference type, so that journal remains
unresolved with the reported telemetry retained. Do not silently edit it or treat the
held amount as a charge; carry the full reservation conservatively.

The original call allowance is exhausted. Implementation of this request fix is not
permission to reset the budget or launch another call. Prepare a concrete aggregate
budget/call amendment, retain every earlier attempt, and permit only one corrected
release review after explicit approval. Primary/verifier and exact preview must be
reused through validated provenance. Exact review approval, original clean compiler
commit, cumulative replay and closure remain mandatory before publication.

## Preparing the corrected review

`batch_request_repair.prepare_successor` is read-only. Supply the original registry,
source authority, workflow/input paths, exact new attempt ID, operator identity,
validity window, and explicitly proposed `aggregate_max_cost_microusd` and
`aggregate_max_calls`. The latter must equal all preceding physical calls plus one.
The new role reservation must fit after every preceding charge/reservation is carried.
A returned proposed document does not establish user approval.

This procedure supports only the released original contract, its released first
successor, and the two identified diagnostic sidecars. It verifies all four journals
and rejects unaccounted authority claims. It binds the source journal tips, old claim
hashes, rejected-provider artifacts, upstream hashes and exact preview. Do not omit
one diagnostic because it failed or did not produce valid content.

After explicit approval, `claim_successor` creates one append-only corrected-review
claim. Pass it through `run_batch_role(..., recovery_checkpoint=...)`; its checkpoint
kind selects the corrected-review execution path. Only the exact release role and
attempt may dispatch. Research roles, changed inputs, forked successors and reused
attempt IDs fail closed. Repeating a completed attempt replays without a new call.
The source journal tips, sidecars and authority inventory are rechecked under the
registry lock at claim and dispatch. The dispatch guard holds that lock through the
one managed call so an unaccounted authority cannot enter during reservation.
A new failure stops rather than widening the amendment.

Use the original reviewed compiler checkout for activation persistence. The prepared
staging path should retain the original pilot rows and keep the canonical pointer
unchanged until the cumulative release and closure have been verified and published
through the repository's normal review process.
