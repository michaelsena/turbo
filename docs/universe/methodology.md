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

During this acquisition, direct unauthenticated non-browser requests to the legacy
Census NAPCS hierarchy pages returned Cloudflare errors. Turbo therefore uses a
pre-registered same-origin public-browser capture that stores
each HTTP response entity body as base64 inside one immutable envelope, with its
canonical/final URL, retrieval UTC, visible response metadata, byte length, and
SHA-256. The envelope contains no login credentials, cookies, or browser storage.
Validation decodes and re-hashes every page before parsing, rejects gateway/challenge
content, and requires the exact 24-section source set. This capture layer preserves
the response entity after normal HTTP content decoding; it does not claim to preserve
transport-level gzip framing.

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
attached to the preceding industry. Adjacent semantic spans use embedded font widths
and x-coordinate gaps to preserve real word spaces without splitting fragmented words.
The two uncovered codes remain explicit; absence
from the index is not negative market evidence.

The Manual definition section is parsed separately from its alphabetic index. Turbo
uses coordinate-aware headings on physical PDF pages 79–603 to close exactly one
semantic record against each of the 2,125 official hierarchy identities. The result
contains 1,571 substantive inline definitions, 522 level-five headings that delegate
to a six-digit definition, and 32 level-four title-only headings. Illustrative
examples (381 blocks) and cross-references (1,095 blocks) remain distinct from the
definition narrative. Every derived field retains its contributing page, x/y,
font, size, and text fragments; delegated endpoints must resolve to current 2022
identities. Definition content supports later operating-boundary judgment but does
not itself create, merge, split, filter, or score a market.

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

The 11,543 normalized NAICS/NAPCS identities are partitioned into bounded operating
families rather than
reviewed as one flat list. For each family, one specialist proposes boundaries, a
second independently tests them and searches for countercases, and adjudication
resolves disagreements or keeps the mapping explicitly unresolved. Accepted events
are appended only after review.

The first pre-registered pilot is the `identity:naics:561110` Office Administrative
Services family. The seed was chosen neutrally to exercise a difficult boundary; it
was not selected for investment attractiveness. The exact frozen pack contains the
seed plus all 65 directly observed collection-product identities, while four NAICS
ancestors, nine Manual cross-reference neighbors, and 149 linked trilateral hierarchy
nodes are context-only. It preserves all 121 selected industry-product observations,
55 collection/trilateral relationships with 110 observations, one official explicit
no-mapping row, nine selected products absent from the concordance, the exact Manual
definition and 13 index entries, one vintage-lineage pair, 66 current reconciliation
work items, 127 retrieved prior candidates, and the complete lightweight 978-candidate
catalog. Expected counts are executable gates; a mismatch aborts compilation.

The pack is compiled only from hash-verified immutable run artifacts. It does not
rerun parsers, browse, filter for strategy fit, score attractiveness, or create graph
events. Two blind specialists must disposition every required identity and candidate
hypothesis. The mandatory adjudicator is cryptographically bound to both exact
specialist outputs. Weak evidence produces a provisional inference or assumption with
lower confidence and a retry gap, never a blank. Even a schema-valid adjudication is
only a proposal until independent review activates deterministic graph events.

The corrected V2 pilot is the first completed activation. A zero-finding independent
review approved three proposals with explicit conditions; a separately preregistered,
network-free compiler then emitted three `create_market` events and one provisional
NAICS `561110` `map` event. It emitted no `reject_candidate` events, preserving all
family-local non-mappings in the global candidate catalog. The projection is graph
version `graph-1287641f7c96ef367b8cba4d`. Horizontal operating-model evidence and the
horizontal-versus-vertical boundary remain active gaps; medical and dental markets
and the NAICS mapping remain provisional. Activation is not Target filtering or
market evaluation.

The global audit then detects cross-family duplicates, incompatible mappings,
hierarchy cycles, task-level false markets, residual buckets hiding missing markets,
one-source-only nodes, and boundaries that are too broad or too narrow.

### Complete-family partition

The first full partition is intentionally mechanical and neutral:

1. Each of 1,012 six-digit NAICS identities anchors one review family, including the
   110 leaves with no observed industry-product relationship.
2. Each of 7,115 linked collection identities appears in every officially related
   family but receives one required-review owner using stable rendezvous hashing.
3. The 121 unlinked collection identities enter prefix-grouped, bounded coverage-
   challenge families instead of receiving invented industry mappings.
4. The 1,113 aggregate NAICS identities are hierarchy context and inherit descendant
   family appearances.
5. All 2,182 trilateral hierarchy identities are context-only and inherit family
   appearances through collection concordances and hierarchy descendants. Nodes with
   no inherited operating family remain in explicit section-level context buckets;
   the published missing-parent anomaly is not repaired.
6. The exact 561110 pilot surface is rebuilt from its frozen pack and compared by
   identity set before general assignment: 66 required identities and 162 context
   identities. A method upgrade therefore cannot silently invalidate the completed
   review while preserving only its count.

This produces 8,248 required-review and 3,295 context-only identities, exactly the
11,543-node source universe. A separate collision ledger routes all 978 prior-market
hypotheses, including 58 with no retrieval collision. These are coverage and workload
facts, not canonical-market decisions.

A separate context-edge ledger preserves all 37,232 industry-product relationships,
3,516 collection/trilateral relationships, and 7 explicit non-mappings with source
observations, endpoints, administrative owners, and family appearances. Candidate
ownership is constrained to a schedulable family or the completed pilot; an explicit
global challenger family is used only when no reviewable collision exists.

The queue favors integrity exceptions, unresolved or unmatched source burden, and
cross-family collision risk. It cannot inspect strategy configuration, market demand,
AI potential, valuation, Target eligibility, or companies. Any future change to the
partition method creates a new plan and receipt; it does not rewrite this version.

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
in the relationship archive, one concordance-only collection identity, all 2,182
published trilateral hierarchy nodes, and the prior 978-market seed. Issue #2 upgrades that
worklist with separate source-row, normalized-source-identity, stable content-based
candidate, and opaque canonical-market IDs; preserved lineage, row roles and semantic
flags; and top-k candidates with component signals. Both
collection/trilateral concordances and both Economic Census industry-product archives
are preserved and parsed into a summary plus complete many-to-many relationship
artifact with referentially closed identity endpoints. Seven official `NA`
concordance rows remain explicit non-mapping dispositions. The reconciliation layer
retains 30,850 source rows/observations but produces one review mapping for each of
11,543 normalized identities. The NAICS Manual identity layer now contains exactly
one definition record for all 2,125 hierarchy identities, including 1,571 substantive
definitions, 522 delegated definition links, 32 title-only headings, 381 illustrative
example blocks, and 1,095 cross-reference blocks. Its 20,373 coded alphabetic-index
entries, 25 uncoded index cross-references, the 1,150 full 2017/2022 lineage pairs,
and 846 bridge
observations are published separately as replayable identity evidence so they cannot
silently alter market-candidate retrieval.

The complete hierarchy capture now preserves 1,064,705 verified response-entity
bytes across 24 official pages. Its 2,182 nodes comprise 24 sections, 60 subsections,
169 divisions, 274 groups, 496 subgroups, and 1,159 products, including 87 products
absent from both concordance workbooks. The one published missing-parent anomaly is
kept as an explicit gap rather than repaired. Canonical operating-market decisions,
SUSB size filtering, and enrichment remain incomplete and must precede claims of
Target Market completeness.

