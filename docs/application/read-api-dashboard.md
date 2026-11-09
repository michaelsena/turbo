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
   hash, then rejects source-lineage mismatches.
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

All collection routes use one-based `page`, bounded `page_size` (1–100), stable
sorting, and an envelope:

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
    "read_model_version": "1.0.0"
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

`context`, `markets`, and later version-aware resources accept an explicit compatible
source-run/partition/graph tuple. The tuple must share one source run. A mismatch,
missing artifact, or hash failure returns an error rather than falling back to a
directory scan or inferred latest version.

Receipt kinds are fixed in code. IDs must match a narrow safe-character grammar and
cannot contain a path separator. Credential, authorization, secret, raw/private
reasoning, and chain-of-thought keys are recursively omitted and listed as redacted
paths. The route never provides arbitrary file access.

## User interface

The visual system is Turbo-owned: quiet white surfaces, strong typography, generous
spacing, restrained grayscale, fine borders and shadows, rounded controls, compact
tables, progressive JSON disclosure, and small optional motion. It uses semantic
navigation, headings, labels, tables, keyboard-focus affordances, a skip link,
responsive breakpoints, and reduced-motion behavior.

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

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_read_model tests.test_web_api -v
cd frontend
npm test
npm run typecheck
npm run build
```

The Python tests cover exact fixture counts, compatibility, hashing boundaries,
ordering, pagination, search, ETags, receipt allowlists, sanitization boundaries,
and compiled-SPA delivery. Frontend tests cover the universe/evaluation boundary and
visible exact provenance. Browser QA checks overview, table, detail, and responsive
CSS against the compiled local build.

## Future extension boundary

Target eligibility, factor scores, pairwise comparisons, rankings, companies, and
notifications require their own durable projections and receipts. They must enter
through new API contracts; the client must never infer them from source titles,
administrative family order, or graph activation status.
