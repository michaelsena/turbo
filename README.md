# Turbo

Turbo is an auditable research system for finding U.S. markets suited to an
AI-enabled lower-middle-market acquisition strategy. It asks where an owner can buy
a good business at a disciplined price, improve its production bottleneck with
Ambient AI, and retain the resulting earnings.

The repository is the source of truth for evidence, market boundaries, research
inputs, decisions, executable methods, and results. The local research console
exposes those same versioned artifacts through a read-only API.

## Current state

**Turbo is constructing the canonical market universe. Target eligibility and
investment scoring have not started.** A source category, retrieval match, family
queue position, or provisional boundary is not an investment recommendation.

| Verified projection | Current result |
| --- | ---: |
| Governed source snapshots | 13 |
| Preserved source rows and observations | 30,850 |
| Normalized NAICS/NAPCS identities | 11,543 |
| Six-digit NAICS source categories | 1,012 |
| Identities requiring boundary review | 8,248 |
| Context-only identities | 3,295 |
| Administrative families / queued families | 1,026 / 1,018 |
| Deterministic review batches | 129 |
| Prior-market candidates / unretrieved challengers | 978 / 58 |
| Canonical markets / accepted mapping events | 3 / 1 |
| Distinct open market-boundary gaps | 2 |
| Target markets / investment scores | 0 / 0 |

The first reviewed family produced **Integrated outsourced office administration**
(accepted with open gaps), **Medical practice administration** (provisional), and
**Dental practice administration** (provisional). NAICS 561110 has one provisional
`broader_than_market` mapping to the horizontal administration market. The operating
model and vertical-boundary gaps remain open; family-local non-mappings have not
removed any of the 978 prior candidates globally.

Current immutable layers:

| Layer | Version |
| --- | --- |
| Source universe | [`run-2ea0f00db84148de663f`](data/runs/run-2ea0f00db84148de663f/) |
| Family schedule | [`family-partition:60517981ab96e7f243c7033e`](data/family_schedules/family-partition:60517981ab96e7f243c7033e/) |
| Cumulative graph release | [`graph-release-aa5b6f83e7a06e073d3a`](data/market_graph/versions/graph-release-aa5b6f83e7a06e073d3a/) |
| Graph version | `graph-e674a77fbfd5939c25c9e9a1` |

`turbo context` verifies and composes these layers. The source receipt's historical
`canonical_markets: 0` describes that source run alone, not the current graph.
The [corrected pilot run](data/agent_runs/boundary-run-1a88e9a3acdf15d63b09/),
[independent approval](data/agent_reviews/independent-review-b95c0d39bef8bffa9c00/),
and [activation](data/market_graph/activations/boundary-activation-9d3772f0364b4632dc62/)
preserve the accepted decision chain. The [universe methodology](docs/universe/methodology.md)
and [schedule specification](docs/issues/0014-family-partition-scheduler.md)
explain source coverage, anomalies, prior corrections, and remaining work.

## Strategy and system design

The initial mandate targets U.S. businesses generally worth **$10M–$50M**, preferably
at **7–8× or less normalized EBITDA**, with a **9× default ceiling** unless an exception
is approved. Existing business economics must support the acquisition; AI is upside.
The strategy favors service businesses and allows either a permanent holdco or
build-and-exit platform. Healthcare delivery, government-dependent revenue,
heavy-equipment ownership, significant inventory, insurance or credit risk,
unionized workforces, and reimbursement exposure are outside the initial mandate.
These are later eligibility rules, not reasons to erase a market from the universe.

Turbo separates three ordered decisions:

1. **Canonical universe — what markets exist.** Preserve official NAICS/NAPCS
   identities and relationships, reconcile the 978 prior hypotheses, and review
   operating boundaries across buyer, job, delivery, workforce, economics,
   acquisition universe, and Ambient AI workflow. A taxonomy code is not itself a
   canonical operating market. Splits, merges, mappings, and exclusions retain lineage.
2. **Target universe — what is eligible.** Apply separately versioned strategy gates
   and size/buyability evidence. SUSB and QCEW enrichment belongs here and remains
   planned; a rejected target still exists in the canonical graph.
3. **Evaluation — what is attractive.** Research and score only eligible markets,
   retaining raw score, confidence, evidence quality, downside penalty, and
   risk-adjusted score. Independent evaluators and adjudication resolve judgments;
   pairwise calibration belongs inside each submodel, not the global ranking.

The Ambient AI thesis is **Capture → Connect → Recognize → Act → Verify**: connect
permitted context across applications, messages, documents, people, and physical
work to a durable customer obligation, take authorized action, and verify completion.
A useful thesis must identify the core production bottleneck, measurable output,
demand for released capacity, and the owner's route to retained earnings.
See the [Ambient AI thesis](docs/ambient-ai/thesis.md) and [scoring design](docs/scoring/model.md).

Sources, observations, claims, scores, decisions, lessons, and questions remain
separate. Reasoning is labeled `fact`, `inference`, `assumption`, or `unknown`.
Immutable snapshots carry URL, retrieval UTC, and SHA-256; changed conclusions append
`supersedes` or `contradicts` edges. Research gaps remain visible. When scoring begins,
weak evidence requires a documented low-confidence score rather than a blank cell.

## Inspect the local product

The console includes an overview, accepted-market explorer and detail pages, neutral
family queue and detail pages, batch plan, and audit view. Historical inspection uses
verified source/schedule/graph tuples. Responses carry exact provenance; ETags identify
the complete response envelope. The client does not decide version compatibility or
reimplement research logic.

