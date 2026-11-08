# Build the canonical multi-source American Market Universe

## Outcome

Reconcile authoritative U.S. industry/product sources and the prior 978-market seed
into a versioned set of canonical operating markets before downstream eligibility
filtering or scoring.

## Why this is the critical path

Ranking quality cannot exceed universe quality. Raw industry and product taxonomies
mix establishments, products, tasks, residual buckets, and operating models. Turbo's
core upstream product is a transparent split/merge/dedupe/add/exclude ledger that
turns those inputs into comparable acquisition markets without confusing a source
label with market truth.

## Three separate universes

1. Complete source universe: every immutable input row and typed disposition.
2. Canonical American Market Universe: every reviewed operating market, including
   unattractive and strategy-ineligible markets.
3. Target Market Universe: the later strategy and size filter.

## Work packages

- #7: ingest the official identity-source stack.
- #6: implement stable graph identities and append-only event contracts.
- #5: build the semantic-preserving review candidate engine.
- Run operating-family review batches, cross-family conflict audit, and final
  graph-version publication.

## Acceptance criteria

- [ ] Every source row retains raw semantics, hierarchy, locator, role, and immutable
      snapshot lineage.
- [ ] No exact or fuzzy label match can create an accepted canonical mapping.
- [ ] Top-k candidates retain component signals, margins, semantic contradictions,
      residual flags, and unresolved ambiguity.
- [ ] Every one of 1,012 NAICS leaves and 6,290 NAPCS rows has a typed mapping,
      split/merge input, new-market proposal, non-market, residual, or exclusion outcome.
- [ ] All 978 prior-model markets are accepted, changed, merged, split, or rejected
      with reasons; none is silently treated as truth.
- [ ] Canonical market identities apply buyer, job, delivery, workforce, economics,
      acquisition-universe, and Ambient AI workflow tests.
- [ ] Stable opaque market IDs do not depend on labels, source codes, or list order.
- [ ] Every decision is append-only, versioned, linked to source rows, and replayable
      at an explicit cutoff.
- [ ] Residual “other” buckets and possible coverage gaps receive dedicated review.
- [ ] Independent review audits duplicates, missing markets, incompatible mappings,
      hierarchy cycles, task-level false markets, and broad/narrow boundary errors.
- [ ] README and detailed universe-method documentation report exact reconciliation
      counts, limitations, and reproducible commands.
- [ ] Local replay and full tests pass at the exact reviewed head.

## Boundaries

- Similarity is retrieval, not evidence of equivalence.
- NAPCS products usually attach through product-sold-by-market; NAICS categories
  usually attach through industry-containing-market.
- SUSB/QCEW enrichment follows market identity and informs size/eligibility.
- No attractiveness ranking begins before the Target Market Universe exists.
- No company discovery or evaluation is authorized.

