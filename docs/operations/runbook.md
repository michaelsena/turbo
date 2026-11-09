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

### Read API and React console

Use Python 3.11+ and a Node.js version supported by Vite 7 (20.19+ or 22.12+).
Install Python and locked frontend dependencies, build the client, then run one local
product process. Serving the console never invokes a model or performs network research.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
python3 -m pip install -r requirements-web.txt
cd frontend
npm ci
npm test
npm run typecheck
npm run build
cd ..
PYTHONPATH=src uvicorn turbo.web.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`; inspect OpenAPI at
`http://127.0.0.1:8000/docs`. During frontend development, keep FastAPI on port
8000 and run `npm run dev` in `frontend/`; the Vite server proxies `/api` and remains
only a development tool. Stop both local processes when inspection is complete.

After installing Google Chrome, run `npm run test:visual` from `frontend/`.
The committed Playwright configuration selects the installed `chrome` channel and
starts Python from the repository-local `.venv/bin/python`; an environment elsewhere
does not satisfy that path automatically. This command builds the client, starts a
temporary FastAPI server on
`127.0.0.1:8017`, runs axe WCAG 2 A/AA checks and screenshot comparisons at fixed
desktop/mobile viewports, exercises the historical snapshot selector, and stops the
server. Screenshot rasterization can depend on OS, fonts, and Chrome version; record
those runtime details in the acceptance receipt. Investigate a mismatch before
changing baselines. Use `npm run test:visual:update` only when an intentional reviewed visual
change requires new baselines. Commit the deterministic files under
`frontend/e2e/__screenshots__/`; never commit `test-results` or `playwright-report`.
The route loop explicitly restores `window.scrollY` to zero before axe and viewport
capture. This keeps the separate Overview market-panel element screenshot—which
scrolls its subject into view—from shifting the next route's viewport baseline.

If the test executor cannot bind a server, start the compiled product from a shell
that can bind loopback. From the repository root:

```bash
./scripts/serve-local.sh
# Optional prepared interpreter: TURBO_PYTHON=/absolute/path/to/python ./scripts/serve-local.sh
```

The launcher requires `frontend/dist`, uses `TURBO_PORT` (default 8017), and binds
only `127.0.0.1`. Then run acceptance against that process from `frontend/`:

```bash
TURBO_TEST_BASE_URL=http://127.0.0.1:8017 npm run test:visual
```

`TURBO_TEST_BASE_URL` accepts only an HTTP loopback origin (`127.0.0.1` or `localhost`,
with an optional port); credentials, non-root paths, queries, and fragments are
rejected. In this mode Playwright does not start or stop the server. The person or
process that launched it must stop it after inspection. If the executor also cannot
reach loopback or launch Chrome, run acceptance in the shell that can; record the
actual result rather than marking the gate passed from unit tests alone.

PR #19's corrected browser checks passed on the host on 2026-11-09; see the
[verification receipt](receipts/2026-11-09-dashboard-corrections.json) for exact hashes,
runtime, and the minor Overview badge-clipping follow-up. All 14 screenshots were
reviewed. A plain `--update-snapshots` only updates changed comparisons; tolerance
can preserve stale small text changes. When deliberately refreshing every reviewed
baseline, run `npm run test:visual:update -- --update-snapshots=all`, inspect the
images, then run `npm run test:visual` again. Use the external-server environment
variable for both commands when the server is managed separately.

Before accepting a UI/API change, run the focused Python tests, frontend tests,
TypeScript check, production build, full Python suite, repository validation, and
current-context compile. Record the exact commit and counts in the issue/PR. Do not
commit `node_modules`, `frontend/dist`, `.venv`, or `*.tsbuildinfo`; do commit
`package-lock.json`.

### Batch authorization and ledger inspection (Track B1)

This lane is simulation-only. It does not use the pilot's provider key, dispatch a
live model, or publish a market decision. Start with exact V2 family preparations,
then validate a bounded authorization against those same directories. Preparations
must match the current implementation hashes, belong to one scheduled batch, and
remain in manifest order. A changed compiler requires fresh preparations; never
rewrite the old ones merely to make replay pass:

```bash
PYTHONPATH=src python3 -m turbo.cli batch-dry-run path/to/authorization.json \
  path/to/preparation-1 path/to/preparation-2
PYTHONPATH=src python3 -m turbo.cli batch-status path/to/execution
PYTHONPATH=src python3 -m turbo.cli batch-validate-execution path/to/execution \
  path/to/preparation-1 path/to/preparation-2
```

