# Turbo

Turbo is an auditable research system for finding U.S. markets suited to an
AI-enabled lower-middle-market acquisition strategy. It asks where an owner can buy
a good business at a disciplined price, improve its production bottleneck with
Ambient AI, and retain the resulting earnings.

The repository holds the evidence, market definitions, executable methods,
decisions, and results. A local research console exposes the same versioned
artifacts through a read-only API. Turbo is currently building and qualifying its
market universe; it has **five canonical markets, zero national target markets,
and zero national investment scores**. A taxonomy category or provisional market
boundary is not an investment recommendation.

## What the system does

Turbo separates three decisions. They have independent versioned projections;
a later decision cannot silently rewrite an earlier one.

| Layer | Question and method | Current scope |
| --- | --- | --- |
| Canonical universe | What operating markets exist? Reconcile official NAICS/NAPCS identities and prior hypotheses; preserve splits, merges, mappings, exclusions, and gaps. | Source ingestion, scheduling, research harness, reviewed publication, and five-market graph implemented; national coverage incomplete. |
| Target universe | Which markets meet the acquisition mandate? Apply strategy gates and size/buyability evidence without erasing ineligible canonical markets. | Governed market eligibility adapter implemented; national filtering and SUSB/QCEW enrichment remain planned. |
| Evaluation | Which eligible markets are attractive? Evaluate factors independently, adjudicate disagreements, calibrate within submodels, and aggregate deterministically. | Governed single-submodel execution adapter implemented. Production factor policies and global aggregation remain pending; no accepted investment scores. |

The initial mandate favors U.S. service businesses generally worth **$10M–$50M**,
preferably at **7–8× or less normalized EBITDA**, with a **9× default ceiling** unless
an exception is approved. Existing economics must support the acquisition; AI is
upside. The strategy allows a permanent holdco or a build-and-exit platform.
Healthcare delivery, government-dependent revenue, heavy-equipment
ownership, significant inventory, insurance or credit risk, unionized workforces,
and reimbursement exposure are outside the initial mandate. These are eligibility
rules, not reasons to delete markets from the canonical universe.

A market definition must address buyer, job-to-be-done, delivery model, workforce,
economics, acquisition universe, and Ambient AI workflow. The AI thesis is
**Capture → Connect → Recognize → Act → Verify**: connect permitted context to a
customer obligation, take authorized action, and verify completion. Research must
identify the production bottleneck, measurable output, demand for released
capacity, and the owner's route to retained earnings. See the
[universe methodology](docs/universe/methodology.md),
[AI thesis](docs/ambient-ai/thesis.md), and [scoring design](docs/scoring/model.md).

## Architecture and research flow

| Component | Responsibility | Durable output or boundary |
| --- | --- | --- |
| Source registry and ingestion | Preserve public snapshots and normalize source identities and relationships. | Immutable bytes, locators, retrieval times, hashes, and source-run receipts. |
| Family scheduler and preparation | Assign administrative ownership, queue review work, and freeze complete evidence packs. | Separate identity obligations, relationship context, candidate collisions, and deterministic batches. Queue position is not attractiveness. |
| Research harness | Bind model roles to explicit inputs, schemas, prompts, routing, and spending authority. | Structured outputs and provenance; invalid output never becomes accepted research merely because a call succeeded. |
| Validation and graph publication | Check coverage/citations, review exact proposed movements, replay accepted events, and preserve unresolved gaps. | Append-only graph events, cumulative releases, closure receipts, and verified current pointers. |
| Target and scoring layers | Apply eligibility, specialist evaluation, adjudication, and submodel calibration. | Separate later projections; boundary defects return to universe review. |
| Read API and console | Compose a verified source/schedule/graph tuple and render it consistently. | Deterministic FastAPI responses and React views; no application database or write API. |

Three research workflows serve different purposes; they are not interchangeable.

| Workflow | Role sequence | Acceptance boundary |
| --- | --- | --- |
| Original boundary pilot | Two blind specialists → adjudicator → independent review. | Established the initial administration-market definitions. |
| Scaled universe construction | Batch primary → selective independent verifier → conditional two blind specialists and adjudicator → mandatory release reviewer. | Reviewer approves the exact compiler preview; deterministic activation, cumulative release, and closure follow. Routine work uses three roles; disagreement adds three. |
| Later investment evaluation | Independent factor evaluators → adjudication → submodel-owned pairwise calibration → deterministic aggregation. | Eligibility and scoring stay separate from market identity; no generalist global pairwise ranking. |

