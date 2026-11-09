# Complete the identity-source stack

## Outcome

Complete the authoritative semantic and vintage source layer used by later American
Market Universe boundary review. This issue acquires and parses identity evidence; it
does not create canonical markets, apply strategy eligibility filters, or score market
attractiveness.

## Pre-registered question

Can the pinned official public sources deterministically recover:

1. NAICS Manual index terms and, separately, industry definition semantics;
2. the full six-level 2022 NAPCS hierarchy from exact Census response-entity
   bytes captured after normal HTTP content decoding; and
3. exact 2017/2022 NAICS lineage plus quantitative bridge observations?

Acceptance requires immutable source bytes at the documented capture layer, source
manifests, exact locators, replayable parsers, explicit coverage tests, and no
downstream market decisions. Transport-level compression and framing are not claimed.

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
  hierarchy identity on physical PDF pages 79–603: 1,571 substantive inline
  definitions, 522 delegated level-five-to-level-six definition links, and 32
  title-only level-four headings.
- Preserved 381 illustrative-example blocks and 1,095 cross-reference blocks as
  separate semantic fields with their original page/x/y/font/size/text fragments.
  All current identity and delegated endpoints are validated; none enters the
  canonical-market queue by parser side effect.
- Independent exact-head review found that derived semantic text inserted spaces
  after single hyphens at physical line wraps. Reconstruction now rejoins those
  compounds and reads illustrative-example columns independently; regression cases
  cover `air-conditioning`, `one-half`, `residential-type`, and `peer-to-peer`.
- Re-review then found the recurring comparability footer inside 458 definition
  records. The definition body gate now excludes that y-coordinate band, and a
  full-record regression rejects the footer phrase from every semantic field.
- Pilot-pack review later found a small bold standalone heading-decoration glyph
  leaking across definition boundaries. The parser now excludes only that exact
  glyph pattern; 5612 correctly changes from false substantive content to a
  title-only heading, and corpus-wide regression rejects the decoration from every
  semantic block.
- Captured all 24 official Census NAPCS hierarchy pages through a same-origin public
  browser session after unauthenticated non-browser requests returned Cloudflare
  errors. The immutable capture envelope contains 1,064,705 response-entity bytes,
  the canonical and final URL, UTC retrieval time, response metadata, byte length,
  and SHA-256 for every page. No login credentials, cookies, or browser storage are
  included.
- Parsed exactly 2,182 published hierarchy nodes: 24 sections, 60 subsections, 169
  divisions, 274 groups, 496 subgroups, and 1,159 trilateral products. All 1,072
  concordance products resolve; the 87 hierarchy-only products now enter the source
  identity worklist.
- Preserved the published `1110201` / absent-`11102` parent-prefix anomaly explicitly.
  The parser does not invent the missing division or create a false parent edge.

## Closure gates

- Recompute all 24 embedded response-body hashes from the immutable envelope.
- Reproduce exact page, level, hierarchy-only-product, and anomaly counts.
- Pass full local validation, exact replay, full tests, and independent exact-head
  review before treating the source-stack issue as complete.

## Boundaries

No canonical market, target-market eligibility result, market score, company name,
or investment conclusion is produced by this issue.
