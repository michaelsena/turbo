# American Market Universe methodology

## Why this is difficult

No single official list equals an investable market universe. NAICS classifies the
primary activity of establishments. Buyers purchase products and services that cross
those boundaries. Acquisition markets also depend on operating model, firm size,
ownership, economics, and geography.

Turbo therefore treats universe construction as evidence-backed graph reconciliation.

## Identity source stack

| Source | Role | Limitation |
| --- | --- | --- |
| Census NAICS 2022 hierarchy | Supply-side backbone and stable industry codes | Establishment classification, not operating-market truth |
| 2022 NAICS Manual and alphabetic index | Definitions, inclusions, exclusions, cross-references, synonyms | Still describes industries rather than acquisition markets |
| Full 2022 trilateral NAPCS hierarchy | Six-level demand-oriented product/service structure | Products are not one-to-one operating markets |
| Economic Census NAPCS collection codes | Broad/detail product lines actually collected | Collection hierarchy differs from trilateral hierarchy |
| NAPCS collection-to-trilateral concordance | Connects collection codes to stable product identities | Establishes product lineage, not market equivalence |
| Industry-by-products / products-by-industry | Observed many-to-many NAICS-NAPCS sales relationships | Coverage and suppression require careful interpretation |
| 2017-2022 NAICS concordances and bridge tables | Split/merge lineage across vintages | Does not define the preferred canonical boundary |
| Prior 978-market model | Coverage challenger and boundary hypotheses | User-authored, not authoritative or presumed complete |

No additional commercial master-industry list is required for V1. The missing
upstream value is official semantic detail, hierarchy, concordance, and observed
industry-product relationships, not another opaque list.

## Enrichment source stack

| Source | Role | Limitation |
| --- | --- | --- |
| Census SUSB | Firms and enterprises by industry and size | EV is inferred, not directly observed |
| BLS QCEW | Establishments, jobs, wages, geography, freshness | Establishments are not independent acquisition targets |
| Census CBP / Nonemployer Statistics | Local structure and microbusiness fragmentation | Establishments and nonemployers are not PE targets |
| OEWS/O*NET | Occupations, tasks, labor composition | Task descriptions require market-specific interpretation |
| BDS | Entry, exit, growth, establishment dynamics | Does not establish transaction availability |
| BEA input-output | Buyer/supplier relationships | Broad sectors and modeled flows |
| Public licensing/regulatory data | Requirements and operator populations | Coverage varies by jurisdiction |
| Public transaction evidence | Pricing and buyer activity | Selection bias and inconsistent normalization |

These enrichment sources inform Target Market eligibility and later scoring. They do
not define canonical identity.

## Reproducible research protocol

For each source, commit the original bytes and a manifest containing dataset ID,
publisher, URL, retrieval UTC, SHA-256, reuse status, and role. Parsers retain raw
labels and source IDs. Every normalized decision points back to those immutable rows.

Automatic normalization is limited to deterministic cleaning, row-role typing,
hierarchy preservation, semantic flags, and top-k retrieval. Exact and fuzzy matches
are proposals only. Candidate output currently retains Jaccard similarity, top-two
margin, exclusions, residual flags, contradictions, official label conflicts, and
ambiguity. Structural NAICS markers remain in raw evidence but are excluded from
normalized labels and retrieval. Pair-level relationship edges preserve every
contributing row-level locator. Review applies the seven
operating-identity tests and records rationale, reviewer, cutoff, confidence,
alternatives, and directed lineage.

The NAICS Manual alphabetic index requires coordinate-aware parsing. It is printed
in two columns; plain text extraction can concatenate the columns and create false
entries. Turbo reconstructs each column independently from physical PDF pages
637–958, accepts only anchors matching an official six-digit 2022 code, carries
wrapped text across column/page boundaries, and emits a unique page/column/baseline/
ordinal locator. The resulting 20,373 coded entries cover 1,010 codes. Twenty-five
`******` cross-reference rows remain separate uncoded observations rather than being
attached to the preceding industry. The two uncovered codes remain explicit; absence
from the index is not negative market evidence.

