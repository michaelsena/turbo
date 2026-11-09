# Data contracts

## Verified read snapshot and API envelope

A read snapshot is an immutable in-memory join of one compatible source run, family
partition, and cumulative graph version. Its identity binds their exact receipts and
artifact hashes plus the read-model version. Loading fails if a pointer, receipt,
projection, output hash, partition ID, or source lineage disagrees. All declared
source artifacts are rehashed when loading a snapshot; the selected source receipt
must also agree with the schedule's frozen source hashes. Historical source context
is built from that selected receipt. Published graph status, graph version, and
recomputed activation/event/market/mapping counts must match the graph receipt.
Schedule artifact headers must agree with its receipt; published totals and family/
batch workloads must agree with the hash-verified collections. Legacy four-artifact
plans remain inspectable, while the corrected five-artifact format enforces its added
count fields and relationship ledger.

Successful JSON resource responses contain `data` plus exact provenance: source run, partition,
graph version, release, as-of time, read-model version, and context fingerprint.
Market, mapping, family, batch, and candidate lists are deterministically sorted
and paginated; nested family context is separately bounded. Search has a bounded
result limit, while versions returns a catalog. Errors use `detail`; `304` responses
have no body. The context fingerprint includes all three exact receipt
hashes; each HTTP ETag hashes its complete response envelope, and `If-None-Match` may
return 304 only for that equivalent representation. Receipt resources resolve only
an enumerated kind and safe ID beneath a fixed repository root, then recursively remove secret, credential, authorization,
and private-reasoning fields.

One shared request dependency applies `source_run_id`, `partition_id`, and
`graph_version_id` to every snapshot-backed endpoint. The version catalog lists
complete compatible tuples only after loading and verifying each join. The browser
may select and propagate one of those tuples, but compatibility remains a backend
contract and is never reimplemented in TypeScript. Partial and empty explicit URL
parameters reach backend validation unchanged; snapshot-load errors use a sanitized
409 response. Active Audit provenance comes from the selected response, not the
version catalog's current-pointer entry.

The API is a projection of repository truth, not new truth. UI state, administrative
ordering, source titles, and client-side filters never create market, Target, or
evaluation facts.

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

An independent boundary-review record binds one exact run, pack, and adjudication
hash. It contains the registered check results, P0/P1/P2 findings, evidence IDs,
affected output paths, activation conditions, alternatives, verdict, and confidence.
The validator requires the exact check set, closed-world evidence references, and
zero findings plus all-pass checks for an approval verdict. Review remains advisory
until a separately preregistered activation config binds the exact run, pack,
adjudication, review, allowed proposals, mapping dispositions, statuses, and gaps.
The network-free activation compiler replays those inputs, emits only the authorized
events, projects the graph, and records exact event/projection hashes plus its
execution commit. `boundary-validate-activation` recompiles the events and projection
and fails on any drift. Family-local non-mappings cannot be compiled as global
candidate rejections.

## Family partition, schedule, and graph release

A family partition binds one immutable source run, the exact reconciliation and
relationship artifact hashes, a versioned deterministic method, explicit UTC cutoff,
configuration hash, and execution commit. Its coverage ledger gives every normalized
identity exactly one administrative owner and one role: `required_review` or
`context_only`. Multiple family appearances are permitted and expected; they cannot
create a second primary disposition obligation.

The candidate-collision ledger is separate because prior market hypotheses and
source identities are different namespaces. It preserves every retrieval occurrence,
all collision families, one administrative challenge owner, and an explicit status
for candidates with no current retrieval collision. A local candidate disposition
never becomes a global rejection through scheduling. The primary owner must be a
schedulable family or completed regression fixture; otherwise the candidate enters an
explicit global challenge family.

The context-edge ledger preserves every official industry-product relationship,
collection/trilateral relationship, and explicit concordance non-mapping with stable
relationship ID, exact endpoints, source observations, and administrative routing.
It is relationship topology for evidence assembly, never a canonical market mapping.

