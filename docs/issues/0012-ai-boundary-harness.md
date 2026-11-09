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

The parser gate, pack compiler, schemas, closed-world validator, isolated runner,
independent review, deterministic activation compiler, and replay tests are
implemented. Three market versions are now activated from the approved pilot; Target
Market admission, company work, and attractiveness scoring have not begun.

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

A tiny same-model structured-output diagnostic then succeeded through Claude
Platform on AWS: one choice, exact `{"ok":true}` content, 226 total tokens, and
`$0.001048` cost. This isolated the problem to the large review request path rather
than model naming or JSON Schema support. A final full request at exact head
`5558d0052e4989d3e2f18279e0b0f299f65a5d4f` again returned HTTP 200 with no choice
after 725,773 ms. Its generation ID is
`gen-1794188091-Gaiev23k5J2UYESwr379`; it reported no served model, provider, token
usage, or cost. The durable failed receipt is
`independent-review-3bcfd22da5c9b201574a/review.receipt.json`. The account usage
rose only by the `$0.001048` diagnostic cost, to `$3.539260`, confirming that neither
failed full request was billed. The Claude full-packet route is retired for this
review; it will not be retried again without a separately documented method change.

The successor review configuration is
`config/universe/reviews/office-administrative-services-v1-boundary-review-gemini.json`.
It binds the same run, pack, adjudication, questions, and activation rule, but names
`google/gemini-4-argon` as the reviewer. At selection time, OpenRouter reported a
1,048,576-token context, structured-output and high-reasoning support, at least one
healthy Google endpoint, and sufficient completion capacity. This is an explicit
successor attempt, not a mutation of the failed Claude preregistration.

### Independent review result

At exact head `26d76dbdc72500f1733340a9b747a75b7da0f209`, successor run
`independent-review-e6058823bd1c604ffb36` completed through Google on
`google/gemini-4-argon`. The local closed-world validator accepted the review with
zero validation errors, and the new replay command reproduces the exact result.
Canonical review output SHA-256 is
`fe47954a90aa3d1ee0217c55d802e1df41e4fc4933c126cdc0611326a17f51ea`.
The call ran from `2026-11-09T01:52:04Z` to `2026-11-09T01:57:51Z`, reported
355,668 total tokens, and cost `$0.946912`.
After the run, the dedicated key reported cumulative usage of `$4.486172` and
`$45.513828` remaining under its `$50` cap.

The verdict is **request changes**, not activation: one P0, two P1, and two P2
findings. All five registered checks failed. The material conclusions are:

- the 127 `reject` dispositions are not explicitly family-local and could be
  misread as global deletion of valid prior seeds;
- lexical retrieval missed directly relevant catalog seeds, including the existing
  horizontal office-administration seed plus medical and dental practice
  administration, so the new proposal could duplicate or overlap them;
- all 13 official NAICS 561110 manual-index entries were omitted, concealing
  medical, dental, hotel, and motel management scope conflicts;
- an empty research-gap list is unjustified while the horizontal-versus-vertical
  boundary, Ambient AI workflow, economics, workforce, acquisition universe, and
  product revenue mix remain unknown or inferred; and
- NAPCS dispositions need fuller identity/prevalence evidence, one staffing judgment
  is mislabeled as fact, and explicit farm-management and holding-company exclusions
  are missing.

Activation conditions require family-local candidate semantics, direct reconciliation
of the missed prior seeds, treatment of all 13 index entries, explicit research gaps,
stronger NAPCS citations, corrected evidence labels, and complete exclusions. No
Market Graph event was created; accepted canonical markets remain zero.

### Correction-cycle preregistration

The correction cycle is versioned as
`config/universe/families/office-administrative-services-v2.json`; the reviewed V1
config, pack, outputs, and review remain immutable. Its deterministic pack has SHA-256
`eccc87570dc259f3cea6449a5a87455ccba4e690ccb82851e28822c3a64346e5`, 550 evidence
items, 66 required source identities, and 130 required prior-candidate dispositions.
It adds explicit required-anchor evidence for the missed horizontal office
administration, medical practice administration, and dental practice administration
seeds while retaining the previously retrieved hotel-administration seed.

Versioned V2 specialist and adjudicator prompts require every `reject` rationale to
state family-local non-mapping semantics, every required prior seed to be reconciled,
all seed manual-index entries to be audited, weak dimensions and unresolved splits to
create research gaps, each NAPCS disposition to cite interpretation evidence beyond a
product link, and direct manual cross-reference exclusions to be preserved. These are
completion-contract changes for a new run, not edits to the reviewed V1 result.

### Correction proposal run

At exact head `7991201b187729aecc0c80d2a43050c43dfedb34`, V2 run
`boundary-run-1a88e9a3acdf15d63b09` completed with three first-pass calls and no
validation repairs. All outputs contain 66 identity and 130 candidate dispositions.
The adjudicator output SHA-256 is
`c560ac7d565f163eee92a4ee839a38e6322258352f1170555085b90b87d87e73`.

The new adjudication proposes three linked operating-market inputs:

- **Integrated outsourced office administration**, adopting the existing horizontal
  prior seed and provisionally retaining the hotel-administration seed as a merge
  input;
