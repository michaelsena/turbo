# Local operating runbook

## GitHub operating model

GitHub is the durable work ledger.

1. Open an issue with scope, acceptance criteria, boundaries, and dependencies.
2. Create a branch named `codex/<issue>-<short-name>`.
3. Post material discoveries and decisions as issue comments.
4. Keep code, docs, generated results, and issue state synchronized.
5. Open a pull request referencing the issue.
6. Obtain independent review for material research or scoring changes.
7. Run all validation and tests locally at the exact PR head.
8. Post the commands, results, hashes, and commit in the PR.
9. Merge only after acceptance; never bypass branch protection.

For larger features, use a feature integration branch. Issue branches merge into
that branch through reviewed PRs; the integrated collection receives a full local
replay and independent review; then one feature PR merges the coherent result to
`main`. `main` must always be the clearest usable product state.

No GitHub Actions or hosted CI is configured. This is an explicit cost-control choice.

## AI-first and publication-ready operation

Agents operate from machine-readable schemas, explicit queues, bounded issue scope,
and deterministic acceptance commands. They must write durable discoveries back to
GitHub records rather than depend on chat memory. Failures create events and retryable
work; they do not silently erase provisional results. Authority boundaries and
Chairman gates remain explicit.

Every important object has two views derived from the same truth:

- a concise human explanation suitable for an investor, interviewer, or public reader
- a machine-readable record with definitions, provenance, confidence, version, and hash

Public explanations may simplify language but may not introduce a second source of
truth. Private or unsupported evidence must never leak into publication artifacts.

## Local verification

For metered model runs, create an ignored local `.env` from `.env.example` and place
the dedicated Turbo OpenRouter key there. Never paste the key into GitHub, a prompt,
or a committed configuration file.

```bash
cp .env.example .env
# Edit .env locally, then load it only into the current shell.
set -a
source .env
set +a
turbo boundary-run
turbo boundary-validate-run data/agent_runs/<boundary-run-id>
turbo boundary-review config/universe/reviews/<review-config>.json
```

`boundary-run` makes two concurrent specialist calls and, only after both validate,
one adjudicator call. It is intentionally explicit and metered; validators and tests
never call OpenRouter. Model slugs are versioned in the family execution config. A
role whose structured output fails local validation may use the configured bounded
correction loop, so one boundary run can make more than three paid calls; inspect the
per-call receipts and remaining key limit after a run.

```bash
PYTHONPATH=src python3 -m turbo.cli validate
PYTHONPATH=src python3 -m turbo.cli run
PYTHONPATH=src python3 -m turbo.cli context
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Before accepting a material run, verify:

- immutable input hashes match their manifests
- source and canonical identities are unique
- every parent and directed edge resolves
- every in-scope market-factor cell is numeric
- exclusions have explicit reasons
- low-confidence scores expose active gaps
- rerunning produces the same substantive projection
- README and relevant detailed docs are current
- exact Git commit and output hashes are recorded

Before a metered run, also verify that `OPENROUTER_API_KEY` is present without
printing it, the configured provider/model slugs are expected, and the dedicated key
limit is sufficient. Receipts may record provider/model/cost metadata but never the
credential or raw private reasoning.

Independent-review runs create their run directory and a sanitized
`review.receipt.json` before sending the metered request. The receipt begins as
`in_progress` and is replaced in place with `valid`, `invalid`, or `failed` after
the attempt. A killed process therefore leaves an inspectable interrupted-run
receipt instead of an untraceable gap. Receipts contain hashes and provider
metadata, never the credential, raw private reasoning, or unsanitized exception
text. Diagnose an interrupted, invalid, or failed receipt before authorizing a
new metered attempt.

Replay a completed review against its exact preregistered configuration and frozen
boundary run before accepting its conclusion:

```bash
turbo boundary-validate-review <review-directory> <review-config> \
  --config <boundary-family-config>
```

The replay fails if the structured review, receipt hashes, requested model, target
envelope, validation status, or credential/reasoning persistence flags differ.

## Agent coordination

The GM/PM owns decomposition and integration. Parallel agents receive non-overlapping
issues or review scopes. Each returns evidence, files changed, local test results, and
open risks. One agent's output is not accepted merely because another agent produced
it; integration and independent review remain explicit.

