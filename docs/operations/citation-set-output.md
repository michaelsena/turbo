# Prospective citation-set output adapter

[Issue 95](https://github.com/michaelsena/turbo/issues/95) adds an opt-in provider
contract for exact repeated evidence IDs. It does not recover failed attempts.
Create a fresh workflow and authority on the reviewed runtime, passing
`citation_sets=True` to `batch_provider.execution_contract_hashes` and
`batch_provider.contract_bindings`. Use the same option for `role_schema` and
`render_assignment` when measuring each real request before dispatch. The managed
runner derives the selected option from the immutable authority's policy binding.
The existing registry, budgets, role sequence and independent review still apply.

Only B3 payload citations in proposed markets (including their seven dimensions),
identity dispositions, candidate dispositions and research gaps are eligible.
The exact `supporting_evidence_ids` and `counterevidence_ids` paths must resolve to
canonical string evidence-ID arrays with `uniqueItems: true`. The provider schema
permits repetitions there; all other constraints remain. The host preserves the
first occurrence of each identical string, then applies unchanged canonical schema
and semantic validation. No metadata, verdicts, subject coverage, gaps, boundaries
or evidence membership are repaired. Verifier and release-review citations and
attestations are outside this policy.

Artifacts retain original `output_base64` and provider body hash. The additional
`citation_normalization` receipt records policy version/hash, canonical document
hash and exact JSON pointers/removed indices. Settlement replay, upstream provenance
and controller inspection recompute this receipt from raw bytes and the canonical
schema, verify the exact authorized provider schema and compare the canonical
submission. A trusted-looking receipt alone is insufficient.

Without the opt-in, raw parsed JSON must still equal the canonical document and a
normalization receipt is rejected. Historical runs require their original frozen
runtime; new code/source hashes cannot be substituted into old authorities. The
adapter cannot be attached through recovery checkpoints. Invalid model output
remains failed, including invented/wrong-subject citations, missing applicable gaps,
duplicate dispositions and incorrect upstream hashes. Preserve failed attempts;
never import their output into a new accepted run.
