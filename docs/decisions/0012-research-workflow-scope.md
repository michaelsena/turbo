# ADR 0012: Distinguish pilot, scaled universe, and ranking workflows

## Status

The chairman explicitly confirmed that Issue 15's later selective-verification batch
plan governs universe construction. [Issue 39](https://github.com/michaelsena/turbo/issues/39)
implements that plan. This clarification is not a new ranking policy or evidence that
all planned execution and closure stages have passed acceptance.

## Decision map

| Scope | Governing flow | Source |
| --- | --- | --- |
| Executed first universe pilot | Two concurrent blind specialists, mandatory adjudicator, independent activation review, deterministic activation | Issue 12; ADRs 0005–0006 |
| Scaled universe construction | Batch primary; selective independent verification; conditional blind escalation and disagreement adjudication; mandatory independent release review; deterministic family closure and cumulative publication | Issue 15, reaffirmed by the chairman; implementation in Issue 39 |
| Later market evaluation/ranking | Two independent evaluators; average close answers using registered tolerance; adjudicate material disagreement; submodel-owned pairwise comparators; weighted global aggregation | `docs/scoring/model.md`; Issue 4 |

For scaled construction, graph-moving proposals, weak-confidence cases, conflicts,
and a preregistered QA sample receive independent verification. Material ambiguity
can escalate to two blind specialists; independently valid material disagreement
requires adjudication. Agreement does not create a universal adjudication requirement.
Independent review of exact planned graph movements remains mandatory before release;
zero-proposal outcomes still require complete supported dispositions and approved
no-movement review. Batch packing preserves separate family lineage and coverage.

## Scope corrections

ADR 0001's broad bootstrap phrase "mandatory adjudication" does not replace these
more specific protocols. ADR 0002 supersedes bootstrap source-category scoring timing;
ADR 0004 separates universe identity, Target eligibility, and evaluations. The pilot's
successful topology is evidence about that pilot, not authority to impose its call
pattern on every scaled batch or ranking comparison.

The six manually authored exploratory hypotheses remain provisional drafts, not
completed accepted research or substitutes for required verification/review. Preserve
their provenance and judge them through the governing scaled workflow. Historical
receipts and original pilot results remain unchanged.
