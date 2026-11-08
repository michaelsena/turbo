# ADR 0004: Separate universe construction, eligibility, and evaluation

- Status: accepted
- Date: 2026-11-08

## Decision

Turbo will maintain three ordered, separately versioned projections:

1. the canonical American Market Universe;
2. the strategy-specific Target Market Universe; and
3. market evaluations and rankings.

Universe events decide identity and boundaries. Eligibility events apply hard gates to
canonical market versions. Evaluation events attach research, factor scores,
confidence, pairwise comparisons, and aggregate rankings to eligible market versions.
No event type may silently perform another layer's job.

Deterministic code owns raw preservation, normalization, reference closure, and replay.
AI specialists own semantic boundary proposals and later market judgments. Missing
public evidence does not create a hidden blank in a published complete projection:
the system records its best defensible inference or assumption, reduces confidence,
and keeps an evidence-gap retry active.

## Why

Market existence, strategic eligibility, and investment attractiveness answer
different questions. Combining them would bias the universe toward the current thesis,
make filtered-out markets disappear, and allow score research to rewrite its own unit
of analysis. Separate projections make coverage, selection, and ranking independently
auditable and allow strategy changes without rebuilding market truth.

## Consequences

- An unattractive or out-of-strategy market remains in the canonical universe.
- Passing the Target Market filter does not imply a favorable score.
- Evaluation always references an exact `market_version_id`.
- A boundary problem found during evaluation creates a proposed universe event; it
  cannot mutate the evaluated market or its historical score in place.
- Research queues, eligibility exceptions, scoring gaps, comparator matches, and
  challenger intake remain separate.
- The API and web app must expose the canonical universe, target universe, and ranking
  as distinct views with their own versions and explanations.
