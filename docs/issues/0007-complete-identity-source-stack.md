# Complete the identity-source stack

## Outcome

Complete the authoritative semantic and vintage source layer used by later American
Market Universe boundary review. This issue acquires and parses identity evidence; it
does not create canonical markets, apply strategy eligibility filters, or score market
attractiveness.

## Pre-registered question

Can the pinned official public sources deterministically recover:

1. NAICS Manual index terms and, separately, industry definition semantics;
2. the full six-level 2022 NAPCS hierarchy from original Census bytes; and
3. exact 2017/2022 NAICS lineage plus quantitative bridge observations?

Acceptance requires immutable original bytes, source manifests, exact locators,
replayable parsers, explicit coverage tests, and no downstream market decisions.

## Completed increment

- Preserved both official full NAICS concordance workbooks and both Economic Census
  NAICS bridge archives with URL, retrieval UTC, SHA-256, publisher, reuse, and role.
- Reconstructed 20,373 coded NAICS Manual alphabetic-index entries using
  coordinate-aware two-column parsing. The entries cover 1,010 of 1,012 official
  six-digit codes; `112130` and `541120` are explicit uncovered codes. Twenty-five
  uncoded `******` cross-reference rows remain separate observations.
- Verified that both concordance directions contain 1,150 rows and reverse to the
  same 1,150 unique code pairs. Preserved every direction-specific row locator.
- Preserved 846 bridge observations: 236 industry totals and 610 component rows.
  Eight-digit bridge values remain observations, never identity or market nodes.
- Published separate compressed summary/evidence artifacts so this semantic and
  historical evidence does not silently change current-market candidate retrieval.
- Independent review found and corrected an initial parser defect: some six-digit
  codes were split across PDF glyph spans, and uncoded cross-reference rows had been
  appended to prior labels. Regression tests now cover both cases.
- Exact-head re-review found and corrected dropped spaces between adjacent PDF text
  spans. Reconstruction now uses embedded font widths and coordinate gaps; regression
  fixtures include `Aftermarket parts, automotive` and `Aluminum billet`.
- Extracted one coordinate-backed Manual definition record for every official NAICS
  hierarchy identity on physical PDF pages 79–603: 1,572 substantive inline
  definitions, 522 delegated level-five-to-level-six definition links, and 31
  title-only level-four headings.
- Preserved 381 illustrative-example blocks and 1,095 cross-reference blocks as
  separate semantic fields with their original page/x/y/font/size/text fragments.
  All current identity and delegated endpoints are validated; none enters the
  canonical-market queue by parser side effect.

## Open source gaps

- Capture original bytes for all 24 live Census NAPCS section pages (or an official
  downloadable equivalent). A read-only semantic audit found 2,182 published rows,
  but the public site blocks automated raw retrieval and the `www2` paths return 404.
  Transformed text is audit evidence only and cannot satisfy the immutable-source gate.
- Preserve the single published NAPCS parent-prefix exception (`1110201` without a
  published `11102` parent) as an explicit source anomaly; do not invent the parent.

## Boundaries

No canonical market, target-market eligibility result, market score, company name,
or investment conclusion is produced by this issue.
