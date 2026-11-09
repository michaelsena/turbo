# Issue #12: AI boundary harness and first pilot family

## Purpose

Build the first executable semantic boundary-review lane without mixing universe
construction, Target Market filtering, or attractiveness evaluation.

The neutral pilot is NAICS `561110`, Office Administrative Services. It was selected
to test overlapping activities, product evidence, exclusions, and weakly supported
operating dimensions—not because it is attractive.

## Pre-registered question

What is the smallest defensible set of canonical operating markets required to
dispose the seed and all directly observed product identities when buyer, job,
delivery, workforce, economics/risk, acquisition universe, and Ambient AI workflow
are kept distinct?

The condition for changing a boundary is explicit evidence that identities differ or
cohere on one or more of those operating dimensions. Label similarity and product
co-occurrence alone cannot decide the result.

## Upstream correction gate

Before any model ran, the pilot exposed a small bold PDF heading-decoration glyph in
445 Manual cross-reference blocks. The parser now excludes only the exact decoration
signature. The pilot definition ends at the real cross-reference sentence, `5612` is
correctly title-only, and the full disposition becomes 1,571 substantive, 522
delegated, and 32 title-only records. The correction produced immutable universe run
`run-2ea0f00db84148de663f` and is covered by focused regression tests.

## Frozen pilot surface

- 66 required-disposition identities: one NAICS seed plus 65 direct products
- 65 industry-product relationships and 121 source observations
- 38 collection workbook rows and 27 relationship-only identities
- 55 collection/trilateral relationships and 110 source observations
- 47 linked trilateral products and 149 hierarchy nodes including ancestors
- one explicit no-mapping record and nine products absent from the concordance
- one Manual definition, 13 Manual index entries, and one vintage-lineage pair
- 66 deterministic reconciliation work items and 127 retrieved prior candidates
- the complete lightweight 978-candidate prior catalog
- 547 stable citable evidence items
- canonical pack SHA-256
  `32634f119b454bbae964cab7ed1c40a2f5eb09285fa3c254191422246f33bbed`

Cross-industry product prevalence ranges from 3 to 682 relationships with a median of
20. This is count-only context; it does not establish revenue share, importance,
exclusivity, or a core workflow.

## Execution contract

1. Compile from hash-verified immutable run artifacts; never rerun a parser inside the
   model lane.
2. Run two specialists concurrently in separate ephemeral read-only sessions.
3. Require strict schema output and complete closed-world identity/candidate coverage.
4. Reject invented evidence, candidates, proposals, gaps, or mismatched pack hashes.
5. Run the adjudicator only after both blind specialist results validate.
6. Bind adjudication to both exact specialist-output hashes.
7. Persist final JSON and receipts, never raw private reasoning streams.
8. Treat adjudication as a proposal until event compilation and independent review.

## Current status

The parser gate, pack compiler, schemas, closed-world validator, isolated runner, and
focused contract tests are implemented. A validated model proposal now exists, but no
canonical market, Target Market admission, company work, or attractiveness score has
yet been accepted.

The original `gpt-6.1-sol` local-CLI baseline was rejected before inference because
that model was not exposed through the local ChatGPT-authenticated Codex CLI. No
output was persisted and the adjudicator did not run. A later `gpt-5.6-terra`
specialist call passed schema preflight but was stopped before completion when the
project adopted OpenRouter as its metered provider layer; its temporary directory was
discarded and no model output entered the repository.

The pilot now requests `openai/gpt-5.6-terra` through OpenRouter for all three roles
as an explicitly provisional baseline. The provider is configuration-driven, so
specialist A, specialist B, and adjudicator may later use different vendors or models
after frozen-case evaluation. Requests require structured-output-capable endpoints,
exclude returned private reasoning, and remain subject to Turbo's own closed-world
validation. This is a provider-access decision, not production model selection.

### Provider-access receipt

Recorded at `2026-11-09T00:28:09Z`, a deliberately tiny structured-output handshake
confirmed the dedicated key and endpoint without running a boundary specialist or
adjudicator. OpenRouter served `openai/gpt-5.6-terra` through OpenAI, returned exactly
`{"ok":true}`, used 53 total tokens, and reported a cost of `$0.000256`. No reasoning
tokens or research evidence were used, no market conclusion was produced, and no
result entered the Market Graph. The live key was never written to this receipt.

The first full pilot attempt at exact head
`5ca991065c0d6c47df330961d765c789aa69565d` failed closed before inference. From
`2026-11-09T00:30:35Z` to `2026-11-09T00:30:38Z`, both configured endpoints rejected
the model-facing schema because constant fields did not include the explicit JSON
types required by their strict-schema subset. No specialist or adjudicator output was
persisted and no graph event changed. The corrective increment adds explicit types to
the canonical schemas, defensively infers them in the provider adapter, and limits
provider-error exceptions to non-personal diagnostic fields plus response hashes.

