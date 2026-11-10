# Replaying the published small qualification

The canonical graph includes the original pilot and two provisional mining markets:
five markets, eight mappings, thirteen active events. This is a compact workflow
qualification, not a completed universe or a universe-wide cost/quality result.

## Durable evidence and derived publication

The [bundle](../../data/research_pilots/small-qualification-20261109/README.md) retains
all six accepted workflow JSON files and both preparation packs without rewriting
plans, prompts, evidence, or approvals. The input commit was originally local-only;
the hash-bound Git-object capsule reconstructs that exact commit/tree. Each imported
object must match its Git SHA-1; the capsule itself is bound by SHA-256 in the manifest.
Shared objects are part of the published source tree. No credentials or provider
account records belong in this bundle.

Activation was regenerated under the exact original clean compiler commit
`b1bc4787a13e101c9088982fed48814a7fa6e4a6`. Its workflow locator changed, producing a
new activation configuration hash. Approved events, activation ID, preview, review,
and activation projection stayed identical. The cumulative graph was then generated
from published source commit `de04aca6da6735eceae5e8ddec2cbec31c0a732a`, which contains
the durable configuration and activation. Its new release and closure are derived
records; the earlier staging receipt remains historical and unchanged.

## Exact-path restoration

The historical compiler binds an absolute workflow path. Exact receipt replay therefore
requires `/private/tmp/turbo-published-small-qualification/workflow`. This is a
recorded compatibility requirement, not arbitrary-path portability. On macOS `/tmp`
resolves to `/private/tmp`. On another system, use an isolated environment where this
recorded path is writable. The read API can display the committed projection without
restoring research inputs; full research replay requires restoration.

From a fresh checkout with Python dependencies installed:

```bash
PYTHONPATH=src python3 scripts/replay-small-qualification.py   --restore   --runtime-root /private/tmp/turbo-published-small-qualification   --input-root /tmp/turbo-small-publication-frozen-input
```

Restoration is explicit. The helper verifies all manifest files before copying,
refuses symlinks or differing existing workflow files, and never overwrites them.
It clones the current repository locally when the supplied input directory is absent,
imports verified frozen-input objects into that clone, and checks out the exact input
commit. It creates only the required empty workflow lock beside immutable JSON files.
No model, network research, automatic retry, or account operation is performed.

Repeat without `--restore` to verify existing reconstruction:

```bash
PYTHONPATH=src python3 scripts/replay-small-qualification.py   --input-root /tmp/turbo-small-publication-frozen-input
```

The helper passes explicit frozen-input/preparation locations to the unchanged graph
and closure validators. Success requires both validators to pass. A mismatched file,
missing required object, moved input tree, wrong locator, or missing exact approval
fails verification. Do not delete a conflicting runtime directory to force success;
inspect the conflict or use an isolated replay environment.

The historical `canonical-universe-v1.json` and pilot release remain available.
The current pointer selects `graph-release-a09c97692a785c2a9711`, generated from
`canonical-universe-small-qualification-v1.json`. Retain the complete closure to keep
the candidate-only gap visible alongside the four market-linked gaps.