FastAPI serves both JSON and the compiled React/TypeScript/Vite client. React Router,
TanStack Query, and TanStack Table support navigation, remote state, and bounded
collections. There is no application database, hosted deployment, write API, model
call, or research-network request in the read product.

Requires Python 3.11+ and a Node.js version supported by Vite 7 (20.19+ or 22.12+).

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
Alternatively, after building the client, `./scripts/serve-local.sh` starts the same
loopback-only product on port 8017. It uses `.venv/bin/python` unless `TURBO_PYTHON`
specifies another prepared interpreter. Stop the local process after use. The [application guide](docs/application/read-api-dashboard.md)
defines routes, provenance, pagination, version selection, and limitations. The
[runbook](docs/operations/runbook.md) covers development and verification, including
Chrome-based desktop/mobile screenshot and accessibility checks.

## Development status and next work

[Family-preparation PR #18](https://github.com/michaelsena/turbo/pull/18) is merged
at `83482e00999200933b9d48e3e018bcbf19246052`. It adds deterministic family configs,
frozen evidence packs, size/count gates, and exact replay. Required NAICS definitions,
exclusions, index evidence, and non-owned candidate context remain available; source,
compiler, and schema hashes bind each preparation. See [Issue 15](docs/issues/0015-batch-native-family-research.md)
and its [audit receipt](docs/operations/receipts/2026-11-09-family-pack-corrections.json).

[Dashboard PR #19](https://github.com/michaelsena/turbo/pull/19) is merged at
`a9aef2befbc61208431ce4b546d6bed15d6edef1`.
The corrected code passed 162 Python tests, frontend unit/type/build checks, and
host-run browser screenshot/accessibility checks. All 14 desktop/mobile images were
reviewed, including corrected family counts and Audit provenance. See the
[verification receipt](docs/operations/receipts/2026-11-09-dashboard-corrections.json)
for exact hashes and the minor Overview status-badge clipping follow-up.

The simulation execution foundation is merged: [B1 / PR #21](https://github.com/michaelsena/turbo/pull/21)
provides authorization, reservation, and replay within one journal; [B2 / PR #23](https://github.com/michaelsena/turbo/pull/23)
adds a trusted local registry at `639c3216ac5d3e3baf28fcffbeac8af5bf8e478d`.
Repeated managed clients share one exact authorization's journal. Ambiguous dispatch
retains its reservation; missing claimed state fails closed. Different registries,
new unsigned authorizations, and privileged deletion/rollback remain outside this
guarantee. Standalone B1 stays per-journal. See the
[B1 receipt](docs/operations/receipts/2026-11-09-batch-ledger-verification.json) and
[B2 receipt](docs/operations/receipts/2026-11-09-shared-registry-verification.json)
for pinned tests, simulation replay, and review results.

[PR #25](https://github.com/michaelsena/turbo/pull/25) implements Track B3, a
standalone batch-output contract over verified family preparations. It checks
structural coverage, evidence references, reasoning labels,
confidence, gaps, and boundary proposals; synthetic validation is not research
acceptance. It does not dispatch models or feed B1 settlement automatically.
All 237 Python tests passed, including 22 focused checks; independent review found
no blocking issues. A synthetic two-family validation covered all 59 required
subjects without changing the market graph. PR #25 remains unmerged. See
[ADR 0010](docs/decisions/0010-batch-output-contract.md) and the
[verification receipt](docs/operations/receipts/2026-11-09-batch-output-verification.json).

Real model dispatch and adapter integration, selective independent verification,
disagreement escalation, and deterministic family closure remain later work. Approve
and evaluate one neutral metered canary before authorizing broad execution. Then
complete cross-family coverage, publish the canonical universe, add Target filtering,
and begin production scoring.
The read product can expand only as those durable projections become available.

## Working protocol and navigation

Every material change starts with a scoped GitHub issue and acceptance criteria.
Use a named branch, keep README and detailed docs synchronized, record decisions and
local verification receipts, obtain independent review, and merge only after
acceptance. Protected checks are never bypassed. Tests and replay run locally;
GitHub Actions and hosted CI are intentionally not configured. No paid sources,
outreach, confidential/personal data, or external representation is authorized.
Metered model runs have separate explicit configuration and spending gates.

| Read or work on | Entry point |
| --- | --- |
| Documentation map | [docs/INDEX.md](docs/INDEX.md) |
| Product purpose | [Vision](docs/product/vision.md) |
| Architecture and contracts | [System](docs/architecture/system.md), [contracts](docs/architecture/data-contracts.md) |
| Source coverage and market identity | [Universe methodology](docs/universe/methodology.md), `src/turbo/universe/` |
| Source snapshots and immutable projections | `data/source_snapshots/`, `data/runs/`, `data/family_schedules/`, `data/market_graph/` |
| Current verified pointers | `data/generated/latest-run.json`, `latest-family-schedule.json`, `latest-graph.json` |
| Model execution and review | `src/turbo/agents/`, `data/agent_runs/`, `data/agent_reviews/` |
| Read API and UI | `src/turbo/web/`, `frontend/`, [application guide](docs/application/read-api-dashboard.md) |
| Commands and acceptance | `src/turbo/cli.py`, `tests/`, [runbook](docs/operations/runbook.md) |
| Consequential design choices | [Architecture decisions](docs/INDEX.md#architecture-decisions) |