The retry at exact head `b3227fc` reached inference but failed the local closed-world
gate. One specialist returned only one of 127 required prior-candidate dispositions,
used a candidate ID as a proposal ID, and left a provisional disposition without a
known research-gap ID. The other concurrent call also completed, but the orchestration
did not run the adjudicator or persist either output. At `2026-11-09T00:38:03Z`, the
dedicated key reported cumulative usage of `$1.245852`, including the earlier
`$0.000256` connectivity handshake. No market conclusion or graph event was accepted.

The corrective design makes the frozen completion contract explicit: all 66 required
identity IDs and all 127 prior-candidate IDs must be disposed exactly once, ID domains
are restated, and provisional judgments must bind a known gap. A role may now use at
most two fully receipted correction calls after local validation failures. Corrections
receive validator errors and the prior output hash but must regenerate a complete
object; exhausted correction rounds still fail closed.

### First validated proposal run

At exact execution head `acb4354f77a5bd5ba5e27982545f61d765a303fa`, run
`boundary-run-1d9b04b683a3544c2644` completed with three first-pass model calls and no
correction rounds. Both blind specialists and the adjudicator used
`openai/gpt-5.6-terra`, served by OpenAI through OpenRouter. Each output contains all
66 required identity dispositions and all 127 prior-candidate dispositions.

The adjudicator proposed one operating market, **Integrated outsourced office
administration**, supported directly by the Manual definition and source identity.
It mapped the one NAICS industry identity to that proposal, classified the 65 NAPCS
product identities as non-market source identities, and marked all 127 retrieved
prior candidates `reject` within the bounded family. No research gaps were returned.

Canonical output hashes:

- specialist A: `b7024b0e5471a1723d8db03492fd6bccbb335979e77e487482dfd5319df17166`
- specialist B: `e8255073c1bacd2f13f161c3ce80b46f887c8dab23ca4fcb12b57d3a4f379565`
- adjudication: `270b95ab18257bb24a464f47d3bf0f7ca7d33e7b3b48259ebf5adbb15223d685`

The run used 695,858 total reported tokens and cost `$2.292360`. At
`2026-11-09T00:46:03Z`, the dedicated key reported cumulative usage of `$3.538212`
and `$46.461788` remaining. Raw private reasoning and the API credential were not
persisted.

The persisted replay validates with zero errors against pack
`32634f119b454bbae964cab7ed1c40a2f5eb09285fa3c254191422246f33bbed`.
This is still `validated_proposal_not_activated`. Independent review must determine
whether the zero-gap result is appropriately cautious and whether `reject` means only
“not part of this bounded family” rather than global deletion of unrelated prior
seeds. Until then, no Market Graph event may be compiled.

### Independent review preregistration

The activation review extends immutable run `boundary-run-1d9b04b683a3544c2644`,
pack `32634f119b454bbae964cab7ed1c40a2f5eb09285fa3c254191422246f33bbed`,
and adjudication
`270b95ab18257bb24a464f47d3bf0f7ca7d33e7b3b48259ebf5adbb15223d685`.
Its versioned configuration is
`config/universe/reviews/office-administrative-services-v1-boundary-review.json`.

To avoid self-review, the preregistered reviewer is
`anthropic/claude-opus-5.5`, a different model family that the current OpenRouter
catalog reports as supporting structured output and a one-million-token context. The
review must test boundary evidence, all identity dispositions, zero-gap calibration,
family-local candidate semantics, and activation safety. Approval requires every
registered check to pass with zero P0/P1/P2 findings. A non-approval must state
concrete activation conditions; no review output may directly activate the graph.

The first independent-review process ended without a local result or durable error
receipt. The dedicated key's cumulative usage remained exactly `$3.538212`, so no
completed provider generation was billed. Before retrying, the runner was hardened to
write a sanitized `in_progress` receipt before network execution and to preserve a
`failed` or `invalid` receipt for transport, provider, parse, and local-validation
failures. This makes every later metered attempt auditable even if its process is
interrupted.

At exact head `6bddfa0d0144bbc7a743b3b704351c9f18d1e1bd`, the single
review retry reached OpenRouter once and received HTTP 200, but the provider response
contained no usable choice. The runner failed closed before local review validation,
produced no review output, and activated nothing. The dedicated key again remained at
exactly `$3.538212`, indicating zero billed usage for this failed generation. The
attempt is preserved as
`independent-review-7fd09e54f4c6bf5cf162/review.receipt.json`; because the response
parser exception exposed a missing catch path, its exact completion time and provider
generation metadata were unavailable and are explicitly left unknown. The receipt
records the later failure-observation time instead. A regression test now covers an
HTTP-200 response with an empty choice list.