- **Medical practice administration**, bound to the missed medical prior seed; and
- **Dental practice administration**, bound to the missed dental prior seed.

All 126 remaining `reject` rationales explicitly state family-local non-mapping
semantics. The output now preserves two active gaps: horizontal buyer/contracting/
economics/workforce/acquisition/AI evidence, and the horizontal-versus-named-vertical
boundary. It also includes the manual farm-management and holding-company exclusions.

The three calls reported 737,944 total tokens and `$2.6181175` cost. Dedicated-key
cumulative usage is `$7.1042895`, with `$42.8957105` remaining. This is still a
`validated_proposal_not_activated`; an independent successor review must test every
original activation condition before any graph event can be considered.

The successor activation audit is preregistered in
`config/universe/reviews/office-administrative-services-v2-boundary-review-gemini.json`.
It binds the exact V2 run, pack, and adjudication hashes and asks Gemini 4 Argon to
re-test family-local semantics, seed reconciliation, all 13 index entries, explicit
exclusions, preserved gaps, NAPCS evidence sufficiency, and evidence-label accuracy.
Approval still requires all five registered checks to pass with zero findings; the
review cannot activate the graph directly.

### Correction review result

At exact head `e1f7592a0662610eec2d0309fd0cf0c160309702`, independent run
`independent-review-b95c0d39bef8bffa9c00` completed through Google on
`google/gemini-4-argon`. The verdict is **approve activation** with all five checks
passing and zero P0/P1/P2 findings. Output SHA-256 is
`3f0b3e668e2f5050fc2a3afb0d10c6b2b869b81e604c786668ff3f6d497e3c43`.
The call ran from `2026-11-09T02:24:57Z` to `2026-11-09T02:29:06Z`, reported
372,620 total tokens, and cost `$0.907288`. Dedicated-key cumulative usage is
`$8.0115775`, with `$41.9884225` remaining.

The review confirms that all candidates are reconciled with family-local rejection
semantics, the horizontal and provisional vertical seeds do not create unsupported
duplicates, all 13 index entries and 10 manual exclusions are substantively covered,
all 65 NAPCS identities have paired identity/relationship evidence, and the two gaps
correctly preserve uncertainty. Its continuing activation conditions are contractual:
medical and dental proposals plus the NAICS mapping remain provisional until the
vertical-boundary gap is resolved; rejected seeds remain globally intact; and the
horizontal operating-model gap remains open for later enrichment.

At that stage, the review authorized a separate deterministic graph-activation
increment. The review itself did not create graph events, apply the Target Market
filter, score markets, or start company work.

### Deterministic activation result

Activation was preregistered in
`config/universe/activations/office-administrative-services-v2.json`, binding the
exact V2 family config, run, pack, adjudication, independent review, zero-finding
rule, three proposals, one identity mapping, statuses, and both gaps. The config
explicitly prohibits model calls, Target filtering, scoring, company work, and global
candidate rejection.

At exact compiler head `243fbc385cad66e5bc6cbbcbd511b8a47397dc6f`, activation
`boundary-activation-9d3772f0364b4632dc62` deterministically emitted:

- three `create_market` events;
- one provisional `broader_than_market` mapping from NAICS `561110` to the horizontal
  market; and
- zero `reject_candidate` events.

The stable market IDs are:

- `market:930fb681a7db796a46677c8c` — Integrated outsourced office administration,
  `accepted_with_open_gaps`;
- `market:a4e5f08d253256b2a0c8ca05` — Medical practice administration,
  `provisional`; and
- `market:8230a0616ef5332c9c156ed2` — Dental practice administration,
  `provisional`.

Both `gap:horizontal-office-admin-operating-tests` and
`gap:vertical-administration-boundary` remain active. The 126 family-local candidate
non-mappings remain globally intact. The projection is
`graph-1287641f7c96ef367b8cba4d`; canonical event hash is
`3e9c3f4f09c8f5ada2301fcfd9a8e04d18e8ba509afcfb2db5cb22ccacc22d51`
and canonical projection hash is
`5341b24b07e24dc40130affeefe7d5c8937abc9c69bab0f6589e5c4bfcae3646`.
Exact replay returns zero errors and requires no model or network call.

This completes one operating-family activation, not the American Market Universe.
No Target Market filtering, attractiveness evaluation, ranking, shortlist, or company
work is implied.

### First exact-head activation audit

An independent read-only audit of exact pushed head
`c79241150d12d13d97cddd2bb381300087394301` found zero P0, one P1, and two P2 issues.
The graph events, statuses, gaps, hashes, and research boundaries were correct. The P1
was a provenance hardening gap: the activation command recorded `git rev-parse HEAD`
without refusing a dirty worktree, so a future dirty execution could be attributed to
code not actually present in that commit. The P2s were an obsolete V1 replay example
in the README and stale GitHub Issue/PR summary metadata.

The correction makes activation fail unless the worktree is clean, requires a full
lowercase hexadecimal execution hash, verifies that receipt commit resolves during
replay, adds regression tests, points the README at the approved V2 review, and updates
the GitHub summaries before closeout. This hardens future provenance; it does not
rewrite the already activated events or change any market conclusion.