NAICS vintage lineage is separate from canonical identity. The two official full
concordance directions must reverse to the same 1,150 pairs. Historical 2017 codes
remain lineage values, and eight-digit Economic Census bridge components remain
quantitative observations. Neither is placed in the current-market reconciliation
queue or treated as an operating market.

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

## Stage boundary and role of AI

Universe construction, strategy filtering, and market evaluation are different
decision systems:

- **Universe construction** determines market identity and boundaries. Raw capture,
  code normalization, source relationships, and locator validation are deterministic.
  AI specialists supply the operating judgment needed to turn classifications into
  canonical markets: create, merge, split, map, reject, or exclude. Independent review
  tests each proposal; accepted judgments retain evidence, assumptions, alternatives,
  confidence, and append-only lineage.
- **Target-universe filtering** applies versioned eligibility gates to already-defined
  markets. A filtered-out market still exists in the canonical universe. Eligibility
  is not an attractiveness score.
- **Market evaluation** researches and scores only eligible market versions. It may
  use evidence-backed inference and lower-confidence assumptions to avoid blank factor
  fields, with retry tasks for weak evidence. It cannot change market identity.

Temporary research queues may contain unresolved items. A published complete
canonical or scored projection may not conceal missing decisions: the system records
the best defensible judgment, labels inference or assumption explicitly, lowers its
confidence, and keeps the gap active for future improvement. If evaluation discovers
a boundary error, it proposes a separate universe event rather than changing the
scored market in place.

## Operating-family review

The 10,433 normalized NAICS/NAPCS identities are partitioned into bounded operating
families rather than
reviewed as one flat list. For each family, one specialist proposes boundaries, a
second independently tests them and searches for countercases, and adjudication
resolves disagreements or keeps the mapping explicitly unresolved. Accepted events
are appended only after review.

The global audit then detects cross-family duplicates, incompatible mappings,
hierarchy cycles, task-level false markets, residual buckets hiding missing markets,
one-source-only nodes, and boundaries that are too broad or too narrow.

Completeness requires both 100% typed source-row disposition and a coverage challenge.
Disposition alone does not prove that no American operating market is missing.

## Granularity rule

“Commercial HVAC services” is a plausible canonical market. “Recurring
mission-critical HVAC maintenance” is better represented as a child submarket or
business-model lens. The test is whether two nodes would share an acquisition
universe and operating playbook, not whether their labels sound similar.

## V1 status

The bootstrap ingests all 2,125 official NAICS hierarchy nodes, the 2022 Economic
Census NAPCS collection-code list, 945 additional product identities observed only
in the relationship archive, one concordance-only collection identity, 1,072
trilateral identities, and the prior 978-market seed. Issue #2 upgrades that
worklist with separate source-row, normalized-source-identity, stable content-based
candidate, and opaque canonical-market IDs; preserved lineage, row roles and semantic
flags; and top-k candidates with component signals. Both
collection/trilateral concordances and both Economic Census industry-product archives
are preserved and parsed into a summary plus complete many-to-many relationship
artifact with referentially closed identity endpoints. Seven official `NA`
concordance rows remain explicit non-mapping dispositions. The reconciliation layer
retains 28,668 source rows/observations but produces one review mapping for each of
10,433 normalized identities. NAICS Manual definition extraction remains open. Its
20,373 coded alphabetic-index entries, 25 uncoded index cross-references, the 1,150
full 2017/2022 lineage pairs, and 846 bridge
observations are published separately as replayable identity evidence so they cannot
silently alter market-candidate retrieval.

The complete trilateral hierarchy capture remains blocked on preservation of original
Census bytes. A semantic audit of the 24 live section pages found 2,182 published
nodes (24 sections, 60 subsections, 169 divisions, 274 groups, 496 subgroups, and
1,159 products), including 87 products absent from the two concordance workbooks.
Those transformed audit results are not substituted for original public-source
snapshots. Canonical operating-market decisions, SUSB size filtering, and enrichment
remain incomplete and must precede claims of Target Market completeness.

