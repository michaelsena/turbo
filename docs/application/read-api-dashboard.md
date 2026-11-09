# Read API and research console

## Purpose

This slice makes the repository's current verified universe-construction state
inspectable without creating a second source of truth. It is intentionally read-only
and local. It does not filter a Target Market Universe, score or rank markets, name
companies, invoke a model, perform network research, or mutate repository artifacts.

## Architecture

The product has three layers:

1. `ReadSnapshot` resolves exactly one source run, operating-family partition, and
   cumulative graph version. It verifies pointer receipts and every bound artifact
   hash, then rejects source-lineage mismatches. Historical source context comes from
   the selected receipt, and the schedule's frozen source hashes must agree with it.
   Graph receipt and projection must agree on version, publication status, and
   recomputed counts.
2. FastAPI exposes deterministic JSON resources. Each response has `data` and
   `provenance`, an ETag, private/no-cache semantics, and exact version headers.
3. The React/TypeScript/Vite client uses only those API resources. React Router owns
   navigation, TanStack Query owns remote state, and TanStack Table renders bounded
   collections. Research logic is never copied into TypeScript.

The compiled frontend is served by FastAPI. Vite's development server is optional
and proxies `/api` to FastAPI; it is not a second product backend.

## Current snapshot

The V1 golden path binds:

- source run `run-2ea0f00db84148de663f`
- partition `family-partition:60517981ab96e7f243c7033e`
- graph release `graph-release-aa5b6f83e7a06e073d3a`
- graph version `graph-e674a77fbfd5939c25c9e9a1`

The exact current counts are 11,543 normalized identities, 1,026 families, 1,018
schedulable families, 129 batches, 978 prior candidates, 58 unretrieved candidates,
3 canonical markets, 1 accepted mapping, and 2 distinct market research gaps.

## API contract

Market, mapping, family, batch, and candidate lists use one-based `page` and
`page_size` (1–100), with stable sorting. Family detail bounds its context separately
with `context_page` and `context_page_size`. Search uses `limit` (1–100), while the
version endpoint returns a catalog rather than a paginated collection. Successful
JSON responses use this envelope:

```json
{
  "data": {},
  "provenance": {
    "source_run_id": "...",
    "partition_id": "...",
    "graph_version_id": "...",
    "release_id": "...",
    "as_of_utc": "...",
    "context_fingerprint": "...",
    "read_model_version": "1.1.0"
  }
}
```

Routes:

- `GET /api/v1/context`
- `GET /api/v1/versions`
- `GET /api/v1/markets` and `/api/v1/markets/{market_id}`
- `GET /api/v1/mappings`
- `GET /api/v1/families` and `/api/v1/families/{family_id}`
- `GET /api/v1/batches`
- `GET /api/v1/identities/{identity_id}`
- `GET /api/v1/candidates`
- `GET /api/v1/search?q=...`
- `GET /api/v1/receipts/{kind}/{receipt_id}`

Every route above accepts the same optional `source_run_id`, `partition_id`, and
`graph_version_id` query parameters through one shared API dependency. The tuple must
share one source run and resolve to hash-verified immutable artifacts. A mismatch,
missing artifact, or hash failure returns an error rather than falling back to a
directory scan or inferred latest version. `/api/v1/versions` publishes only complete
compatible tuples as `compatible_snapshots`; the current pointer tuple remains
explicitly labeled. Missing tuple components use their current pointer values on
the backend; explicitly empty or invalid IDs are rejected. Snapshot-load failures
return a sanitized `409` response without exposing local paths.

Receipt kinds are fixed in code. IDs must match a narrow safe-character grammar and
cannot contain a path separator. Credential, authorization, secret, raw/private
reasoning, and chain-of-thought keys are recursively omitted and listed as redacted
paths. The route never provides arbitrary file access.

The provenance fingerprint binds the exact source, schedule, and graph receipt
hashes. HTTP ETags separately hash the complete response envelope, so a tag from one
route, filter, or page cannot incorrectly validate a different representation.
An equivalent cached response may return `304` with no JSON body. Error responses
use a `detail` field rather than the success envelope. A missing allowlisted receipt
returns `404 Receipt not found`; malformed stored receipt errors are sanitized.

## User interface

The visual system is Turbo-owned: quiet white surfaces, strong typography, generous
spacing, restrained grayscale, fine borders and shadows, rounded controls, compact
tables, progressive JSON disclosure, and small optional motion. It uses semantic
navigation, headings, labels, tables, keyboard-focus affordances, a skip link,
responsive breakpoints, and reduced-motion behavior.

