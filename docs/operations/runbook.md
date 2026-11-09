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

For the current PR #19 correction, inspect and replace the inherited mobile
family-detail baseline (`0` required identities instead of `80`) and Audit baseline
(read-model `1.0.0` instead of `1.1.0`) before claiming visual acceptance. The bind
restriction blocks that check in the current executor; neither those stale images
nor prior receipts establish a pass for the corrected tree.

Before accepting a UI/API change, run the focused Python tests, frontend tests,
TypeScript check, production build, full Python suite, repository validation, and
current-context compile. Record the exact commit and counts in the issue/PR. Do not
commit `node_modules`, `frontend/dist`, `.venv`, or `*.tsbuildinfo`; do commit
`package-lock.json`.

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

