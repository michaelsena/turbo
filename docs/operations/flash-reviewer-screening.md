# Limited Flash reviewer screening

The explicitly approved screening completed four calls using
`google/gemini-3.8-flash` on `google-vertex/global`, with high reasoning, a 16,000
output-token allowance, no fallback and no retries. All four canonical responses
passed mechanical validation and independent semantic assessment. The
[receipt and exact responses](receipts/2026-11-10-flash-reviewer-screening/receipt.json)
retain the input/output bindings and assessment evidence. Financial accounting is
retained separately and is not included in public artifacts.

| Fixture | Representation | Verdict | Input tokens | Output tokens | Call elapsed seconds |
| --- | --- | --- | ---: | ---: | ---: |
| Accepted positive | Plain | Approve | 224,519 | 6,803 | 49.396 |
| Accepted positive | References | Approve | 114,621 | 5,209 | 33.674 |
| Semantic negative | Plain | Reject | 224,556 | 11,728 | 82.801 |
| Semantic negative | References | Reject | 114,659 | 15,886 | 96.908 |

Elapsed time covers the local runner invocation, not isolated provider inference.
Each cell was called once. Requests contained no earlier answers or rubric. Both
negative responses identified the exact industrial-sand job inversion, original
source evidence ID and affected preview. Both positive responses retained the
provisional judgments and explicit gaps. The negative fixture deliberately retained
synthetic verifier agreement; the finding against that trail is not evidence of an
actual verifier failure.

The referenced requests used approximately 49% fewer input tokens in these two
fixtures. This is not a claim of equivalent cost or latency savings. The negative
referenced case used 15,886 of its 16,000 output tokens and took longer than its
plain counterpart. Larger-workload output headroom remains unqualified; neither
lower output allowances nor universal speed or cost improvements follow.

This is a limited screening pass, not broad quality equivalence or production
adoption. Production defaults and the five-market canonical graph are unchanged.
The [medium preflight](medium-primary-preflight.md) still requires a compatible
explicit authorization and admission envelope. The next candidate qualification
can consider this model and representation while preserving the existing primary,
selective verifier, conditional escalation and exact independent review workflow.
No further calls are authorized by this receipt, and no budget or authority is
created or extended by a successful screening.