The family manifest contains exact required identities, context identities, context
shards, required candidate hypotheses, workload counts, status, and a neutral priority
key. A batch is an ordered collection of independent family runs, not a merged evidence
pack. Coverage, relationship-context, collision, family, and batch outputs use
byte-stable canonical JSON or fixed-timestamp gzip and are hash-bound from the schedule
receipt.

A cumulative graph release binds exact activation IDs, directories, configs, event
hashes, projection hashes, source-universe run, cutoff, config hash, code commit, and
the resulting cumulative projection hash. `latest-graph.json` and
`latest-family-schedule.json` are verification pointers only; their referenced
receipts and artifacts must rehash before they enter composed context.

### Schedule-driven family config and evidence pack V2

A family config V2 resolves to exactly one schedulable family-manifest entry. It binds
the schedule receipt and artifact hashes, cumulative graph receipt and projection,
exact required identities, authored context shards, exact required candidates,
expected context-edge count, and fail-closed limits. The config is a deterministic
research-input declaration, not a decision or execution authorization.

A family evidence pack V2 is a disposable, frozen view over those immutable inputs.
It includes complete cards for required source identities, compact cards for context,
exact ledger relationship IDs and locators, required candidate cards, and relevant
existing graph context. Context-only identities cannot become primary obligations.
The content hash excludes only its own hash field. Persisted preparations are
content-addressed and replayed by regenerating the config and pack. Replay also
requires each persisted config, pack, and receipt file to equal its canonical JSON
bytes exactly; parsing to the same object is insufficient.

Pack compilation verifies the full source-run receipt and all declared artifact bytes.
Artifacts frozen by the family schedule must additionally match its source hashes.
The Manual artifact is separately bound through the verified full source run because
the historical schedule did not consume it; the schedule is never retroactively changed. Graph context likewise requires the latest
pointer, immutable graph receipt, and projection to agree on the release, graph
version, source run, projection hash, and recomputed counts. Standalone validation
recompiles the full expected pack and compares every top-level evidence and lineage
collection, rather than treating a recomputed pack self-hash as proof of completeness.


## Batch authorization and execution journal

Track B1's `batch-authorization.schema.json` is an execution-control contract, not a
market or scoring schema. It is restricted to `simulation_only` mode, the
`simulation` provider, the `batch_primary` role, and required
`budget_scope: single_journal_simulation`. Status exposes the same budget scope. The bounded batch retains each
family separately; combining input envelopes never merges market identities or
research obligations. All selected preparations must belong to exactly one schedule
batch and retain its manifest order. Duplicated families/preparations are rejected.

| Binding | Fields and meaning |
| --- | --- |
| Exact inputs | `batch_id`; 2–8 `families` with `family_id`, `preparation_id`, `config_sha256`, `pack_file_sha256`, and `receipt_sha256` |
| Contract versions | `execution_schema_hashes` binds the authorization and execution-event schemas |
| Execution identity | `authorized_by`, `model`, `provider`, `role`, `prompt_sha256` |
| Validity | `valid_from_utc`, `expires_at_utc`; timestamps ending in `Z`, valid from the inclusive start until the exclusive expiry |
| Cost assumptions | `pricing` with integer input/output microdollars per token, plus `pricing_sha256` |
| Budget and work bounds | `max_cost_microusd`, `max_calls`, combined retry/repair `max_retries`, `max_input_tokens`, `max_output_tokens` |
| Coordination | `max_concurrency` must be 1 in B1; `lease_seconds` |

A family pack's content hash and its canonical file-byte hash are different concepts:
`pack_file_sha256` binds the persisted file, including its own metadata hash field.
The authorization must match the exact validated preparation rather than merely a
family label or path. `build_authorization` defaults concurrency to 1; serialized
authorization documents must explicitly contain `max_concurrency: 1`. B1 has one
batch-primary task: one initial request and a linear retry/repair chain. A new
initial request ID cannot bypass that chain or its retry cap. Concurrency 2 is
reserved for a later multi-task scheduler and is rejected here. The prompt hash
is a pinned declaration in this foundation: prompt contents and a production output
schema are not yet supplied or validated.

