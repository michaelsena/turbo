# Opt-in readable references for the release reviewer

This representation is available only through a fresh, explicit authorization.
Plain requests remain the default. It has not passed a model-quality qualification
and must not be enabled automatically or used to justify projected spend savings.
Primary, verifier, escalation and adjudicator assignments remain plain JSON.

Use `batch_provider.execution_contract_hashes(reviewer_view=readable.FORMAT)` and
`batch_provider.contract_bindings(input_root=..., reviewer_view=readable.FORMAT)`
when constructing a new authorization. Here `readable` is
`turbo.agents.readable_request_candidate`. Both its policy digest and source digest
are frozen in the execution contract; only the reviewer's prompt binding changes.
The `run_batch_role` interface has no representation override. It selects the
representation from the authority and uses the same rendered bytes for admission
and the actual request. Existing authorizations cannot silently opt in. Combining
this representation with the legacy lossless view or a recovery checkpoint fails
before admission. Existing historical research cannot be relabeled under a new
authority to obtain a compressed review.

The first occurrence of each complete object or array stays inline with its original
field names and values. Subsequent identical containers may reference that earlier
location with an explicit JSON Pointer. Scalar strings and IDs are not abbreviated.
IDs inside a referenced container are retained at its first location and recovered
at every use; they are not repeated literally at every reference. Canonical sorted
traversal keeps references backward even after wire serialization. Marker collisions
are escaped by selecting an unused marker key. The decoder rejects unknown,
forward, ancestor and malformed references, limits expanded bytes, and checks the
original canonical SHA-256. No evidence is selected, summarized, merged or dropped.
Canonical output schemas, original submission documents, preview binding, upstream
provenance checks and post-response validation are unchanged.

## Offline measurements and limits

These measurements cover complete assignment JSON, including its representation
wrapper/instructions, but exclude the unchanged provider prompt and schema. The
integration additionally appends reference instructions to the reviewer prompt, so
these are not complete HTTP request sizes. No provider tokenizer was available.

| Assignment | Plain bytes | Referenced bytes | Reduction |
| --- | ---: | ---: | ---: |
| Accepted small primary, offline candidate only | 191,358 | 177,674 | 7.15% |
| Accepted small verifier, offline candidate only | 216,391 | 202,707 | 6.32% |
| Accepted small reviewer | 552,984 | 257,537 | 53.43% |
| Blocked medium primary, offline candidate only | 1,597,231 | 1,472,122 | 7.83% |

The primary/verifier measurements informed rejection of all-role integration; those
roles are not encoded in production. This change does not unblock the medium primary
request. Exact decoder roundtrips and synthetic transports establish software
behavior, not whether a reviewer can reason reliably across references.

## Qualification before live adoption

1. Freeze two offline reviewer assignment fixtures. The positive fixture contains
   the accepted small workflow's exact original compiler preview and dependencies.
   The negative fixture contains a known material unsupported identity or evidence
   claim, with an independently specified expected finding and verdict. Keep the
   accepted source artifacts immutable; produce the negative fixture separately.
2. For each fixture, verify canonical roundtrip, all evidence/identity IDs and hashes,
   unchanged schema, and exact preview binding. Record full provider-request byte
   counts for plain and referenced versions, including prompt/schema overhead.
3. Synthetic tests must prove unchanged canonical approve/reject handling, refusal
   of a wrong approved-preview digest, identical admission/HTTP representations,
   no dispatch after cap/binding failure, and idempotent replay. These are software
   tests only; do not record their outcomes as model-quality evidence.
4. A later separately approved, budgeted model comparison must hold model, routing,
   reasoning effort, output limit, canonical assignment and schema constant. Compare
   plain versus referenced requests on both fixtures without sharing answers.
   Require exact preview/evidence references, all independently expected material
   findings, correct approve/reject behavior and no missing mandatory checks.
   Track actual usage, cost and latency. Any missed material finding blocks adoption.
5. Until that comparison is accepted, leave operational authorization builders on
   their plain defaults. No automatic retry, budget increase or production enable
   follows from successful software tests or smaller byte counts.
