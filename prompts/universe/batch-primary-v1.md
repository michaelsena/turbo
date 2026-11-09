# Batch-primary boundary output contract V1

This contract defines a structured boundary-research response. It does not authorize
model execution, external research, paid sources, graph activation, Target selection,
or investment scoring. Structural validation is not research approval.

Use only the verified batch context supplied by the caller. Return one JSON object
matching the pinned batch-primary-output schema. Echo the exact request, invocation,
context, schema, prompt, family, preparation, and pack bindings. Preserve family order.

For each family, dispose every required identity and every required prior candidate
exactly once. Context identities and candidates may inform reasoning but never enter
the primary disposition lists. A candidates-only family has an empty identity list;
no proposal is required when no mapping is supported.

Cite evidence_id values from that family's evidence_catalog only. These are views
of complete immutable pack items, with exact JSON pointers and item hashes. They
are not new evidence. Each disposition needs at least one supporting item whose
subject_ids contains its own required identity or candidate. A citation's structural
validity does not establish that it supports the stated interpretation.

Use the supplied proposal_id_prefix and gap_id_prefix for new local IDs. Never
reference another family's proposals or gaps. Existing graph references must be in
that family's graph_market_ids. Proposals need seven operating-identity dimensions,
explicit exclusions, typed reasoning, confidence, and citations. The dimensions are
buyer, job, delivery, workforce, economics_risk, acquisition_universe, and
ambient_ai_workflow. Labels are fact, inference, assumption, or unknown; confidence
must be a finite number between zero and one. Do not manufacture numerical certainty.

Identity map_to_proposals and provisional_map_to_proposals require one or more
proposal references; all other identity outcomes require none. Candidate adopt,
change, and merge_input require exactly one proposal; split_input needs at least
two; provisional_map_to_proposals needs one or more; reject and unresolved need none.
Every proposal must be used by a required disposition in its own family.

Every unresolved or provisional disposition needs a local research gap that names
its subject and gives a concrete retry_trigger. An unknown disposition label, or an
unknown dimension in a referenced proposal, also requires an applicable gap. Gaps
may name required identities and candidates only, and must retain current judgment,
typed reasoning, confidence, and citations. Preserve uncertainty instead of turning
source categories or retrieval matches into accepted operating markets.
