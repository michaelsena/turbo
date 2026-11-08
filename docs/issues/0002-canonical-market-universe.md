# Build the canonical multi-source American Market Universe

## Outcome

Reconcile NAICS, NAPCS, and the prior 978-market seed into a versioned set of
canonical operating markets before downstream eligibility filtering or scoring.

## Why this is the critical path

Ranking quality cannot exceed universe quality. Raw industry and product taxonomies
mix establishments, products, tasks, residual buckets, and operating models. Turbo's
core upstream product is a transparent split/merge/dedupe/add/exclude ledger that
turns those lists into comparable acquisition markets.

## Acceptance criteria

- [ ] Every one of 1,012 NAICS leaves and 6,290 NAPCS rows has an explicit mapping,
      split input, merge input, new-market proposal, or exclusion outcome.
- [ ] All 978 prior-model markets are accepted, changed, merged, split, or rejected
      with reasons; none is silently treated as truth.
- [ ] Canonical market identities apply buyer, job, delivery, workforce, economics,
      acquisition-universe, and Ambient AI workflow tests.
- [ ] Every decision is append-only, versioned, and linked to source rows.
- [ ] Residual “other” buckets and possible coverage gaps receive dedicated review.
- [ ] Independent review audits duplicate, missing, over-broad, and over-specific nodes.
- [ ] README and detailed universe-method documentation report exact reconciliation
      counts, limitations, and reproducible commands.
- [ ] Local replay and full tests pass at the exact reviewed head.

## Boundaries

- Similarity matches are proposals, not automatic canonical decisions.
- SUSB/QCEW enrichment follows market identity and informs size/eligibility.
- No company discovery or evaluation is authorized.

