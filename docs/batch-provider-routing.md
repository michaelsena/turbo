# Authorization-bound provider routing

V2 role configuration optionally contains `routing`. Existing profiles without it
retain their request shape. New bounded canary profiles must supply it explicitly:

```json
{
  "schema_version": 1,
  "provider": {
    "only": ["openai"],
    "ignore": ["openai/fast", "openai/flex"],
    "max_price": {"prompt": "0.4", "completion": "1.8"}
  },
  "prompt_cache_options": {"mode": "explicit"}
}
```

This is a role's `routing` value, not a complete authorization. Provider slugs are
exact lower-case routing tags. `only` must be nonempty; `ignore` may be empty.
The wire always requires parameter support and disables fallbacks. Extra policy
keys, request overrides, endpoints, headers and cache breakpoints are rejected or
never constructed. Omit `prompt_cache_options` for non-OpenAI models.

Prices are **USD per million tokens**, numerically equal to local microUSD per
token. Authorization stores bounded nonnegative decimal strings, not floats.
Decimal comparisons require each local integer rate to cover its corresponding
cap (e.g. 0.4/1.8 requires integer ceilings at least 1/2). Wire conversion rejects
values that do not survive exact decimal JSON roundtrip or exceed safe integers.
No float participates in budget arithmetic. The identical request builder adds
provider/cache fields before size admission and one-shot dispatch. Authorization
and request hashes include the policy; changing it requires fresh authority and
cannot resume a prior settled workflow output as a new provider result.

The optional policy is compatibility support, not canary approval. Refresh endpoint
pricing and confirm context fit, available balance, credential injection and explicit
run authority before any paid run. Price filters do not guarantee total billed cost:
cache writes, reasoning or other billing categories may require additional local
headroom. Missing eligible endpoints fail in one attempt; reported charges remain
accounted for, and missing billing stays unresolved. The shared local registry is
not a provider-enforced account-wide spending limit.

Verified against official [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
and [prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
documentation on 2026-11-09. Explicit mode with no breakpoints disables automatic
cache writes on supported OpenAI GPT-5.6+ models. This implementation does not infer
support for other models or approve any proposed verifier's research quality.
