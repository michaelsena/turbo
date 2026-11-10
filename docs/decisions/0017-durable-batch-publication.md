# ADR 0017: Preserve approval while publishing durable batch artifacts

Status: accepted for the small-qualification publication implementation.

The independent reviewer approved a preview whose compiler hashes and execution
commit are immutable. Its historical activation format binds an absolute workflow
path. Changing the compiler solely to relocate that workflow would change the
approved contract; changing old receipts would hide provenance.

Preserve accepted workflow and preparation bytes in the repository. Regenerate
activation configuration and downstream cumulative release/closure as new derived
records, retaining the approved events, preview, review, and original staging receipt.
The new source commit must contain the publication configuration and activation.

Exact replay restores the recorded workflow locator with explicit operator action;
it verifies every source file, refuses collisions, and invokes the unchanged graph
and closure validators. A hash-bound Git-object capsule preserves the originally
local-only frozen input commit; objects are verified before import into a separate
input checkout. This makes reconstruction independent of the original temporary
research directories, but does not claim arbitrary-path receipt portability.

The read API serves committed verified projections without restoring research inputs.
Future arbitrary-location replay requires a separately reviewed transport contract.
No new model call or changed research judgment is authorized by publication.
