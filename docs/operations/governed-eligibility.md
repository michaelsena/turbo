# Governed market eligibility

Eligibility is the versioned Target Market filter between published canonical
market definitions and factor evaluation. It does not rename markets, revise
boundaries, evaluate companies, or produce scores. The compiler is implemented;
production admission additionally requires the separately reviewed provider runtime
and a successful, replayable eligibility judgment. No service market or eligibility
result is claimed by this implementation.

| Gate or condition | Meaning |
| --- | --- |
| United States scope | The frozen operating market has the required U.S. scope. |
| Acquisition population | Evidence supports a population near $10–50 million enterprise value; no individual company's valuation is invented. |
| Buyability feasibility | Market-level feasibility addresses the hard 9x EBITDA ceiling and permitted ownership models; 7–8x remains preferred. |
| Seven excluded exposures | Healthcare delivery, government-dependent revenue, heavy equipment ownership, significant inventory, insurance/credit risk, unionized workforces, and reimbursement exposure are separate required gates. |
| Deal conditions | Actual company EV, purchase multiple, ownership suitability, and due diligence remain mandatory before a transaction. A market pass does not certify them. |

For every gate, `pass` means compatible with strategy, `fail` incompatible, and
`unknown` insufficient support. An excluded-exposure gate passes when that exposure
is not required by the operating market, not when it is present. Any failure
excludes the market; otherwise any unknown holds it; only all passes permit
factor evaluation. Excluded and held markets remain in the canonical universe.
There is no union deferral or waiver. Documented inference or assumption may support
a judgment, but it requires source support, reduced confidence, and retained gaps.
Unknown evidence may never be labeled a pass.

## Frozen input and proof

A work-unit plan binds an ordered `market_version_ids` list, evidence cutoff, and
SHA-256 for every input file. Its `graph`, `strategy`, and `evidence` fields name
relative artifacts inside the work unit. Absolute artifact paths, parent traversal,
symlinks, missing files, and changed bytes fail validation.

The graph descriptor names a canonical Git root, exact latest-graph pointer, graph
release configuration path, and configuration file hash. Validation replays the
published release rather than trusting a self-consistent caller-authored projection.
The strategy artifact must match that repository's original strategy exactly.

The evidence artifact contains `schema_version: 1` and separate `items`, `claims`,
and `gaps`. Each source item binds source bytes, URL, retrieval time, market versions,
and an exact excerpt that must occur in its UTF-8 snapshot. Provider inputs include
the verified source text. Claims carry their own labels, source references, market
scope, and gap references; they cannot masquerade as raw source excerpts. Future
sources, foreign-market references, and dangling or duplicate references fail closed.

`validate_eligibility_input()` produces the verified provider input.
`validate_eligibility_output()` checks exact gate coverage and bindings.
`compile_eligibility()` is a pure projection and is **not** acceptance proof.
`validate_for_evaluation()` additionally calls the provider runtime's independent
journal/artifact verifier before admitting only eligible market versions. A copied
judgment or a caller-authored receipt does not authorize evaluation.

The eligibility work unit has a separate one-call authority for its frozen market
cohort. Its cost cannot be borrowed silently from evaluation authority. The later
scoring protocol retains two independent evaluators, conditional adjudication, and
submodel-owned comparison. See [ADR 0004](../decisions/0004-separate-universe-filtering-and-evaluation.md)
and [scoring protocol](../scoring/model.md).
