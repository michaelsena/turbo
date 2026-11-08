# Implement specialist pairwise comparators within each submodel

## Outcome

Calibrate market ordering inside each research submodel using a comparator specialized
in that submodel's factors, while keeping the global ranking a transparent weighted
aggregation of submodel data.

## Acceptance criteria

- [ ] Every submodel defines its own comparator identity, rubric, and pair queue.
- [ ] Close-neighbor selection tests fine ordering; sampled far-neighbor selection
      tests scale and anchor consistency.
- [ ] Comparison is blind to unrelated submodel scores and global rank where possible.
- [ ] A comparison can affect only the owning submodel's score.
- [ ] Every event records pair, selection reason, evidence cutoff, factor analysis,
      outcome, confidence, score delta, and model/prompt/config versions.
- [ ] Cycles and inconsistent pairwise preferences create calibration/research gaps.
- [ ] Global output is limited to versioned weighting, aggregation, contribution,
      sensitivity, uncertainty, and rank-stability analysis.
- [ ] Local replay and tests reproduce all accepted comparison effects.

## Dependencies

Canonical Market Universe and production submodel score contracts.