The `batch-execution-event.schema.json` envelope records sequence, UTC time,
authorization hash, preceding event hash, event kind/data, and event hash. Its event
kinds are `opened`, `reserved`, `dispatched`, `settled`, `unresolved`, and `released`.
An execution directory holds `authorization.json`, append-only `events.jsonl`, and a
process coordination `.lock`. A settled request distinguishes `succeeded` from
`failed`; neither means an accepted research conclusion.
Replay validates both integrity and permitted transitions; hashing alone cannot
legitimize an impossible state or inconsistent budget. The chain detects edits to
retained records and invalid transitions; it is not external proof against a complete
journal rewrite or deletion to a valid prefix. An independently retained receipt must
pin the output hashes and final event hash to establish the accepted journal tip.

Budgets and idempotency apply only within one trusted execution journal. Copying an
authorization into another directory does not share counters. This is not production
spend authority: a shared spent-authorization registry or a deterministic governed
execution namespace is required before any live adapter or paid canary.

Costs use integer microdollars (1,000,000 = USD 1). Reservation precedes dispatch and
is protected by the same process-safe lock as the journal transition. Confirmed cost
plus outstanding reservations and a proposed next reservation must fit the cap.
Attempt identifiers govern idempotent resume. A pre-dispatch reservation may be
released after lease expiry, but its call count is still consumed. Ambiguous
dispatched work remains reserved and cannot receive an automatic retry or refund.
Retry/repair attempts share the global `max_retries` cap and must reference a failed,
settled predecessor or a safely released undispatched predecessor through `retry_of`.
Each uses a fresh request ID and consumes both a call and retry allowance; the chain
cannot fork. A ledger result never constitutes a valid model-output disposition or accepted market event.

The implementation uses fake transport only. Real-provider settlement, model-output
contracts, selective verification, disagreement escalation, and reviewed activation
or no-movement closure remain separate contracts. No live-dispatch CLI is exposed.

## Trusted local registry (Track B2)

A managed registry binds the digest of an exact canonical authorization document to
one canonical journal under its trusted root. This adds local journal selection above
B1; it does not change the authorization's `single_journal_simulation` scope or turn
it into a signed spending grant. The same exact document resolves the same journal
within that registry. Editing the document produces another digest and is outside
the same-authorization guarantee.

| Durable record | Binding and purpose |
| --- | --- |
| `registry.json` | Registry UUID, resolved root path, registry schema and implementation hashes |
| `.lock` | Same-host POSIX coordination for claims and validation |
| `claims/<authorization-digest>.json` | Immutable claim linking the exact authorization to its canonical journal |
| `claims/<authorization-digest>.ready.json` | Receipt written after durable journal initialization |
| `journals/<authorization-digest>/` | B1's canonical authorization, event journal, and per-journal lock |

Initialization requires a new directory beneath an existing parent and writes
metadata last; existing or partially initialized directories are not adopted.
Registry status exposes `registry_id`, `registry_sha256`, `registry_path`,
`managed_budget_scope: single_registry_exact_authorization`, and per-claim journal
paths, call counts, committed/outstanding costs, and event counts. Managed journal
status adds registry identity, managed scope, and journal path to B1 status, while
retaining `budget_scope: single_journal_simulation`. Both remain simulation-only.

The claim is persisted before journal creation; the ready receipt follows durable
initialization. An existing claim without its ready receipt, a missing or partial
claimed journal, or an unclaimed journal at the derived path fails closed. The
registry never automatically adopts or recreates that state. Recovery requires a
future reviewed policy. Fixed paths reject symlinks; no delete or rebind API exists.