`batch-dry-run` validates scope and limits without dispatch. `batch-status` inspects
and replays an existing journal without changing it. `batch-validate-execution` also
checks the exact preparation inputs. None creates a live model call, and there is no
new `batch-execute` CLI command in Track B1. Fake execution is exercised by the Python
library and focused tests.

The authorization must use `mode: simulation_only`, `provider: simulation`, and
`role: batch_primary`, and `budget_scope: single_journal_simulation`. It binds 2–8 exact family preparations, the batch ID, model and
prompt hash, both execution-schema hashes, integer token-price assumptions and their hash, UTC validity interval,
maximum input/output tokens, total microdollar/call caps, combined retry/repair
allowance, concurrency, and lease duration. Times must end in `Z`; authorization is
valid at its start and invalid at its expiry. Set `max_concurrency` to 1; B1 rejects
2. It supports one initial batch-primary request and a linear retry/repair chain, not concurrent independent tasks.
An authorization file does not itself authorize a real provider or future canary.

Budget and idempotency checks cover one trusted journal only. Copying the same
authorization into another execution directory starts separate counters; it does not
share or enforce a global budget. Do not use B1 as production spend authority. A
shared spent-authorization registry or deterministic governed execution namespace
is a blocking requirement before any live adapter or paid canary.

Before retrying interrupted work, inspect the journal. A dispatched attempt with an
unknown outcome retains its full reservation; lease expiry does not prove that no
work occurred. Do not remove the journal, invent a zero-cost settlement, or create
a new attempt to bypass that reservation. Deterministic replay must explain the
confirmed cost and every outstanding reservation. A reservation expired before
its dispatch can release funds, but does not restore its consumed call allowance.
A subsequent attempt references a failed, settled predecessor or a safely released
undispatched predecessor through `retry_of`. It uses a fresh request ID and consumes
both a call and the shared `max_retries` allowance; the chain cannot fork. Provider
reconciliation, real output validation, and reviewed family closure remain later work.