The header snapshot selector is sourced from `compatible_snapshots`. Choosing a
historical tuple writes all three exact IDs into the URL and the client carries those
parameters into every API query and internal navigation. The client never computes
compatibility or joins versions itself. Partial or empty version parameters entered
in a URL are preserved for backend validation rather than silently replaced with
latest. The selector provides recovery to the current snapshot. The Audit page's
active snapshot comes from the selected response provenance; the catalog's current
pointer remains a separate concept.

Pages:

- `/` verified overview and explicit “not a ranking” boundary
- `/universe` accepted market table
- `/markets/{market_id}` boundary, gaps, source lineage, and audit chain
- `/families` neutral schedule
- `/families/{family_id}` required work, paginated context, and candidates
- `/batches` deterministic batch manifest
- `/audit` version catalog and active provenance
- `/docs` generated API reference

## Local verification

Install the Python environment and locked frontend dependencies using the
[runbook](../operations/runbook.md#read-api-and-react-console) first. Browser
acceptance requires Google Chrome. The default managed-server path uses the
repository-local `.venv`, as configured in `frontend/playwright.config.ts`. An
optional external loopback server can be supplied through `TURBO_TEST_BASE_URL`;
see the runbook for setup and lifecycle ownership.

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_read_model tests.test_web_api -v
cd frontend
npm test
npm run typecheck
npm run build
npm run test:visual
```

The Python tests cover exact fixture counts, compatibility, hashing boundaries,
ordering, pagination, search, ETags, receipt allowlists, sanitization boundaries,
and compiled-SPA delivery. Frontend tests cover the universe/evaluation boundary,
visible exact provenance, and tuple propagation. Playwright starts the compiled app
locally, runs WCAG 2 A/AA axe checks, exercises historical selection, and compares
screenshots for overview, universe, market detail, families, family detail, batches,
and audit at fixed desktop and mobile viewports. Baselines live under
`frontend/e2e/__screenshots__/`; transient reports remain ignored.

## Future extension boundary

Target eligibility, factor scores, pairwise comparisons, rankings, companies, and
notifications require their own durable projections and receipts. They must enter
through new API contracts; the client must never infer them from source titles,
administrative family order, or graph activation status.

Acceptance results belong to the exact commit receipt in GitHub. The presence of
a test or screenshot baseline is not a claim that the current tree has passed it.

The corrected code passed host-run browser comparisons and accessibility checks on
2026-11-09; all 14 screenshots were visually reviewed. Family detail now shows 80
required identities and Audit reports read-model 1.1.0. The executor's loopback and
Chrome restrictions were handled with the runbook's external-server path. See the
[exact verification receipt](../operations/receipts/2026-11-09-dashboard-corrections.json).
That receipt records the earlier desktop Overview badge clipping. The follow-up
uses a bounded single-column market row: name/description first, then the complete
status badge, wrapping when necessary. Overview and Universe call the collection
canonical markets in the selected graph and explicitly retain provisional boundaries;
listing a boundary does not imply it is settled. No status value or graph record is
changed. Regression checks assert status geometry at desktop/mobile widths and use
an explicitly synthetic long-status stress case. Direct connected-Chrome inspection
at desktop (1440 × 1000) and mobile (390 × 844) confirms all three full statuses and
bounded descriptions; historical Universe → Audit navigation retains the exact tuple.
This interactive check is distinct from executing the packaged Playwright/axe suite.
That suite and intentional screenshot refresh remain pending; historical baselines
are retained until the suite can run in a permitted process environment.
PR #19 is merged at `a9aef2befbc61208431ce4b546d6bed15d6edef1`.

## App ownership and intake

The [App/UI GM charter](https://github.com/michaelsena/turbo/issues/26) governs frontend,
UX, accessibility, frontend tests, app documentation, and the app backlog. Platform GM
retains research and execution ownership. Propose shared read/API changes through a
linked issue specifying contracts, compatibility, and acceptance checks before editing.
Each app issue names `Owner: App/UI GM`; its claim records branch and immediate scope.
The merged dispatcher implements `area:app` plus `status:ready` routing and requires
an authorized readiness event. Label existence and live pickup are separate checks.
The installed runtime currently reports no attempts and has not been verified running;
see [#27](https://github.com/michaelsena/turbo/issues/27) and the
[dispatcher guide](../operations/app-dispatcher.md).
During an active session, resume owned work before claiming another issue. No merge
occurs without explicit chairman authorization.
