# Initial service-cohort calibration v0.1

The GM adopted this **new baseline for initial bounded calibration only** after
independent review. Execution still requires reviewed, eligible market versions.
The repository specifies six submodels and inherits twelve criteria, but does not supply previously agreed numeric weights,
anchors, tolerance or adjustment parameters. No model call or score is authorized
by these configuration files.

The [calibration manifest](../../config/evaluation/calibration/service-cohort-v0.1/calibration-manifest.json)
binds all six factor artifacts and records the exact runtime contract used for
validation. Each factor contains specific anchors at 0, 25, 50, 75 and 100, evidence
expectations, and the exact adopted task model policy. The manifest records the UTC
adoption time, issue decision, reviewed proposal commit and unchanged factor hashes.

| Submodel | Factors, weighted equally within the submodel |
| --- | --- |
| Demand and Market Attractiveness | Durable demand; competitive opening |
| LMM Buyability and Roll-Up Potential | Acquisition pricing; target availability |
| Base-Business Quality and Cash Economics | Quality of earnings; resilience to displacement |
| Operating Scalability and Integration | Implementation feasibility; reuse across acquisitions |
| Ambient-AI Workflow Transformability | Increase in completed work; accumulated-context dependence |
| Ownership Value Capture and Risk | Distinctiveness; retained economic value |

## Bounded calibration policy

| Parameter | Initial calibration setting |
| --- | --- |
| Raw factor scale | 0–100; interpolate against the explicit factor anchors |
| Within-submodel weights | 1 for each of two factors, normalized equally |
| Global submodel weights | 1 for each of six submodels, proposed equal sixths; the current adapter does not publish a global ranking |
| Close-answer resolution | Arithmetic mean when the raw-score difference is at most 10 points |
| Material disagreement | Adjudication when the raw-score difference exceeds 10 points |
| Uncertainty adjustment | Raw × confidence × evidence quality |
| Downside adjustment | Subtract the explicit downside penalty, with scenario and rationale |
| Pairwise comparison | All unordered pairs in the small frozen cohort, within each submodel only |
| Comparison effect | At most ±5 points per market, attributed to comparisons; zero with a single market |

Confidence and evidence quality may penalize related uncertainty twice. This is an
explicit conservative starting policy, not a calibrated economic forecast or a
previously agreed model. Always inspect raw scores, confidence and evidence quality
individually alongside adjusted results. Do not charge the same downside again after
it is already reflected in the raw judgment or a hard exclusion. Negative adjusted
results are allowed; do not clip them or interpret them as probabilities.

A midpoint-shrinkage alternative is recorded in the manifest for later review:
`midpoint + confidence × (raw − midpoint) − downside`, reporting evidence quality
separately. That alternative is not selected here and is not supported by the
current runtime. It must not be substituted silently.

## Task model policy and independence

| Task | Model | Reasoning effort |
| --- | --- | --- |
| Evaluator A | `openai/gpt-5.6-terra` | high |
| Evaluator B | `google/gemini-4-argon` | high |
| Conditional adjudicator | `openai/gpt-5.6-terra` | high |
| Submodel comparator | `google/gemini-4-argon` | high |

The runtime requires four distinct actor IDs and exact agreement between these
factor policies and the frozen task configurations. Model reuse for adjudication
and comparison is permitted. Evaluator independence comes from distinct actors and
blind assignments containing the same frozen evidence without the peer's answer;
using different evaluator models is an additional choice in this calibration.

Adoption of these model identifiers does not establish that every route or role is
qualified. Provider routes, current prices, context fit, schemas, prompts, attempt
limits and spending authority require their own preflight before execution.

## Adoption and first run

The [GM decision](https://github.com/michaelsena/turbo/issues/86#issuecomment-6774592466)
adopts the exact six reviewed factor files for this initial service calibration. It
does not approve a production factor catalog, global ranking, or provider spending.
Operators must still prepare work units using published canonical market versions,
provider-backed eligibility, a frozen cutoff, and source/claim/gap evidence.
No assumption that association management or lease administration is accepted or
eligible is embedded in this configuration.

Six submodels require 18 evaluation calls without adjudication or at most 24 with all
adjudications, plus separate eligibility. Freeze a cohort-wide spending ceiling and
per-workunit allocations before execution; a cap for one submodel must not silently
multiply by six. Review real outcomes before treating this calibration as suitable
for broader ranking.

The anchors retain the [prior criteria](../decisions/prior-model-crosswalk.md), the
[scoring protocol](model.md), and the [concrete Ambient-AI implementation requirement](../ambient-ai/thesis.md).
They are bounded calibration judgments about how to score evidence, not evidence
about markets. The original seven excluded-exposure gates remain mandatory, including
union exposure; no waiver or automatic eligibility pass is introduced.
