# Universe workload envelope

The read-only report performs no model calls, pack compilation, publication, or writes. Supply
one `--publication-manifest` for each batch activation in the current canonical
graph; duplicate identical manifests are harmless. Missing manifests fail rather
than silently counting published work as remaining.

## Current six-market report

Include both published manifests for the current graph:

```bash
python3 scripts/report-universe-workload.py \
  --publication-manifest data/research_pilots/small-qualification-20261109/publication-manifest.json \
  --publication-manifest data/research_pilots/lease-qualification-20261110/publication-manifest.json
```

The lease manifest references its already-public replay ZIP without extracting or
copying workflow content. Together the two publications account for three families,
12 identity obligations and two candidate obligations. Remaining work is 1,015
families, 8,170 identities and 974 candidates across all 129 original batches.
Ten distinct market-linked or closure-only gap IDs remain unresolved. These are
review-completion counts, not eligibility passes or investment scores.

Supplying only the older manifest still fails with
`publication manifests do not cover current batch activations`. Historical totals
remain tested in a disposable copy pinned to the original five-market release.

## Archive-backed publication manifests

Version 1 manifests retain their existing on-disk artifact format. Version 2 adds
`archived_files`, a map from repository-relative virtual artifact names to objects
with exactly `archive_path`, `member` and `sha256`. The `files` map must bind the ZIP's
exact bytes as well as the on-disk config, closure, activation and release files.
The archive member digest binds its uncompressed bytes. Virtual paths must neither
overlap `files` nor exist on disk; a member cannot have multiple virtual bindings.

Archive paths and members are canonical relative POSIX paths. Absolute paths,
traversal, backslashes, NULs, duplicate entries, symlinks and other special entries
are rejected. Colon-containing preparation names remain valid. The reader ignores
transport restoration locations: nothing is extracted or written. It hashes bounded
archive bytes once and opens those same bytes in memory, then parses selected members
with the existing duplicate-key-rejecting strict JSON decoder.

Limits are eight archives, 256 total entries and virtual references, 16 MiB per
archive, 8 MiB per expanded member, 64 MiB aggregate compressed and expanded bytes,
and a maximum expansion ratio of 200. Only unencrypted stored or deflated ZIP entries
are supported. Every entry's path/type/declared expansion is checked, including
unused entries; selected members additionally undergo bounded decompression, CRC,
size and SHA256 checks. These are defensive transport limits, not research policy.

All existing approval, lineage, closure, schedule and current-activation checks run
unchanged after artifact resolution. The transport inventory alone still cannot
prove publication coverage, nor does a version 2 manifest grant spending authority.

## What the counts mean

The schedule is the obligation baseline. The report verifies current source,
schedule, and graph artifacts, checks family subject uniqueness and counts, and
checks that batch assignments cover the scheduled families exactly once. It then
subtracts reviewed family obligations bound to supplied canonical publications.
These are family/identity/candidate review counts, not counts of new markets.

For that historical five-market published fixture, the schedule contains 1,018 families, 8,182
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
