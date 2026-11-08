# Turbo operating protocol

Turbo is a research system, not a prose report. Durable evidence, scores, and
decisions must be replayable from version-controlled inputs.

## Before material research

1. Validate the repository with `python3 -m turbo.cli validate`.
2. Compile the narrowest relevant as-of view with `python3 -m turbo.cli context`.
3. State which market, factor, source snapshot, or open evidence gap the work extends.
4. Pre-register the research question and the condition that would change a score.

## Evidence and scoring boundaries

- Keep sources, observations, claims, scores, decisions, lessons, and questions distinct.
- Label reasoning as `fact`, `inference`, `assumption`, or `unknown`.
- Preserve source files as immutable snapshots with URL, retrieval time, and SHA-256.
- Never silently mutate a prior conclusion. Add a new version with a directed
  `supersedes` or `contradicts` edge.
- Every market-factor intersection must have a score. When evidence is weak, use a
  documented inference or assumption with low confidence rather than a blank cell.
- Retain open evidence gaps and retry them according to expected ranking impact.
- Distinguish raw score, confidence, evidence quality, downside penalty, and
  risk-adjusted score.
- Independent evaluators must not share one another's answer before scoring.
- If evaluators materially disagree, adjudication must produce a provisional score,
  explain the disagreement, and optionally request more research. A research gap may
  remain open; the current score may not be null.
- No paid sources, outreach, confidential data, personal data, or external
  representation without an explicit governance change.

## Market identity

- NAICS nodes are source categories, not automatically canonical operating markets.
- A canonical market should share buyer, job-to-be-done, delivery model, workforce,
  economics, acquisition universe, and Ambient AI workflow.
- Split a market when economics, buyability, risk, or AI transformability differs
  materially. Merge only when operating identity and evidence support equivalence.
- Preserve every source-to-market mapping and split/merge decision in the market graph.

## Documentation is part of the product

- Keep `README.md` current as the executive one-page-plus guide to purpose, design,
  operation, current results, and navigation.
- Update the relevant file under `docs/` with every material architecture, universe,
  scoring, governance, or operating change.
- Add an architecture decision record for consequential design choices.
- A code change that alters behavior without updating its documentation is incomplete.

## Closeout

1. Run the narrowest focused tests, then `python3 -m unittest discover -s tests -v`.
2. Run `python3 -m turbo.cli validate` and replay the relevant pipeline.
3. Inspect the full-field rerender, including exclusions, low-confidence scores, and gaps.
4. Record exact input hashes, output hashes, UTC time, and Git commit when available.
5. Obtain independent review for material scoring or research changes.
6. Commit and push small audited increments. Never bypass protected checks.

