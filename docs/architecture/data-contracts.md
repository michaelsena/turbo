# Data contracts

Turbo separates durable objects so one convenient JSON blob never becomes an
unreviewable source of truth.

## Source snapshot

Immutable bytes plus dataset ID, publisher, canonical URL, retrieval UTC, SHA-256,
reuse status, and declared role. Validation fails when bytes differ from the manifest.
For a governed multi-page browser capture, the immutable envelope additionally stores
each canonical/final URL, response status and content type, retrieval UTC, byte length,
body SHA-256, and base64 response entity. Capture metadata states whether ordinary
HTTP content decoding occurred; transport framing is never implied. Cookies,
credentials, and browser storage are excluded from the source snapshot.

## Source record

A stable row or object within one immutable snapshot:

- source-record ID, snapshot ID, source system, and unique row/object locator
- raw code, raw label, raw definition, hierarchy path, and source parent IDs
- row role such as industry, product, service, task, aggregate, residual, survey
  control, or unknown
- immutable source relationships and semantic flags

Retrieval normalization is never authoritative. Raw exclusions, negations, regulated
distinctions, customer scope, geography, and residual wording remain preserved.

## Normalized source identity

A typed NAICS or NAPCS code identity is distinct from every immutable row or
observation that mentions it. Identity nodes use their own namespace and link to one
or more source-record IDs. Official hierarchy, concordance, and industry-product
relationships connect identity nodes. Pair-level relationship edges retain every
contributing source observation separately, including snapshot ID, row number,
dimensions, and a unique locator. Source-row IDs, normalized identities,
candidate-market hypotheses, and canonical-market IDs are never interchangeable.

Manual index terms are stored in a separate identity-evidence artifact with their
current 2022 NAICS identity endpoint, raw extracted fragments, derived normalized
label, and exact PDF coordinates. Manual definition records are a second semantic
identity-evidence collection. Each record has one current NAICS endpoint, hierarchy
level, disposition (`substantive_inline_definition`, `delegated_definition`, or
`title_only_heading`), page range, derived narrative, separately derived illustrative
and cross-reference blocks, and the original coordinate fragments behind every
field. Delegated records also carry a validated current-identity endpoint. Historical
NAICS codes are stored as vintage lineage values rather than current identities.
Economic Census eight-digit bridge components are observations, not taxonomy or
market nodes. This prevents semantic enrichment and historical accounting constructs
from silently expanding the current market-reconciliation worklist.

## Observation and claim

An observation is a narrow, directly located source statement. A claim is an
interpretation labeled `fact`, `inference`, `assumption`, or `unknown`, with supporting
and contradicting observations and directed version edges.

## Market and market version

The market ID is an opaque stable identity and is never derived from a label, NAICS
code, or list position. A market version contains:

- canonical name, definition, boundary, parent, aliases, and explicit exclusions
- buyer, buyer role, budget owner, purchase trigger, and job-to-be-done
- deliverable, delivery model, work location, workforce, and revenue model
- capital, inventory, regulation, economics, and risk
- acquisition universe and operating playbook
- Ambient AI workflow and bounded context sources
- source mappings, split/merge lineage, evidence labels, and confidence by dimension

Dimension-level confidence is required because buyer identity may be well supported
while acquisition-universe equivalence remains uncertain.

## Mapping relationship

Normalized source identities and their supporting source records relate to markets
through typed, many-to-many edges:

- equivalent-label candidate
- broader-than-market / narrower-than-market
- industry-containing-market
- product-sold-by-market
- task-performed-by-market
- partial overlap
- residual bucket
- duplicate source record
- non-market product
- out of scope for canonicalization
- unresolved

NAICS usually supplies industry-containing-market edges. NAPCS usually supplies
product-sold-by-market edges. Neither source becomes a market one-for-one.

## Reconciliation event and graph version

Accepted decisions are append-only create, map, split, merge, rename, reparent,
exclude-source-record, reject-candidate, or supersede-decision events. Each event
preserves inputs, outputs, typed relationship, seven operating-identity results,
supporting and contrary records, alternatives, proposer, independent review,
adjudication, cutoff, and supersession.

Candidate-market hypotheses have a dedicated typed input field. Event supersession
withdraws or replaces a decision; rename and reparent events instead supersede the
current `market_version_id` without deactivating the event that originally created
the stable market identity.

A graph version is the deterministic projection of accepted events through a cutoff.
Its identity includes the ordered-event hash plus governed source, configuration, and
code hashes. Corrections add a superseding event; they never rewrite the prior event.
Split and merge events retire their predecessor market IDs from the effective graph
while preserving them and their successor lineage in history. Mappings to retired
markets move to an explicitly historical collection rather than dangling in the
effective graph.

Every accepted market version installed by an active event remains subject to
referential validation even if a later split or merge retires it. Retirement changes
effective state; it does not erase historical validation obligations.

## Boundary evidence pack and model outputs

A boundary pack is a deterministic, disposable view over one immutable universe run.
It records the family configuration, source-run and artifact hashes, explicit cutoff,
required-disposition identities, context-only identities, citable evidence catalog,
prior-candidate details, exact count gates, and its own canonical SHA-256. Changing any
content changes the pack hash; changing a governed source artifact fails compilation.

Specialist outputs contain proposed markets, complete identity and candidate
dispositions, evidence labels, dimension-level confidence, supporting and contrary
evidence IDs, alternatives, and active retry gaps. Evidence IDs must resolve inside
the exact pack. Adjudication uses the same decision payload plus a resolution record
for each specialist and the two exact specialist-output hashes. Neither output is an
accepted Market Graph event. A deterministic compiler and independent review are
separate activation gates.

Invocation receipts store provider, role, requested and served model, served provider
when reported, reasoning effort, prompt, schema, pack, request, response, and output
hashes, model-facing provider-schema hash, UTC start/end, latency, attempts,
generation ID, sanitized token/cost usage, and validation result. Provider-specific
fields such as CLI version or HTTP status are retained where relevant. The full
canonical schema remains the acceptance contract even when a portable subset is sent
to a model provider. A bounded correction sequence retains one nested call receipt
per model call plus the number of validation repairs used. Receipts explicitly state
that credentials and raw model reasoning were not persisted.

A boundary run receipt also records the exact execution commit, config hash, frozen
pack hash, both specialist output hashes, adjudication hash, and non-activation
status. `boundary-validate-run` rebuilds the exact pack, reruns all three local
validators, and checks every receipt binding before review.


## Factor definition, evaluator result, and score event

A factor definition contains anchors, evidence expectations, weight, confidence
policy, model policy, disagreement tolerance, and version. An evaluator result
preserves its frozen evidence pack, model/prompt/config versions, raw answer,
rationale, evidence, counterevidence, alternatives, and hash. A score event resolves
results into a factor score with confidence, evidence quality, downside, risk
adjustment, and adjudication.

## Evidence gap

An active work item with question, scope, retry state, ranking sensitivity,
uncertainty, probability of finding evidence, cost estimate, priority, attempts, and
terminal condition. Gaps never null out accepted scores.

## Run receipt

Contains immutable run ID, input/configuration hashes, the explicitly scoped universe-
generation code and source-schema fingerprints, parser dependency versions, output
hashes, and validation results. Agent, scoring, API, or UI files cannot create a new
source-universe run when the universe method is unchanged. Exact Git head and wall-clock local verification are
posted as GitHub issue/PR receipts so deterministic replay never dirties the worktree.

Formal JSON Schemas and executable projection tests precede external API stability.

