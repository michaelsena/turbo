# Native service boundary preflight (#85)

These offline drafts use the original boundary harness and canonical activation path.
They do not create accepted markets, close scheduler work, authorize execution, or
inject the separate service research packs. The source run is
`run-2ea0f00db84148de663f`; the exact starting tree and deterministic rebuild results
are in [the receipt](native-service-preflight-receipt.json).

## Preregistered questions and complete scope

Association management: does the source evidence support a distinct outsourced
HOA/condominium management operating market, and where does it separate from the
association entity and other property managers? Start at Residential Property
Managers (`531311`), retain every direct linked product, and require explicit
reconciliation of `candidate-market:75a899ee94891cab2fa004b6`. Context includes
`813990`, `531312`, and `561110`. A supported difference in buyer, workflow,
delivery, labor, economics, acquisition universe, or AI work changes the proposed
boundary; weak evidence must remain a gap or provisional outcome.

Lease administration: does a distinct outsourced occupier-side lease
administration/audit market exist within or adjacent to other real estate services?
Start at Other Activities Related to Real Estate (`531390`), whose source definition
excludes property management, brokerage, lessors, and appraisal. This is a boundary
hypothesis, not an official classification of the candidate. Retain every direct
linked product and require `candidate-market:f4f2acb8f7469f250ed2eb00` reconciliation.
`531312`, `531311`, `531210`, `561110`, and `541219` provide context-only neighbors.
Evidence establishing landlord-side property management or broader office/accounting
administration would change or reject the proposed boundary.

| Draft | Required identities | Required candidate dispositions | Evidence | Specialist wire bytes |
|---|---:|---:|---:|---:|
| Association management | 54 | 131 | 452 | 748462 |
| Lease administration | 47 | 111 | 394 | 667760 |

All retrieved candidates require dispositions under the original runtime contract.
The small owned-family scheduler counts are not these full linked-product counts.
Existing candidate ownership remains unchanged; targeted candidate inclusion is a
family-local hypothesis, not global reassignment or proof of schedule completion.

## Execution proposal and limits

Draft all three research roles use `openai/gpt-5.6-luna`, high reasoning, a 32000-token
completion ceiling, one transport attempt, zero validation repairs, and no fallback.
These settings are proposals, not evidence of output sufficiency or model qualification
on these new packs. Each family uses two independent blind specialists followed by
one adjudicator only after both validate. Each then needs its separately configured
independent review, exact activation replay, and cumulative graph release before use
as a canonical market. No filtering or factor scoring belongs in these calls.

The specialist wire measurements exactly render the native builder with an
identical-length placeholder random invocation ID. Adjudicator measurements in the
receipt are only base lower bounds because the two actual validated outputs do not
exist yet. Bytes are not provider tokens. This receipt makes no dollar-reservation,
context-fit, runtime, output-sufficiency, or full-completion claim.

The original runner has no shared dollar authority/reservation journal, no pinned
provider routing parameter, and writes the final run directory only after all three
roles succeed. An interrupted or invalid later role can strand valid earlier work.
Therefore a bounded call count is not an enforced shared-dollar ceiling. Parent must
review an explicit execution/capture arrangement and fresh metadata before dispatch;
copying this configuration alone does not provide either guarantee. The screened
Flash release reviewer is only a candidate for a separately reviewed original-boundary
review configuration, not automatically qualified for this distinct review contract.

## Offline checks

Both configurations compiled through `build_boundary_pack`, passed
`validate_boundary_pack` with no errors, and produced identical packs on a second
native rebuild. Exact count gates, config hashes, pack hashes, source artifact hashes
inside the packs, and structural request hashes bind the draft. No source obligations
were removed; no source code, provider code, or scheduler was changed.
