# American Market Universe methodology

## Why this is difficult

No single official list equals an investable market universe. NAICS classifies the
primary activity of establishments. Buyers purchase products and services that cross
those boundaries. Acquisition markets also depend on operating model, firm size,
ownership, economics, and geography.

Turbo therefore treats universe construction as evidence-backed graph reconciliation.

## Source stack

| Source | Role | Limitation |
| --- | --- | --- |
| Census NAICS 2022 | Complete industry hierarchy and stable source codes | Establishment classification, not operating-market truth |
| Census NAPCS | Demand/product/service hierarchy | Requires mapping to industries and operating models |
| Census SUSB | Firms and enterprises by industry and size | EV is inferred, not directly observed |
| BLS QCEW | Establishments, jobs, wages, geography, freshness | Establishments are not independent acquisition targets |
| Economic Census/product lines | Revenue and service mix | Periodic and sometimes coarse |
| OEWS/O*NET | Occupations, tasks, labor composition | Task descriptions require market-specific interpretation |
| BDS | Entry, exit, growth, establishment dynamics | Does not establish transaction availability |
| BEA input-output | Buyer/supplier relationships | Broad sectors and modeled flows |
| Public licensing/regulatory data | Requirements and operator populations | Coverage varies by jurisdiction |
| Public transaction evidence | Pricing and buyer activity | Selection bias and inconsistent normalization |

The bootstrap also preserves the user's prior 978-market model as a candidate and
audit list. It can propose missing markets and useful boundaries, but its classifications
and scores are not accepted without replayable reconciliation.

## Reproducible research protocol

For each source, commit the original bytes and a manifest containing dataset ID,
publisher, URL, retrieval UTC, SHA-256, reuse status, and role. Parsers retain raw
labels and source IDs. Every normalized decision points back to those immutable rows.

Automatic normalization is limited to deterministic cleaning and conservative exact
matches. Similarity search may create review proposals but cannot silently accept a
merge. Review applies the seven operating-identity tests and records rationale,
reviewer, cutoff, confidence, alternatives, and directed lineage. Coverage audits
report all unmatched inputs, residual “other” categories, duplicate candidates, and
source families with weak representation.

## Transformation stages

1. Preserve every source snapshot and record.
2. Normalize labels without erasing source identity.
3. Connect industry activities to products/services and buyers.
4. Generate canonical operating-market candidates.
5. Split materially different buyer, delivery, economics, workforce, risk, or AI models.
6. Merge duplicative labels only with an explicit equivalence decision.
7. Apply hard strategy exclusions separately from weighted scoring.
8. Estimate whether the market contains enough U.S. businesses near $10M–$50M EV.
9. Publish the Target Market Universe with confidence and lineage.
10. Continue discovering omissions, resolving residual categories, and versioning changes.

## Granularity rule

“Commercial HVAC services” is a plausible canonical market. “Recurring
mission-critical HVAC maintenance” is better represented as a child submarket or
business-model lens. The test is whether two nodes would share an acquisition
universe and operating playbook, not whether their labels sound similar.

## V1 status

V1 ingests all 2,125 official NAICS hierarchy nodes, the 2022 Economic Census NAPCS
product/service list, and the prior 978-market seed. It generates a complete mapping
worklist, treating even exact normalized labels as review candidates and exposing
every proposed or unmatched row. Canonical operating-market decisions, SUSB size filtering, and QCEW
enrichment remain incomplete and must precede claims of Target Market completeness.

