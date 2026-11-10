# Isolated reviewer qualification

Issue #69 provides a separate four-cell qualification path for reviewer references.
It is not a production workflow run. Nothing is enabled automatically, and neither
the fixture builder nor the runner creates spending authority.

## Build and inspect offline

Use a new directory, the accepted small workflow, its frozen input checkout and a
JSON document containing the proposed reviewer role settings. Explicit preparation
paths can point to the durable published preparation artifacts.

```bash
PYTHONPATH=src python scripts/build-reviewer-qualification.py \
  --destination /tmp/reviewer-qualification-bundle \
  --source-workflow /tmp/turbo-published-small-qualification/workflow \
  --input-root /tmp/reviewer-frozen-input \
  --reviewer-config /tmp/reviewer-role-settings.json

PYTHONPATH=src python scripts/run-reviewer-qualification.py \
  --bundle /tmp/reviewer-qualification-bundle \
  --registry /tmp/dedicated-qualification-registry
```

The builder pins the positive to the accepted small compiler-preview hash. It copies
plan/context into a separate negative workflow and changes exactly the Industrial
Sand proposal's job statement to water-resource construction, which the frozen
source excludes. The original fact label, confidence and evidence IDs remain.
Ordinary offline submission validation recomputes the primary envelope and verifier
input hash; the compiler regenerates a coherent negative preview. Original verifier
agreement is deliberately retained as **synthetic agreement**, not a new judgment.
Original accepted artifacts are never edited, and the accepted reviewer answer is
not included in either request.

The packet contains four independent requests: positive/negative × plain/references.
Their paired canonical assignments match exactly. Model, route, schema, reasoning
and output limit are shared; reference-specific instructions differ intentionally.
The rubric is an external artifact, hash-bound but never included in model inputs.
The expected negative finding is a material operating-identity contradiction, not a
schema or stale-hash error. The positive's expected approval remains subject to
independent adjudication of any unexpected evidence-backed finding.

## Separate authority and execution

Read-only preflight returns the packet digest, required execution contracts and
role bindings, exact request sizes plus the existing 4,096 admission allowance,
and reservation arithmetic. Supply the intended `--registry` to obtain its canonical
path binding before constructing authority; bundle inspection without that path
explicitly reports that the binding is still required. The same authority cannot
be reused at a different registry path. A trusted operator must separately supply a V2
authorization with those exact bindings, `max_calls=4`, one attempt per accounting
slot, a finite validity window, and the reported aggregate reservation. Role bindings
must be used exactly: the prompt digest binds each cell's rendered runtime text.
The frozen settings' price ceilings are reservation bounds, not predicted spend or
an account balance. Authority files and account metadata do not belong in GitHub.

The unusual accounting-slot labels are documented in
[ADR 0019](../decisions/0019-isolated-reviewer-qualification.md). Actual model role is
always release reviewer. The production provider cannot accept this qualification
authority, and this runner never submits or activates research.

After separate explicit bounded approval, run one exact cell at a time:

```bash
PYTHONPATH=src python scripts/run-reviewer-qualification.py \
  --bundle /tmp/reviewer-qualification-bundle \
  --authority /tmp/qualification-authority.json \
  --registry /tmp/dedicated-qualification-registry \
  --cell positive-plain --execute
```

The API key is read from `OPENROUTER_API_KEY`; never put it in command arguments or
artifacts. Omitting `--execute` is read-only. No looping, automatic retries, authority
creation, funding changes, or publication occurs. Cells are fixed and cannot be
renamed, added or remapped under the existing authority. The runner exclusively owns
its registry. It records cell and accounting slot together in requests, responses
and results. Requests and response contents are immutable local artifacts, while
settlement and held exposure use the unchanged V2 journal.

Unknown usage/cost, transport failure, or interrupted dispatch remains reserved;
other cells are blocked and restart never resends the original attempt. Known invalid
schema, wrong preview/upstream hashes or unknown literal evidence IDs are settled as
charged failures. Literal evidence references are checked against the frozen catalog;
prose claims and semantic correctness still require an independent reviewer.

## Assess without enabling production

```bash
PYTHONPATH=src python scripts/run-reviewer-qualification.py \
  --bundle /tmp/reviewer-qualification-bundle \
  --authority /tmp/qualification-authority.json \
  --registry /tmp/dedicated-qualification-registry --report
```

The report replays the journal and validates fixed cell/slot/request bindings,
registry ownership, settled artifact hashes, raw body hashes, canonical documents
and their validation outcome without writing. It exposes raw canonical documents and execution status, not an automatic
quality verdict. Retain any uncertain raw response artifact for manual inspection;
an unresolved response never becomes accepted research or released exposure.

An independent blinded comparison must check the predetermined negative contradiction,
exact preview/evidence references and mandatory checks, and adjudicate unexpected
positive findings. A missed material finding blocks adoption. Four cells on one
positive and one deliberately contradictory negative establish neither broad quality
equivalence nor generalized savings. Actual usage, latency and cost can be reported
only after separately authorized calls. Software tests use synthetic transports and
are not model-quality evidence.
