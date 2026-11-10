# ADR 0022: Admit operating evidence through frozen family inputs

- Status: implementation review for issue #90
- Date: 2026-11-10

## Decision

The existing managed family preparation may explicitly bind one optional supplemental
manifest from its frozen input checkout. The manifest separates immutable source
representations, researcher claims, and open questions. Every entry binds subjects
already present in that family's required or context scope; no supplemental entry
creates ownership or a new required disposition.

Preparation replay verifies the manifest hash, source file hashes, family/source-run
bindings, references, and full regenerated content. Supplemental entries receive
content-bound catalog references alongside the complete original evidence. Default
preparations omit these optional fields. Historical preparations keep their frozen
implementation; they are not silently migrated.

A source checksum establishes provenance, not truth. Excerpts with paraphrases must
be labeled as such. Researcher `fact` and `inference` claims require source references;
`assumption` and `unknown` claims require unresolved questions. All claims remain
unreviewed inputs until the existing research and independent review establish their
support. The compiler does not certify semantic validity or a requested market's
existence.

## Consequences

Operating research can reach the real batch harness without editing prepared packs,
injecting candidate ownership, changing the schedule, or creating a parallel pilot.
The primary/selective-verifier/conditional-escalation/exact-release-review sequence,
ledger, and explicit publication gate are unchanged. Preparation success cannot
stand in for canonical acceptance, Target eligibility, or scoring.

All original evidence remains available, so context capacity and exact request
admission must still be checked. Evidence admission does not authorize truncation or
another paid call. See the [operating guide](../operations/family-supplemental-evidence.md)
for the manifest contract and replay commands.
