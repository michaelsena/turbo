# ADR 0011: Batch-output artifacts and managed settlement

## Status

Proposed for [Issue 33](https://github.com/michaelsena/turbo/issues/33), Track B4 of
Issue 15. Local tests, synthetic replay, and independent review remain pending.
This is a fake-transport integration; it enables no real provider or research spend.

## Context

B3 accepts finite floating-point confidence in a structurally valid boundary output.
B1's simulation ledger intentionally rejects floats throughout its response envelope.
Embedding B3 output directly would weaken that ledger contract or discard confidence.
The two contracts also answer different questions: usage settlement records consumed
capacity, while output validation checks structural obligations and references.

## Decision

Preserve B1/B2 schemas and arithmetic. Store the full confidence-bearing response
and validation receipt as immutable, hash-bound artifacts. The journal settles a
compact integer/string-only reference to those artifacts, never the raw B3 output.

Regenerate verified V2 context and bind the request, deterministic invocation,
authorization, prompt/schema, and preparations before fake transport. Use the
canonical managed registry journal and its reservation, attempt, and resume rules.
Store `research_contract_sha256(root=...)` in the existing authorization
`prompt_sha256` slot: it binds artifact kind, raw B3 prompt hash, output-schema hash,
and output/context byte limits before claim or dispatch. B3 context keeps the raw
prompt hash, while the artifact receipt also records `execution_contract_sha256`.
This strengthens schema binding without changing B1/B2 schemas.
A repeated or restarted attempt must not call transport again.

Charge known valid bounded usage even if output fails structural validation. An
invalid output is not free execution. Invalid or unknown usage, ambiguous transport,
or uncertain artifact persistence retains the reservation, with no automatic refund
or retry. Do not inherit an older provider runner's automatic retry loop.

Replay must verify artifact ownership and bytes, context and request bindings,
structural verdict, and exact journal reference. Missing, altered, mismatched, or
transplanted artifacts fail closed. Artifacts do not become research conclusions
merely because their structure or hashes validate.

## Consequences and boundary

- Confidence-bearing output survives without adding floats to the ledger.
- Usage settlement, structural validity, substantive research review, and graph
  acceptance remain separate states.
- Ambiguous work may retain its full reservation until a reviewed reconciliation
  mechanism exists.
- Fake-transport tests and synthetic replay establish implementation behavior only.
  Real provider integration, production spend authority, selective substantive
  verification, disagreement handling, and family closure remain separate work.
- No live execution CLI, score, market activation, or frontend change is introduced.
  Historical verification receipts remain unchanged.
