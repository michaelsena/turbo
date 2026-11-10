# ADR 0020: Explicit publication with immutable staging and a source-commit boundary

Status: independently reviewed implementation for issue #70; integration validation
is required before deployment.

Independent review authorizes one exact semantic preview. Publication must preserve
that review and its frozen compiler contract while deriving activation, cumulative
graph and closure artifacts. It cannot manufacture semantic decisions, rebase an
approval onto a changed graph, or start another workflow.

An explicit controller publication command binds its configuration, original
canonical pointer, exact preview/reviewer hashes, implementation, and deterministic
activation/configuration in immutable records also bound in the trusted registry.
Existing deterministic artifacts are reused only after exact compiler validation.
Missing or changed bindings and ambiguous partial writes stop for reconciliation.

Activation persistence requires the exact clean reviewed execution commit. Its
versioned artifacts then make that checkout dirty. The controller therefore stops
at `WAITING_PUBLICATION_SOURCE_COMMIT`; the GM commits the exact activation and
cumulative graph configuration. The controller never creates that commit. Resume
requires a clean source commit containing only those additions and records its
identity and source hashes in an immutable supplement.

The unchanged graph writer stages its output using a private pointer. Closure is
compiled and validated against that persisted cumulative graph before canonical
promotion. Completion requires validated graph, closure and pointer relationships,
then an immutable completion receipt. A no-movement decision completes a validated
closure against the unchanged graph; it does not claim a new activation.

Historical cumulative activations retain their own recorded input/preparation
locations. Missing historical restoration is an explicit replay failure, not license
to substitute the newest batch's frozen inputs. Compiler files already hashed into
accepted previews are not edited to add orchestration or locking.

Canonical promotion uses a shared writer lock and expected-base check across the
CLI and controller entrypoints, implemented in a separate graph-publication module.
The lock lives in Git metadata and does not dirty the compiler source checkout.
Staged graph/closure/source files and their directories are synchronized before the
atomic canonical pointer replacement. Exact repeated targets are validated no-ops.
The historical low-level graph writer retains its approved bytes and is restricted
operationally to private staging pointers. Direct external file edits and old
unguarded library callers remain outside the supported concurrent-writer contract;
they must not run alongside publication. No blanket compiler hash exemption is added.

`COMPLETE` is local validated publication, not a claim of a final Git commit or
GitHub push. The GM retains final artifact review/commit/publication and clean
next-input freeze. The immutable receipt identifies local artifacts and source
provenance without asserting repository durability that has not occurred.