The registry lock is released before B1 operations and fake transport. Attempt
serialization and budget arithmetic remain B1's per-journal responsibility. This
same-host local design assumes trusted filesystem state; it provides no guarantee
across different registries, new unsigned authorizations, wholesale state deletion,
or privileged mid-operation filesystem mutation. Production authorization, provider
integration, and spending remain excluded. See
[ADR 0009](../decisions/0009-trusted-local-execution-registry.md).

## Standalone batch-output contract (Track B3)

B3 regenerates its validation context from 2–8 verified V2 family preparations in
one scheduled batch, retaining manifest order. The files
`schemas/batch-primary-output.schema.json` and `prompts/universe/batch-primary-v1.md`
define the `batch-primary-v1` contract. A caller-supplied context is not authoritative.
Request and invocation IDs, prompt/schema bindings, context digest, and byte limits
bind a response to the intended obligations. Request IDs have 1–128 permitted
identifier characters; invocation IDs are `invocation:` plus 24 lowercase hexadecimal
characters. Defaults bound output to 1,000,000 bytes and context to 100,000,000 bytes.
The file validator checks raw file size and canonical JSON output size, rejects
duplicate object keys and nonfinite numbers, and never silently truncates.
Context construction and output
validation are read-only; neither dispatches a model nor changes a journal or graph.

Each family has its own frozen evidence catalog. References bind the family, pack,
JSON pointer, item hash, full evidence value, and subject IDs. A citation must resolve
within the output family's catalog. Every disposition needs supporting evidence
anchored to its own subject; gaps need such support for every affected subject.
Supporting and counterevidence lists cannot overlap. Contextual
material can support reasoning but cannot replace a required identity or candidate
as primary coverage. A candidates-only family may have no identity dispositions.
Required identities and candidates must each receive exactly
one disposition; duplicates, omissions, and extra primary subjects are invalid.

Reasoning uses `fact`, `inference`, `assumption`, or `unknown` with finite confidence
from zero through one. This range check does not calibrate confidence or prove a
claim. Unresolved, provisional, and unknown outcomes require applicable gaps with
retry triggers. An unknown dimension in a referenced proposal also requires an
applicable gap for that disposition. No fixed confidence threshold triggers a gap.
Supplementary gaps may describe required subjects without being referenced by a
disposition; they must still satisfy the same scope, citation, and retry-trigger
checks. Whenever a disposition supplies a gap ID, that gap must name its subject.

Proposals describe all seven operating-identity dimensions: buyer, job-to-be-done,
delivery model, workforce, economics/risk, acquisition universe, and Ambient AI
workflow. Each dimension carries a statement, reasoning label, confidence, and
citations. The `explicit_exclusions` field is required but may be an empty array. Local proposal/gap IDs follow the namespace
supplied by the context, and related graph-market references must resolve within
that family's known graph context. Structural validation cannot establish that a
proposal is supported well enough for acceptance; substantive evidence review
remains necessary.

Disposition-to-proposal cardinality is explicit:

| Subject | Disposition | Proposal references |
| --- | --- | --- |
| Identity | `map_to_proposals`, `provisional_map_to_proposals` | At least one |
| Identity | `no_mapping_to_family`, `non_market_source_identity`, `unresolved` | None |
| Candidate | `adopt`, `change`, `merge_input` | Exactly one |
| Candidate | `split_input` | At least two |
| Candidate | `provisional_map_to_proposals` | At least one |
| Candidate | `reject`, `unresolved` | None |

Every proposal must be referenced by a required disposition in its own family;
an empty proposal list is valid when no disposition maps to a proposal.
`merge_input` is a structural label, not proof that an actual merge is justified or
that multiple required candidates participated. Public validation returns `valid`,
`errors`, `structural_validation_only: true`, and `model_invoked: false`, with the
regenerated context hash when context construction succeeds.

