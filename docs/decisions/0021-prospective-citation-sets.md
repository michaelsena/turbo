# ADR 0021: Prospective citation-set normalization

Status: accepted for opt-in fresh managed runs under Issue 95.

A repeated identical evidence citation has no additional set meaning, but previously
failed provider schema validation before canonical semantic checks. Paid runs also
exhibited semantic and metadata defects; those remain failures.

We retain strict canonical schemas and add an explicitly selected, source-bound
provider contract that permits repeated strings only at enumerated B3 citation-set
paths. Deterministic first-occurrence deduplication records a replayable trace while
preserving raw bytes. Every provenance reader recomputes the transformation; the
normalization policy and exact wire schema are bound to the fresh authority.

This does not normalize arbitrary unique arrays, replace metadata, infer evidence,
repair missing obligations, reopen historical attempts or change review gates.
Default output validation remains raw-document equality. Literal upstream hash
navigation is a separate request-side aid; hash attestations remain model-authored
and strictly validated.
