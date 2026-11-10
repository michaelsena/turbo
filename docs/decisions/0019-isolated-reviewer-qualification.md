# ADR 0019: Isolated reviewer qualification with V2 accounting slots

Status: accepted for implementation; live qualification requires separate authority.
Issue: #69, child of #64.

The reviewer reference representation needs a controlled positive/semantic-negative
comparison. Existing research submissions must not be relabeled under new authority,
and a qualification must not publish research or activate a graph.

Use a separate four-cell packet, external V2 authority and dedicated registry. The
V2 engine enforces physical-attempt accounting; workflow eligibility belongs to its
caller. Its fixed role names permit a second attempt for one role only after a failed
predecessor. Four successful reviewer calls therefore cannot use one role slot.

The qualification protocol explicitly maps its cells to four **accounting slots**:

| Qualification cell | V2 accounting slot |
| --- | --- |
| positive-plain | primary |
| positive-references | verifier |
| negative-plain | escalation_a |
| negative-references | escalation_b |

These slot names are never research judgments. Every transport request uses the
release-reviewer role and canonical reviewer schema. All four cells have the same
model, route, reasoning effort, output limit and token price ceilings. Representation
instructions differ intentionally and are frozen separately. The remaining V2 slots
cannot be invoked through this runner. One attempt per slot and four calls overall
provide one aggregate exposure ceiling; an uncertain attempt blocks further cells.

The qualification kind, mapping, packet digest, request hashes, external rubric,
source provenance, intended canonical registry path and implementation hashes are
bound by the supplied authority. The path binding prevents reusing that authority
in a second fresh registry.
The runner creates no authority and never calls workflow submission/publication APIs.
A fixture builder may use ordinary offline workflow/compiler APIs in a new directory
solely to prepare a mechanically valid semantic-negative fixture.

This avoids both changing the production ledger and adding a multi-authority budget
coordinator. Production provider calls reject the extra qualification execution
contract. The runner rejects production authorities and registries belonging to
another purpose. Local authority files remain trusted operator records, as in V2;
this does not introduce a cryptographic signing or hostile-local-process boundary.

A successful ledger settlement means telemetry and output validity were established,
not that the model made the correct semantic judgment. Independent assessment of
both fixtures remains necessary. No result automatically enables references in
production, publishes artifacts, retries a cell, or increases funding.