B3 itself is separate from B1/B2 execution settlement. B1 rejects floats anywhere in its
fake response output, while B3 permits finite confidence values. B4 bridges these
contracts through immutable artifacts rather than embedding raw confidence in the
ledger; see [ADR 0011](../decisions/0011-batch-output-artifacts.md). Synthetic validation
does not authorize a real provider, metered canary, score, or market activation.
See [ADR 0010](../decisions/0010-batch-output-contract.md).

## Managed batch-output artifacts (Track B4)

`BatchResearch` bridges the managed registry journal and B3 using fake transport.
Its authorization's existing `prompt_sha256` field must equal
`research_contract_sha256(root=...)`: the canonical digest of artifact kind, raw B3
prompt-file hash, output-schema hash, and output/context byte caps. The bridge checks
this effective contract before claiming a journal, dispatching, and replaying. A
schema or limit change therefore cannot silently reuse an earlier authorization.
B3 context retains its separate raw prompt-file `prompt_sha256`. Context is regenerated from
verified preparations, with an invocation derived deterministically from the
canonical authorization digest and request ID. The bridge does not accept arbitrary
caller-supplied validation context or an alternative execution directory.

The transport receives B3 context and returns `body` as bytes plus `usage` containing
integer `input_tokens` and `output_tokens`. Limits are fixed at 1,000,000 output bytes,
100,000,000 context bytes, and 4,000,000 receipt bytes. Raw confidence-bearing content
is not placed in B1's response envelope.

| Artifact under the managed journal | Purpose |
| --- | --- |
| `research-artifacts/<invocation-hex>/context.json` | Frozen exact context and input bindings |
| `research-artifacts/<invocation-hex>/output.raw` | Exact transport response bytes, including invalid JSON when bounded |
| `research-artifacts/<invocation-hex>/receipt.json` | Validation verdict, usage, ownership, and artifact bindings |

Artifacts are persisted durably and atomically before settlement. The ledger stores
only `kind: batch_research_artifact_v1`, `artifact_path`, `receipt_sha256`,
`output_sha256`, `context_sha256`, and `invocation_id` as its output reference, plus
integer usage accounting. The receipt separately binds registry/authorization/request
identity, exact raw-output and canonical-context file hashes, prompt/schema hashes,
usage/cost, verdict, outcome, and creation time. Its `execution_contract_sha256`
records the effective execution-contract digest; its `prompt_sha256` remains the raw B3
prompt-file hash. `context_sha256` is the context
content digest; `context_file_sha256` hashes its canonical persisted bytes.
B1/B2 schemas and their float prohibition remain unchanged. Missing, altered,
mismatched, or transplanted artifacts fail validation.

Known valid bounded usage is settled even if JSON or structural validation fails;
that attempt is charged and marked failed. Unknown, invalid, or over-limit usage,
oversized raw output, transport failure, or uncertain persistence leaves an
unresolved attempt with its full reservation. No automatic retry or refund follows.
A crash can leave orphan artifacts; their existence does not authorize automatic
settlement, re-dispatch, or research acceptance.

Read-only replay regenerates B3 context and verdict, checks artifact bytes and
ownership, and reconciles every settled B4 reference with the journal. A generic B1
settlement is not a valid B4 artifact receipt. Results distinguish `settled_requests`,
`artifact_valid_requests`, `structurally_valid_outputs`, and `unresolved_requests`.
An empty or unresolved journal can have valid accounting replay with zero validated
artifacts; `valid: true` does not mean every attempt produced a valid output.
Unaccepted `.pending-` directories and orphan artifacts are not automatically
recovered or counted as settled outputs. These counts are not research acceptance. Real
providers, substantive verification, and reviewed family closure remain outside this
contract. See [ADR 0011](../decisions/0011-batch-output-artifacts.md).

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


V2 preparations additionally bind the full verified source-run receipt/artifact map
and exact Turbo Python/executable-schema bytes. Packs retain required NAICS Manual
records and index-absence facts, plus non-owned retrieved candidates as context-only
cards with source records. These fields participate in content identity, size gates,
and deterministic regeneration; they do not alter administrative ownership.
