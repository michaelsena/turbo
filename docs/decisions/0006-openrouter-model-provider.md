# ADR 0006: OpenRouter as the metered model-provider layer

## Status

Accepted for the Issue #12 execution pilot. Role assignments remain provisional.

## Decision

Turbo uses OpenRouter as its primary metered model-provider layer. Each agent role has
an explicit, versioned model slug in configuration. The system sends one model slug
per request; it does not use an opaque cross-model auto-router. Provider fallback for
the same requested model is allowed, and receipts preserve both the requested model
and the model/provider reported by OpenRouter.

The provider boundary uses OpenRouter's OpenAI-compatible chat-completions endpoint,
strict JSON Schema response format, and `provider.require_parameters=true`. Turbo
adapts the model-facing schema to a portable provider subset, removing optional
numeric and uniqueness constraints that some vendors reject. Turbo still treats every
response as untrusted and reruns the complete canonical schema plus closed-world
validation before any output can be persisted. The receipt binds both schema hashes.
Two specialists remain blind and the adjudicator remains bound to their exact
validated output hashes.

The dedicated Turbo API key is supplied only through `OPENROUTER_API_KEY`. It is not
stored in configuration, receipts, logs, committed files, prompts, or model output.
The local `.env` path is ignored by Git. The initial account key has a $50 monthly
cap and a 180-day lifetime; these operational controls may be tightened without
changing the research contract.

Requests exclude returned private reasoning. Receipts retain non-content operational
metadata: request/response hashes, UTC bounds, latency, attempts, generation ID,
requested/served model, served provider when reported, token usage, cost when
reported, and validation status.

## Rationale

Turbo needs to benchmark and assign different vendors' models by role without
rewriting the harness or distributing several provider credentials. OpenRouter gives
one API surface while the explicit model slug, frozen input, schema, validation, and
receipts preserve auditability. Local Codex CLI execution remains available as a
fallback provider, but the pilot configuration now selects OpenRouter.

## Consequences

- Model access is broad, but model choice is still governed and measured.
- A provider outage may fail over within the requested model; a different model
  requires an explicit configuration change and new receipt.
- Structured-output support is filtered at routing time and verified again locally.
- Spending remains bounded by both the account key limit and explicit run commands.
- No model call may directly activate a Market Graph event.

## Primary references

- [OpenRouter chat-completions API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request)
- [OpenRouter structured-output routing and `require_parameters`](https://openrouter.ai/blog/insights/confidence-thresholds-for-model-escalation-routing/)
- [Provisional GPT-5.6 Terra model endpoint](https://openrouter.ai/openai/gpt-5.6-terra)
