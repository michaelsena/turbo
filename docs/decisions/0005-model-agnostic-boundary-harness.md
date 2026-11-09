# ADR 0005: Model-agnostic boundary harness

## Status

Accepted for the Issue #12 pilot. Model assignments remain provisional.

## Decision

Turbo separates the semantic decision topology from the model used to execute each
role. A bounded operating-family review uses two blind specialists on one frozen
evidence pack followed by one mandatory adjudicator. Deterministic code compiles and
hashes the pack, validates every structured result, assigns durable event identities,
and controls activation. Models may propose; they may not write Market Graph events.

Every required source identity and retrieved prior-candidate hypothesis receives a
current disposition. Thin evidence becomes an explicit lower-confidence inference or
assumption with a retry gap. The adjudicator cannot ignore a specialist or invent a
new evidence source because its input and citations are closed against exact hashes.

Only final structured JSON and execution receipts are durable. Private reasoning
streams are not evidence and are not committed.

## Rationale

General model reputation does not establish fitness for Turbo's boundary task. The
stable harness makes model choice measurable on identical cases while preserving
lineage and allowing specialists and adjudicators to use different models. It also
prevents a model upgrade from silently changing the data contract or accepted graph.

## Model-selection consequence

The first end-to-end run uses a strong provisional baseline. Production selection
follows role-specific frozen-case evaluation of boundary correctness, evidence
grounding, schema and ID reliability, repeatability, disagreement quality, latency,
and cost. Model configuration is versioned and periodically rebenchmarked.

The provider decision is recorded separately in
[ADR 0006](0006-openrouter-model-provider.md). OpenRouter broadens model access but
does not replace explicit per-role model assignments or local output validation.

## Activation consequence

A valid adjudication is not an accepted universe decision. Deterministic event
compilation, local replay, and independent exact-head review remain mandatory before
activation.
