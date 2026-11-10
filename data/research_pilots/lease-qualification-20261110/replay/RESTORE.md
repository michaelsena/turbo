# Exact canonical lease research replay

This transport contains only the six accepted workflow JSON files, three immutable
preparation JSON files, the standard source-object pack, and its unchanged manifest
and source-only restoration note. `transport-manifest.json` binds all 12 ZIP entries,
their byte sizes and SHA-256 hashes, and the nine original JSON restoration paths.
The archive is 614,379 bytes, SHA-256
`351fb82a7caf362e74f92401f470912d050bc17aa910d15ac75abf66512c22ed`.

The accepted submissions are canonical research records. They are not raw provider
responses. No account registry, authorization, cost record, failed submission,
private dispatch wrapper, environment file, or credential is included. The source
pack includes ordinary historical runtime source needed for exact tree identity;
it contains no account credentials. The plan retains its original statement that
spend telemetry is unavailable and not claimed.

## Restore without changing recorded identities

Use a fresh full public Git clone containing PR98 and the final lease publication,
with Python dependencies installed. The source commit named by the final lease
graph receipt must be available in that clone. Use a dedicated environment where
the exact `/private/tmp/...` paths below are writable. Never overwrite a differing
existing file or checkout; stop and inspect the collision instead.

1. Verify the ZIP SHA-256 against the adjacent transport manifest. Inspect its
   inventory: exactly 12 regular entries, no absolute archive names, no `..` path
   components, no symlinks or duplicate entries. Extract into a new staging folder
   using standard ZIP tools. Verify every extracted byte size and SHA-256 against
   `transport-manifest.json` before restoring original locations.
2. Verify `source-restoration/turbo-service-source-minimal.pack` against the
   unchanged `turbo-service-minimal-SHA256.json` (138,906 bytes,
   SHA-256 `dd4abf56b74b56f73f65a61d8013dd1f24d9bbe0bc6d50126cc6c719eeb53d41`).
   Import it into the public clone with
   `git -C /path/to/public-clone index-pack --stdin < /path/to/extracted/source-restoration/turbo-service-source-minimal.pack`.
   Git verifies the object identities. This restores the exact detached historical
   source objects; it intentionally does not invent missing ancestor history.
3. Run the existing published small-qualification helper from that public clone:

   ```sh
   PYTHONPATH=src python3 scripts/replay-small-qualification.py --restore --runtime-root /private/tmp/turbo-published-small-qualification --input-root /private/tmp/turbo-parity-input
   ```

   It verifies published artifacts and restores its workflow and exact historical
   input `e9e7c4c93bfb601bac4a0368cde20fda40044321`, tree
   `4f2262909ab60f99e4a4eb5e06bcaf77806e48fa`. Both returned validators must pass.
4. Copy the two already-public preparation directories from
   `data/research_pilots/small-qualification-20261109/preparations/` byte-for-byte to
   `/private/tmp/turbo-small-qualification-compact/preparations/`, retaining the
   names `family-preparation:912826dc158672ffe1422048` and
   `family-preparation:8e9567722ad643e5177e97b8`. Validate their three files against
   the existing small-qualification publication manifest. These original paths are
   necessary because cumulative replay must use each workflow's recorded inputs.
5. Create a separate no-checkout local clone of the public clone at the absent path
   `/private/tmp/turbo-service-qualified-v2` using `git clone --local --no-hardlinks --no-checkout`.
   Import the same source pack into that clone, then check out detached
   `f5fcbbd82c0fd5b847b26be96ac2a65522ef308a`. Verify its tree is exactly
   `c3e3db157f4b9e0c04b38527c4d2f24005fb5ce8` and its worktree is clean.
6. Restore the six extracted `workflow/*.json` files byte-for-byte to
   `/private/tmp/turbo-service-qualified-v2-ember/workflow/`. Restore the three
   extracted preparation files to
   `/private/tmp/turbo-service-qualified-v2-run/preparations/family-preparation:7e7d6b8b53a5730ee7368ffc/`.
   Check each destination against the transport manifest. Create only an empty
   `.lock` file in each restored workflow if absent. Do not change plans, actor
   identities, source paths, accepted submissions, previews, or reviews.
7. From the final public checkout, validate its committed lease graph and closure
   using `graph_release.validate_graph_release` and
   `batch_closure.validate_batch_closure`, passing `root` as the resolved public
   checkout and the committed config/release/closure paths. The workflow argument
   is `/private/tmp/turbo-service-qualified-v2-ember/workflow`. Do not pass global
   `input_root` or `preparation_dirs` overrides. Require both validators' `valid`
   fields to be true. The expected graph is six markets and nine mappings; the
   added lease market and mapping remain provisional.

Replay validates existing graph and closure artifacts; it does not invoke models,
contact providers, recreate spending authority, or promote a new graph pointer.
The legacy receipt source SHA must remain exact, even when another commit has the
same tree. This archive was hash-checked and restored into isolated scratch staging;
that transport check alone is not a claim of complete clean-environment graph replay.
