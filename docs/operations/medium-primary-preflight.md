# Medium primary admission decision

Later execution outcome: the approved larger admission envelope allowed one
primary attempt, which [failed acceptance](medium-primary-result.md). The historical
preflight below remains unchanged; no downstream call or publication followed.

Issue [68](https://github.com/michaelsena/turbo/issues/68) prepares a decision, not
execution authority. **The existing medium pair remains blocked.** It contains
38 required identities, one required candidate, and 1,304 evidence items. The
plain request is 1,718,379 serialized bytes; the unchanged managed admission rule
adds 4,096, requiring a 1,722,475 input ceiling. The supplied primary ceiling is
230,000. No cap is changed by this work. The [public preflight receipt](receipts/2026-11-10-medium-primary-preflight.json) records the exact replay and separate gates.

## Reproduce the decision

Run from the current repository, with the original frozen input checkout and
workflow available. The command runs the frozen implementation's existing
assignment replay for only these two preparations, then constructs the exact
plain primary provider request. It makes no provider call, creates no authority,
changes no workflow artifacts, and prints diagnostics to standard output.

```bash
python3 scripts/preflight-medium-primary.py \
  --input-root /tmp/turbo-medium-input \
  --workflow /tmp/turbo-medium-qualification/workflow \
  --roles /tmp/turbo-medium-qualification/role-proposal.json \
  --model-metadata /tmp/turbo-medium-qualification/model-metadata.json
```

These local paths are qualification inputs, not committed fixtures. Restore them
with their original frozen checkout and preparation bindings; do not substitute
the latest compiler into an old workflow. Before importing frozen code, the helper
requires its exact Git toplevel, matching HEAD tree, and no tracked or untracked
changes; it records the actual commit. Failed replay stops the command. The
receipt binds the workflow plan, input tree, context, assignment, request builder,
role prompt/schema, role configuration, and supplied model metadata. It preserves
the original full families and evidence. The fixed-length invocation placeholder
matches managed admission sizing; it does not create an invocation.

## Three separate checks

| Check | Current result | Meaning |
|---|---|---|
| Managed admission | Fails: 1,722,475 versus 230,000 | Exact request exceeds supplied ceiling |
| Output constraint | 32,000 is within reported 128,000 | Snapshot comparison only |
| Context constraint | 1,754,475 conservative input-plus-output versus reported 1,050,000 | Fit is unproven; actual overflow is not established |

The cached model metadata has no trustworthy retrieval timestamp or provenance
envelope. Its filesystem modification time is not retrieval evidence. The helper
therefore reports `supplied_snapshot_unverified`, keeps `retrieved_at` null, and
never treats its top-provider limits as verified limits for the routed endpoint.
An optional `--metadata-observed-at` records only the operator's observation time.
It does not upgrade this provenance. Fresh routed-model facts are still needed
before an execution decision.

The admission bound uses UTF-8 request bytes as a conservative token upper bound;
it is not actual tokenization or a cost forecast. No verified model-specific
request tokenizer is available in this qualification. Even a credible advisory
estimate would not replace the managed byte-bound gate without a separately
reviewed accounting change. A context upper bound exceeding the advertised window
means this proof cannot establish fit; it does not prove the real request is too
large. Conversely, a bound fitting supplied metadata does not establish current
endpoint availability, authority, or research quality.

Prior separate representation measurements remain diagnostic: the existing
reversible view has a 1,065,794 admission bound, and readable references have a
1,588,156 bound. Neither fits 230,000; neither supplies conservative context-fit
proof with the current output allowance. Readable execution is reviewer-only.
This task does not change representation, model, evidence scope, or admission rules.

## Qualification proposal and stopping points

A one-call primary-only journal is the smallest measurement experiment but is
**not recommended as the path to completed coverage**. It exhausts `max_calls=1`;
a fresh ordinary authorization cannot inherit an accepted primary from a different
journal. It may force repeated research. No successor mechanism is added here.
Such a diagnostic would remain incomplete research, without verifier, independent
review, closure, or publication.

The useful resumable alternative uses the existing six-role workflow with one
attempt per role, at most six calls, concurrency one, no automatic retries or
fallbacks, and one unchanged trusted authorization/journal. An operator pauses
after the single primary attempt. This preserves the established primary,
selective verifier, conditional two-blind escalation/adjudication, and independent
release-review architecture. A fresh authorization would need to bind the exact
workflow, frozen execution contracts, role settings, time window and explicit
budget; no authorization is created here.

Before any primary dispatch, establish reliable routed-model context/output fit
and a compatible explicit admission/reservation envelope. The present proposal
remains blocked at that prerequisite. Do not manufacture a fitting input ceiling
by changing a cap in this report.

After a future authorized primary, stop on rejected or invalid output, ambiguous
transport, unknown usage/cost, exhausted authority, or any missing provenance.
Retain the managed reservation as required; do not retry automatically. Even on a
valid result, pause and measure the exact next eligible request using that result.
Continue in the same journal only if its existing role and shared limits admit the
request and sufficient unexpired authority remains. Otherwise stop; changing
budgets is not an implicit continuation permission.

Downstream request sizes depend on actual primary and verification outputs;
escalation depends on substantive findings. Neither complete-path admission nor
whole-workflow affordability is established. A six-call cap permits a bounded
path but does not guarantee that all six requests will fit or that six calls will
complete valid research. An authority that expires or lacks downstream capacity
can still strand work; the GM must assess that risk before proposing execution.

## Private reservation arithmetic

Add `--private-budget` only for a private diagnostic. It reports the supplied
primary reservation and the hypothetical minimum reservation needed by the
unchanged request-size rule, using the existing integer formula:

`max_input_tokens × input_price_ceiling + max_output_tokens × output_price_ceiling`

This is bounded exposure, not expected spend, a price quote, available account
funds, or authorization. The hypothetical calculation does not alter any limits.
A resumable six-role authority must cover the chosen shared maximum exposure;
request sizes and actual charges remain unknown until measured. Keep private
proposal arithmetic and account information out of public receipts and GitHub.

## Later advisory evidence: 2026-11-10 13:09 UTC

This section supplements the historical preflight above; it does not rewrite that
receipt or change admission. The later [advisory token receipt](receipts/2026-11-10-medium-advisory-token-count.json)
records a pinned offline tokenization experiment and a fresh, retained
[public endpoint response](receipts/2026-11-10-medium-openai-endpoint-response.json).
The endpoint response was retrieved at `2026-11-10T13:09:24.439095+00:00` from
`https://openrouter.ai/api/v1/models/openai/gpt-5.6-luna/endpoints`. Selecting the
exact `openai` tag, excluding `openai/fast` and `openai/flex`, reports a 922,000-token
prompt limit, 1,050,000-token context, and 128,000-token maximum completion.
The raw response is retained beside its SHA-256 receipt. These are dated endpoint
facts, not a promise of future availability or an account-specific price quote.

The measurement uses `tiktoken==0.14.0` installed only in a temporary environment.
The installed `model.py` exactly matches the SHA-256 of the
[official release source](https://github.com/openai/tiktoken/blob/0.14.0/tiktoken/model.py),
whose `gpt-5` prefix maps to `o200k_base`. The wheel hash and official vocabulary
hash are pinned in the receipt. The
[OpenAI CLI tokenizer documentation](https://github.com/openai/openai-cli/blob/main/docs/local-utilities.md)
also identifies GPT-5.x with `o200k_base`; its source snapshot hash and retrieval
UTC are recorded. Prefix recognition alone does not establish a particular routed
provider's tokenizer or hidden prompt format.

The exact frozen primary replay produced the same request SHA-256 as the earlier
byte measurement: `7ac11b69b11a0122ee3ffb65ff8fc1b074272f96c394e85a02b3441be0f07afc`.
Every component is tokenized as one complete string with `encode_ordinary`, without
chunking, normalization, or assumed special/chat tokens. JSON components use the
same canonical UTF-8 serialization as the request builder.

| Measured component | Ordinary-text tokens |
|---|---:|
| Actual user-message content, including prompt and full assignment | 547,015 |
| Full response-format JSON, including the schema | 2,892 |
| Sum of those two separately tokenized components | 549,907 |
| Entire serialized wire JSON, separately tokenized | 566,631 |

The two totals are alternative diagnostics, **not quantities to add together**.
The first sums actual user content and canonical response-format JSON. The second
also includes transport serialization and JSON escaping, which the provider does
not necessarily present to the model. Neither is an exact provider input count.
Unknown message framing, hidden wrappers, schema transformations and special-token
handling prevent that claim; component token boundaries also differ from a combined
provider prompt.

Relative to the reported prompt limit, the respective advisory headrooms are
372,093 and 355,369 tokens. Including the configured 32,000 output allowance leaves
468,093 and 451,369 tokens against the reported context limit. These differences
show how much additional overhead each proxy could tolerate; they do not establish
an upper bound on hidden overhead. They support practical fit as an inference,
not proof of context fit, usage, cost, or research quality.

The **managed gate is unchanged**: 1,722,475 byte-bound units exceed the supplied
230,000 ceiling. No tokenizer estimate was substituted for that gate, no repository
dependency was added, and no paid call or new authority was created. Any next
execution decision must explicitly reconcile its admission/reservation envelope
with these advisory observations and retain the same-journal stopping conditions
above. Downstream request sizes remain unknown until actual outputs exist.
