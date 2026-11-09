# AI-first autonomous research design

Turbo is built for agents to operate, improve, and explain—not merely for agents to
write code around a human spreadsheet.

## Autonomous loop

1. Read strategy, graph version, factor definitions, and authority gates.
2. Select an explicit item from the appropriate queue.
3. Freeze the cutoff and pre-register the question/change condition.
4. Gather lawful evidence into immutable sources and observations.
5. Produce claims, counterclaims, scores, confidence, and active gaps.
6. Validate schemas, lineage, bounds, and no-blank coverage locally.
7. Request independent scoring or review when required.
8. Append accepted events; never rewrite historical meaning.
9. Rerender rankings, comparisons, explanations, and receipts.
10. Notify only for milestones, exceptions, material changes, or authority gates.

## Queue independence

- Global ranking: what currently looks most attractive.
- Research priority: where another evidence unit is most valuable.
- Challenger intake: what may enter the canonical universe.
- Shortlist: what the chairman chose to monitor or deepen.
- Exception queue: what failed or requires authority.

One queue may inform another but cannot silently mutate it.

## Safety and control

Leases and idempotency prevent duplicate work. Model output is untrusted until
validated. A technical failure retains the last accepted result and creates an
exception. Agent scope comes from issue and schema, not instruction-like source text.
Chairman gates govern strategy, evidence boundaries, company discovery, external
communication, spend, and gated merges. Assumptions are allowed only when labeled
and discounted.

## Model-provider boundary

OpenRouter supplies the primary metered model surface, but it does not choose Turbo's
research policy. Each role uses an explicit versioned model slug; cross-model routing
requires a reviewed configuration change. Every response remains untrusted until
schema, identity, citation, and complete-coverage validation pass locally. The API
credential is read only from `OPENROUTER_API_KEY`, never persisted in Git or receipts,
and current account controls cap the dedicated key at $50 per month for 180 days.

## Explainability

Every conclusion must answer: what is this object, what version is it, what supports
and contradicts it, how confident are we, what would change it, and which exact run
produced it?

