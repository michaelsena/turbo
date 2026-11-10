# Frozen supplemental evidence for managed family research

[ADR 0022](../decisions/0022-frozen-family-supplemental-evidence.md) records the input-provenance decision.

Supplemental evidence gives the existing managed family workflow explicit operating
research inputs. It changes neither the scheduled family's required obligations nor
the primary, selective verifier, conditional blind escalation/adjudication, exact
release review, and publication sequence. It creates no canonical market, Target
eligibility, or evaluation score by itself.

Use an optional `family-supplement-v1.schema.json` manifest committed inside the
frozen input checkout. Bind one existing `family_id` and the schedule's exact
`source_run_id`. Keep source bytes and researcher claims separate:

| Manifest field | Meaning and checks |
| --- | --- |
| `sources` | Repository-relative UTF-8 file, exact SHA-256, original public URL, explicit UTC retrieval time, representation, and existing family subject IDs |
| `representation` | `full_text`, `excerpt`, or `excerpt_with_paraphrase`; the last explicitly contains researcher interpretation and is not wholly verbatim |
| `claims` | Researcher text labeled `fact`, `inference`, `assumption`, or `unknown`; exact source/gap references and subject bindings |
| `gaps` | Unresolved research questions bound to the same existing subjects |

`fact` and `inference` require linked sources. `assumption` and `unknown` require
linked gaps. The label `fact` is the researcher's assertion, **not compiler-certified
truth**. All admitted claims carry this warning. Source and claim support must still
be judged in research and independent release review. A checksum proves selected
bytes, not the accuracy of an excerpt, paraphrase, or claim.

Every referenced subject must already be a required or context identity, or an owned
prior candidate, of this family. Supplemental context cannot make an unrelated prior
candidate an owned disposition, change administrative ownership, or force a requested
market to exist. Existing source sections and full coverage remain intact.

## Prepare, replay, then authorize

Commit the reviewed source files and manifest with the runtime before preparing a
fresh work unit. Do not edit a prior prepared pack or reuse authority from another
frozen source tree.

```sh
python -m turbo.cli family-dry-run family:naics-2022:531390 \
  --supplemental-manifest data/research/lease/manifest.json
python -m turbo.cli family-prepare family:naics-2022:531390 \
  --supplemental-manifest data/research/lease/manifest.json \
  --output-root /absolute/fresh-preparations
python -m turbo.cli family-validate-preparation /absolute/fresh-preparations/PREPARATION_ID
```

The equivalent Python APIs accept `supplemental_manifest=Path(...)`. Paths resolve
against the frozen input root, not the output directory. The manifest's bytes/hash
are bound in the generated configuration. Each source's exact bytes and all claims
and gaps are regenerated during preparation validation. Missing, changed, duplicate,
unselected, malformed, or symlinked inputs fail closed. A caller cannot inject a
prepared supplemental card and recompute its hash to bypass original-source replay.

The batch evidence catalog gives sources, claims, and gaps their own typed JSON
pointers and content-bound evidence IDs. The existing batch output contract remains
unchanged; no canonical IDs or failed model answers are repaired by this feature.
When no manifest is supplied, supplemental fields are absent and the existing
preparation/document shape is unchanged. Code/schema hashes still change with a
new runtime, so old preparations remain on their original frozen runtime.

The initial association-management and lease-administration research files remain
draft inputs until their provenance and source support are independently reviewed.
After admission, measure the exact model request and context capacity before any
call; adding evidence does not solve a context-window limit. See the existing
[controller guide](batch-controller.md) for governed execution and explicit release.