The governed model path uses the project's harness and **OpenRouter**, with explicit
model and provider-routing configuration. It does not silently choose a cheaper
model or change scope. The separate [local Codex draft runner](docs/operations/real-batch-research.md)
is not the governed OpenRouter batch path. The
[workflow decision map](docs/decisions/0012-research-workflow-scope.md) defines these boundaries.

Sources, observations, claims, scores, decisions, lessons, and questions remain
separate. Reasoning is labeled `fact`, `inference`, `assumption`, or `unknown`.
Changed conclusions append supersession or contradiction links; they do not erase
history. Weak evidence must remain visible as uncertainty and explicit research gaps.
Structural validation is necessary, but cannot prove semantic correctness.

## Verified state and qualification limits

| Current verified projection | Result |
| --- | ---: |
| Governed snapshots / preserved source rows and observations | 13 / 30,850 |
| Normalized NAICS/NAPCS identities / six-digit NAICS categories | 11,543 / 1,012 |
| Identities requiring boundary review / context-only identities | 8,248 / 3,295 |
| Administrative families / queued families / deterministic batches | 1,026 / 1,018 / 129 |
| Prior-market candidates / unretrieved challengers | 978 / 58 |
| Canonical markets / accepted mapping events | 5 / 8 |
| Distinct market-linked boundary gaps / gaps in full closure lineage | 4 / 5 |
| National target markets / national investment scores | 0 / 0 |

The canonical graph contains Integrated outsourced office administration (accepted
with open gaps), Medical practice administration and Dental practice administration
(provisional), and Industrial Sand Mining and Preparation and Copper, Nickel, Lead,
and Zinc Ore Mining (provisional). The original NAICS 561110 mapping is provisionally
`broader_than_market`; family-local non-mappings do not remove prior candidates globally.

