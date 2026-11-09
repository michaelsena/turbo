# Scoring model

## Mature topology

Turbo will use six submodels so the global score does not depend excessively on one
conceptual axis:

1. Demand and Market Attractiveness
2. LMM Buyability and Roll-Up Potential
3. Base-Business Quality and Cash Economics
4. Operating Scalability and Integration
5. Ambient-AI Workflow Transformability
6. Ownership Value Capture and Risk

The previous model's twelve criteria remain useful anchors: durable demand, quality
of earnings, acquisition pricing, target availability, competitive opening,
resilience to displacement, increase in completed work, accumulated-context
dependence, implementation feasibility, distinctiveness, retained economic value,
and reuse across acquisitions. Turbo redistributes and expands them rather than
discarding them.

## No-blank rule

Every market-factor pair must resolve to a numeric score. Evidence quality affects
confidence. When direct evidence is missing, the evaluator may use a documented
analogue, inference, or assumption. It must state why the proxy applies and what
evidence would change the result.

## Evaluation protocol

This is the later market-factor scoring protocol, not the universe-construction
pilot or scaled batch review flow. See
[ADR 0012](../decisions/0012-research-workflow-scope.md) for the scope distinction.

1. Freeze market definition, factor version, evidence cutoff, and scoring anchors.
2. Give the same evidence pack independently to two specialists.
3. Record raw answer, rationale, evidence links, counterevidence, and confidence.
4. Average close answers according to the registered tolerance.
5. Send material disagreement to a third adjudicator.
6. The adjudicator must issue a provisional score, explain the resolution, and may
   create high-priority research questions.
7. Aggregate factor scores using versioned weights.
8. Adjust for evidence confidence and explicit downside.
9. Within the submodel, its specialist comparator compares close and selected far
   neighbors to detect fine-ordering errors, scale drift, or inconsistent anchors.
10. Record pair selection, evidence cutoff, result, score effect, confidence, and
    rationale as a versioned comparison event.

## Pairwise comparison boundary

Each of the six submodels owns a comparator specialized in its topics and factors.
The comparator may refine only that submodel's resolved score. Close neighbors test
small ranking differences; deliberately sampled far neighbors test whether anchors
remain globally coherent within the domain.

There is no global generalist comparator. The global layer combines submodel scores
using versioned weights and exposes raw, confidence-adjusted, and downside-adjusted
rankings. It performs sensitivity, contribution, and rank-stability analysis and may
request deeper research, but it cannot invent a qualitative override to the weighted
data.

## Current implementation status

V1 performs no real-market scoring. It constructs and reconciles the starting source
lists. Production factor research begins only after canonical operating markets are
reviewed and filtered into the Target Market Universe. Synthetic fixtures may later
test scoring mechanics, but they must never rank real source categories or appear as
research results.

## Research-gap priority

The planned priority signal is proportional to:

`ranking sensitivity × uncertainty × probability of finding evidence ÷ research cost`

The formula will be calibrated against observed score movement and research yield.

