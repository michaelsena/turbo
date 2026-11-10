# Universe workload envelope

Run the read-only report from the repository root:

```bash
python3 scripts/report-universe-workload.py \
  --publication-manifest data/research_pilots/small-qualification-20261109/publication-manifest.json
```

The command performs no model calls, pack compilation, publication, or writes. Supply
one `--publication-manifest` for each batch activation in the current canonical
graph; duplicate identical manifests are harmless. Missing manifests fail rather
than silently counting published work as remaining.

## What the counts mean

The schedule is the obligation baseline. The report verifies current source,
schedule, and graph artifacts, checks family subject uniqueness and counts, and
checks that batch assignments cover the scheduled families exactly once. It then
subtracts reviewed family obligations bound to supplied canonical publications.
These are family/identity/candidate review counts, not counts of new markets.

For the current published fixture, the schedule contains 1,018 families, 8,182
identity obligations, and 976 candidate obligations in 129 batches. The two
published mining family closures account for eight identity obligations and one
candidate obligation. This leaves 1,016 families, 8,174 identities, and 975
candidates; all 129 original batches still contain remaining work. The separate
original regression family is not queued work and is not subtracted again.

Completion does not resolve evidence gaps. Market-linked and closure-only gaps
are retained separately and combined by exact gap ID. Candidate-only gaps remain
visible. A retry-required outcome never counts as completed. Conflicting closures
for the same family, or conflicting contents under the same gap ID, fail closed.
Identical repeated closures count once.

## Validation boundary

The declared mode is
`published_artifact_binding_verification_not_fresh_research_replay`.
This is a **published activated-closure overlay**, not a universal workflow progress
tracker and not a new evaluation of research quality. Hashes establish artifact
consistency; they do not authenticate an external author or replace independent
research review.

The report checks manifest file hashes; workflow/context and upstream submission
hashes; the review schema and approved preview; final research lineage; exact
schedule receipt, partition, source and subject bindings; closure content address;
and the historical release's activation in the current graph. Approved events and
reviewed market/mapping rows must still be present unchanged in the current graph.
The historical mutable latest-graph locator is excluded from manifest file checks;
the selected current graph is independently verified instead.

Unsupported unanchored no-movement or retry-only publications fail explicitly.
Future support requires a declared full-workflow replay validation mode before
such closures can contribute coverage. Research outputs alone never contribute
completed coverage. Subsequent legitimate market supersession can also make this
strict overlay fail; extending it requires explicit lineage-aware validation.

## Optional scenarios

No cost or duration forecast appears by default. `--scenario path/to/scenario.json`
accepts exactly these explicit assumptions:

```json
{
  "escalation_fraction": "0.25",
  "seconds_per_call": "10",
  "concurrency": 1,
  "cost_units_per_call": "1",
  "cost_unit": "hypothetical units"
}
```

These illustrative values are not measured estimates. The scenario uses three
routine calls per remaining batch, plus three additional calls per escalated
batch, retaining the existing primary/selective-verifier/conditional-blind-and-
adjudicator/independent-review process. Concurrency must be one or two. Idealized
time divides call time by concurrency; it excludes preparation, publication,
failures, retries, role-size variation and qualification. Fractional expected call
counts represent an expectation, not an executable call schedule.

A credible forecast still needs representative request/output sizes, review
amplification, escalation and failure rates, and role latency across workload
strata. The report supplies batch identity-size histograms and family kinds to
help select those samples. It does not extrapolate compact-family costs to the
full universe and contains no account balances or private financial data.
