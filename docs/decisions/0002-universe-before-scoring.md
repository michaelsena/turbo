# ADR 0002: Complete the market universe before real-market scoring

- Status: accepted
- Date: 2026-11-08
- Supersedes: the bootstrap scoring-timing portions of ADR 0001

## Decision

Turbo will not score or rank real source categories. It will first:

1. preserve the complete identity-source stack;
2. publish a reviewed canonical American Market Universe;
3. apply explicit strategy and size gates to create the Target Market Universe; and
4. research and score every target market.

If evidence research cannot close a factor field, Turbo will then use a documented
inference or assumption with lower confidence and an active retry gap. Inference is a
last-mile completion policy for researched market-factor fields, not a substitute for
constructing the market universe.

## Why

NAICS industries, NAPCS products, tasks, survey controls, residual categories, and
prior-model labels are different objects. Title-based estimates would create a
numerically complete ranking before the things being ranked had defensible identities.
That output would look more mature than the underlying evidence.

## Consequences

- Bootstrap output is useful immediately as a complete reconciliation worklist.
- Zero canonical markets, target markets, and research scores is an honest early state.
- Canonicalization and Target Market filtering are the critical path.
- Synthetic fixtures may test scoring mechanics, but cannot rank real source rows.
- Historical proxy-score runs remain immutable and explicitly superseded.