See [Issue 15](../issues/0015-batch-native-family-research.md),
[the contracts](../architecture/data-contracts.md#batch-authorization-and-execution-journal),
and [ADR 0008](../decisions/0008-batch-authorization-execution-ledger.md). Record the
exact code/input hashes and local test results in GitHub before accepting this lane;
fake-transport tests must not be reported as a metered research run.

### Managed local registry (Track B2)

Choose one trusted registry directory for same-host simulation clients. Its parent
must already exist and the selected directory must not exist. Initialize it once:

```bash
PYTHONPATH=src python3 -m turbo.cli batch-registry-init path/to/new-registry
PYTHONPATH=src python3 -m turbo.cli batch-registry-status path/to/new-registry
PYTHONPATH=src python3 -m turbo.cli batch-registry-validate path/to/new-registry \
  "$AUTHORIZATION_SHA256" path/to/preparation-1 path/to/preparation-2
```

Set `AUTHORIZATION_SHA256` to the existing claim's full authorization digest shown by
registry status. Initialization explicitly writes local registry state. Status and
validation only inspect existing state; validation also replays the exact preparation
inputs. Neither creates a claim or dispatches a transport. There is no registry claim
or dispatch CLI. A new registry has no claims to validate.

The Python API `initialize_registry` creates a registry. `BatchRegistry` opens an
existing registry; its `open(authorization, preparation_dirs)` creates or reuses the
canonical journal and returns a managed client for B1's simulation operations. It has
no execution-directory argument. Managed clients using the same exact authorization
and registry share that journal's attempt history and counters. The new
`managed_budget_scope: single_registry_exact_authorization` describes this selection
boundary; B1's `budget_scope: single_journal_simulation` remains unchanged.

Keep the registry at its bound resolved path and use its pinned registry module and
schema versions. Its metadata binds a UUID and those hashes; moving the directory or
changing the bound implementation/schema fails validation. Same-host POSIX locks
coordinate claims and inspection. B1's journal locks coordinate attempts after the
registry lock is released, including before a fake transport callback.

A claim is durable before its journal is created. The ready receipt follows durable
journal initialization. Missing ready receipts, missing or partial claimed journals,
unclaimed journals at derived paths, and invalid bindings fail closed. Do not delete
or rebuild files to clear that failure. There is no automatic adoption, reset,
refund, claim deletion/rebinding, or implemented manual-recovery procedure. A partial
registry initialization likewise cannot be adopted by rerunning initialization.

This is one trusted local registry, not global spending authority. Separate
registries and edited or newly minted unsigned authorizations have independent
identities. Deleting/replacing all trusted state and privileged filesystem mutation
during operations are outside the guarantee. Standalone B1 still permits separate
journals and does not join the registry implicitly. Production authorization and
trusted-state governance remain blocking work before a live provider or paid canary.
See [ADR 0009](../decisions/0009-trusted-local-execution-registry.md).

### Batch-output contract inspection (Track B3)

Use 2–8 verified V2 preparations from the same scheduled batch in manifest order. Keep the
request and invocation IDs fixed when generating the context and validating the
corresponding synthetic output. Invocation IDs use `invocation:` followed by 24
lowercase hexadecimal characters; the example below is a synthetic placeholder:

```bash
PYTHONPATH=src python3 -m turbo.cli batch-output-context request-example invocation:000000000000000000000001 \
  path/to/preparation-1 path/to/preparation-2 --max-output-bytes 1000000
PYTHONPATH=src python3 -m turbo.cli batch-output-validate path/to/output.json \
  request-example invocation:000000000000000000000001 path/to/preparation-1 path/to/preparation-2 \
  --max-output-bytes 1000000
```

Both commands are read-only and write JSON to stdout. They neither save a context
file nor dispatch a model; shell redirection is a separate caller choice. Validation
regenerates the context from the verified preparations. Reuse the same output-byte
limit and IDs; an output bound to another context must not pass by changing only
its family labels.

A valid result establishes structural coverage and reference integrity. Finite
confidence in the range zero through one is not proof of calibration or factual
truth. A proposal with valid fields still needs substantive evidence and quality
review. Synthetic examples are not research executions or accepted boundaries.

This contract is not connected to B1 settlement or a real provider. B1's fake
response envelope rejects floating-point values throughout its output; do not assume
that a B3 confidence-bearing document can be embedded there unchanged. Adapter and
settlement integration require a later reviewed contract. See
[ADR 0010](../decisions/0010-batch-output-contract.md).

### Existing metered pilot lane

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
turbo boundary-activate config/universe/activations/<activation-config>.json
turbo boundary-validate-activation \
  data/market_graph/activations/<activation-id> \
  config/universe/activations/<activation-config>.json
turbo family-plan config/universe/family-partition-v1.json
turbo family-validate-plan data/family_schedules/<partition-id> \
  config/universe/family-partition-v1.json
turbo family-dry-run <family-id>
turbo family-prepare <family-id> --output-root <directory>
turbo family-validate-preparation <preparation-directory>
turbo graph-release config/universe/graph-releases/<release-config>.json
turbo graph-validate-release data/market_graph/versions/<release-id> \
  config/universe/graph-releases/<release-config>.json
```

The three V2 family-preparation commands are deterministic and make no model calls.
Use `family-dry-run` first. It verifies the corrected schedule and current graph,
compiles the exact config and pack in memory, enforces all count/size gates, and
prints hashes and counts without writing an artifact. Preparation fails rather than
truncating evidence. A persisted preparation is not authorization to execute it.

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

Activation is a separate, network-free step. Its preregistered config must bind an
exact valid run and zero-finding approval, enumerate the exact proposals and mappings,
retain every required provisional status and research gap, and prohibit Target
filtering, scoring, company work, model calls, and global rejection of family-local
candidate non-mappings. Commit the compiler before running activation so the receipt
can bind the exact execution head. The command fails if the worktree contains any
tracked or untracked change, and replay requires the receipt's full hexadecimal
execution commit to resolve locally. Then commit the resulting immutable events,
projection, receipt, replay test, and documentation as a separate increment.

Family plans and graph releases use the same exact-head rule. Commit their compiler,
configuration, tests, and documentation first. With a clean worktree, publish the
immutable outputs and verification pointer. Commit those outputs separately, replay
them, run the full local suite, and post exact hashes and head receipts to GitHub.

`turbo context` is the inspection command for current system state. It verifies the
latest source pointer against its immutable receipt, verifies every family-plan output
hash, verifies the cumulative graph receipt and projection, requires a common source
run, and then renders the layers separately. A failure is a blocker; do not replace
the missing layer with a directory scan or an inferred “latest” result.

## Agent coordination

The GM/PM owns decomposition and integration. Parallel agents receive non-overlapping
issues or review scopes. Each returns evidence, files changed, local test results, and
open risks. One agent's output is not accepted merely because another agent produced
it; integration and independent review remain explicit.