| Capability or experiment | Status and limitation |
| --- | --- |
| Source, schedule, graph, and local read console | Implemented. The console provides overview, market and family detail, batch plan, and audit views with explicit historical version selection. |
| Small two-family qualification | Published: eight identities, primary/verifier approval, independent exact-preview approval, cumulative release, and validated closure. Original pilot rows remain intact. [Replay bundle](data/research_pilots/small-qualification-20261109/README.md). |
| Managed execution and serial controller | Implemented within one trusted local registry. Stable attempt IDs and retained reservations prevent automatic resend after uncertainty. Publication pauses for an explicit source commit; local completion does not imply GitHub publication or the next input freeze. |
| Reviewer readable references and cheaper-model screening | Experimental opt-in. Flash passed four cells over two fixtures; this is not general quality qualification or production-default enablement. [Screening report](docs/operations/flash-reviewer-screening.md). |
| Medium primary qualification | Failed citation validation and independent semantic review; zero accepted coverage. Correction is tracked in [#73](https://github.com/michaelsena/turbo/issues/73); the [result documentation PR](https://github.com/michaelsena/turbo/pull/74) is separate from this README update. |
| Next service cohort | Association management and lease administration are priority research candidates under [#78](https://github.com/michaelsena/turbo/issues/78). Neither is an accepted canonical market; neither has accepted eligibility decisions or scores. They must pass the governed boundary, target, and evaluation stages. |
| Broad universe rollout, national eligibility, and investment ranking | Not complete. Larger-workload quality, output headroom, throughput, and total spend still require qualification. No universe-wide 5× cost reduction is established. |

The separate [anchored research pilot](data/research_pilots/anchored-20261109/README.md)
contains six provisional manufacturing hypotheses, 82 identity dispositions, one
candidate, and 16 gaps. It was collaboration-agent authored after a local CLI
failure; it is not accepted canonical coverage or a successful CLI run.

Current immutable layers are the
[source run](data/runs/run-2ea0f00db84148de663f/),
[family schedule](data/family_schedules/family-partition:60517981ab96e7f243c7033e/),
and [cumulative graph release](data/market_graph/versions/graph-release-a09c97692a785c2a9711/)
(graph version `graph-9838996c8153c20c7f86c37a`). `turbo context` verifies their
composition. Historical source-run counts are not current cumulative graph counts.
The [workload report](docs/operations/universe-workload-envelope.md) distinguishes
completed dispositions from unresolved gaps and remaining schedule obligations.

The reviewed lease boundary is [staged for cumulative publication](data/research_pilots/lease-qualification-20261110/README.md).
Its provisional activation and replay inputs are preserved; the current graph remains
at five markets until the cumulative release is generated and verified.

The next implementation priority is the governed end-to-end path for that service
cohort: accepted market identity, explicit target eligibility, then independently
reviewed investment evaluation. Governed eligibility and single-submodel execution
adapters are implemented, but production runs still require accepted canonical
versions, verified eligibility evidence, and explicit registered factor policies.
No service-market eligibility decision or investment score has been accepted.

## Run the local console

Requires Python 3.11+ and Node.js supported by Vite 7 (20.19+ or 22.12+).
These commands validate committed artifacts and start the read product; they do
not dispatch models or perform research-network requests.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
python3 -m pip install -r requirements-web.txt
python3 -m turbo.cli validate
python3 -m turbo.cli context
cd frontend
npm ci
npm run build
cd ..
PYTHONPATH=src .venv/bin/python -m uvicorn turbo.web.app:app --host 127.0.0.1 --port 8000
```

Open [the console](http://127.0.0.1:8000) or [API documentation](http://127.0.0.1:8000/docs).
Alternatively, after building the client, `./scripts/serve-local.sh` uses port 8017
and `.venv/bin/python` (or `TURBO_PYTHON`). Stop the local process after use.
FastAPI serves the compiled React/TypeScript/Vite client. The UI does not recreate
research logic or version compatibility; provenance and ETags bind complete responses.
There is no hosted deployment, application database, or model-dispatch surface in
this read product. See the [application guide](docs/application/read-api-dashboard.md).

## Operate and contribute

Start material work with a scoped, scored GitHub issue and acceptance criteria.
A narrowly [bound release-review successor](docs/operations/release-review-recovery.md) preserves accepted research after a supported HTTP400 while retaining unknown cost exposure.
Fresh managed runs may opt into [traced citation-set normalization](docs/operations/citation-set-output.md);
canonical semantic checks and independent review remain mandatory.
Use a named branch, immutable evidence, synchronized documentation, local verification
receipts, and independent review. Do not bypass protected checks. GitHub Actions and
hosted CI are intentionally not configured; verification runs locally.

```bash
python3 -m turbo.cli validate
python3 -m turbo.cli context
python3 -m unittest discover -s tests -v
```

Run the narrowest focused tests first, then the required suite and relevant replay.
The [runbook](docs/operations/runbook.md) covers frontend checks, browser acceptance,
and governed operator commands. The App/UI and Platform GM roles own separate
backlogs; a ready GitHub issue alone does not guarantee an agent is running. See the
[worker charter](docs/operations/app-gm-worker.md) and [dispatcher guide](docs/operations/app-dispatcher.md).

Metered model execution requires explicit scope, configuration, and spending
approval. Known usage remains charged even when output is invalid; uncertain
transport or usage retains its reservation. The trusted local registry guarantee
does not span arbitrary separate registries, new unsigned authorities, or privileged
state deletion. Recovery never silently resets budgets or repairs accepted history.
No paid sources, outreach, confidential/personal data, or external representation
is authorized by this repository's normal workflow.

## Documentation map

| Need | Authoritative guide |
| --- | --- |
| Purpose, architecture, and data contracts | [Vision](docs/product/vision.md), [system](docs/architecture/system.md), [contracts](docs/architecture/data-contracts.md) |
| Market methodology and strategy research | [Universe](docs/universe/methodology.md), [Ambient AI](docs/ambient-ai/thesis.md), [scoring](docs/scoring/model.md) |
| Prepare, execute, and publish a batch | [Runbook](docs/operations/runbook.md), [serial controller](docs/operations/batch-controller.md), [frozen supplemental evidence](docs/operations/family-supplemental-evidence.md), [single-family runs](docs/operations/single-family-batch.md), [publication replay](docs/operations/small-qualification-publication.md) |
| Admit eligible markets and evaluate one submodel | [Eligibility](docs/operations/governed-eligibility.md), [governed execution](docs/operations/governed-evaluation-runtime.md), [initial bounded service calibration](docs/scoring/initial-service-calibration.md); production factor policies and global aggregation remain pending |
| Recover failed execution | [Payment recovery](docs/operations/payment-rejection-recovery.md), [release-review recovery](docs/operations/release-review-recovery.md) |
| Qualify larger workloads or reviewer changes | [Medium preflight](docs/operations/medium-primary-preflight.md), [reviewer qualification](docs/operations/reviewer-qualification.md), [readable references](docs/operations/reviewer-readable-view.md) |
| Inspect implementation and artifacts | `src/turbo/universe/`, `src/turbo/agents/`, `src/turbo/web/`, `frontend/`; `data/source_snapshots/`, `data/runs/`, `data/family_schedules/`, `data/market_graph/` |
| Find current verified pointers | `data/generated/latest-run.json`, `latest-family-schedule.json`, `latest-graph.json` |
| Detailed design decisions and historical receipts | [Documentation index](docs/INDEX.md), [architecture decisions](docs/INDEX.md#architecture-decisions) |
