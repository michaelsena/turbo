# Interrupted provider attempts

Status: prospective design and read-only operating guidance. This document adds no recovery implementation, authority, provider call, or permission to settle an interrupted attempt. Existing strict validators and no-resend behavior remain authoritative.

## Verified current lifecycle

The current governed path has a durable admission boundary but a later response-persistence boundary:

1. `BatchExecutionV2.run` in `src/turbo/agents/batch_execution_v2.py` appends and fsyncs `reserved`, then `dispatched`, before invoking the provider callback. The event means dispatch was admitted; it does not prove that a request reached the provider.
2. `_no_redirect_transport` in `src/turbo/agents/openrouter_attempt.py` performs one synchronous HTTP request and reads a bounded response into memory. It does not checkpoint response headers or partial body bytes.
3. `invoke_openrouter_once` parses the completed response and extracts generation identity, usage, cost, and final content. Response headers are not retained in its returned evidence.
4. For an otherwise valid response, the callback inside `run_batch_role` in `src/turbo/agents/batch_provider.py` normalizes content, rechecks input and upstream provenance, and validates the document before `_save_artifact` persists the first provider artifact. Invalid responses are also recorded without passing those acceptance steps. Artifact creation is exclusive and fsynced; partial artifacts are not silently overwritten.
5. The execution ledger settles only after the callback returns acceptable telemetry. Ordinary exceptions produce an unresolved event when control returns to the ledger. Hard process termination can leave only `dispatched`.
6. An operator wrapper can emit its final status only after this chain returns. An empty redirected result file is therefore not evidence of no request, no provider work, or no cost.

`tests/test_batch_execution_v2.py::test_hard_crash_dispatch_never_resends_after_restart` already verifies that a hard interruption leaves the attempt dispatched, holds its reservation, and does not resend. This is correct budget protection, not an automatic recovery facility.

## Rules at the interruption boundary

- Preserve the original authority, request, attempts, journal, outputs, and source checkout. Record observations separately.
- Keep the full outstanding reservation until governed, attributable evidence permits reconciliation. An account balance change is not an attempt-specific cost receipt; an unchanged balance is not proof of zero cost.
- Never resend an existing attempt or create a replacement simply because the process disappeared, monitoring failed, or a result file is empty.
- Do not mark a missing result as succeeded, failed with known cost, cancelled, or zero-cost. Distinguish the persisted ledger state from an operator's observation that execution is no longer visible.
- Do not submit reconstructed research, repair provider content, import unproven outputs, or admit downstream work without accepted upstream provenance.
- A policy rejection during monitoring does not authorize detaching, relaunching, changing transport, or bypassing the rejected action.

A lost process handle and absent process establish loss of local execution visibility. Without an exit status or signal, they do not establish the termination cause. A nearby approval rejection is a temporal observation, not proof that it killed the process.

## Read-only operator procedure

1. Inspect the original journal and its hash chain. Record its tip, state, stable attempt identity, request binding, outstanding reservation, and any already persisted artifact references.
2. Inspect existing result files and artifacts without rewriting them. Determine whether a complete response, generation identifier, usage, or provider receipt actually survived. Do not expose credentials or raw provider reasoning in reports.
3. Inspect existing process or supervisor status without starting another process that dispatches. Record an exit status when available; otherwise retain uncertainty.
4. If a genuine generation identifier exists, consult the provider's documented read-only metadata interface. Bind any retrieved evidence to the original model, provider, session/request, timestamp, and attempt. Similar timestamps or matching costs alone are insufficient.
5. If no generation identifier survived, use an already authorized authenticated provider dashboard to locate the exact session/request, if supported. Do not invent API parameters, substitute a session identifier for a generation identifier, or enable retrospective content logging as a purported recovery.
6. Report findings separately from ledger settlement. A metadata receipt may resolve cost without recovering acceptable research content. A recovered completion still requires its original provenance and strict validation; evidence retrieval is not automatic workflow acceptance.
7. Stop if the documented retrieval route is unavailable or cannot establish attribution. Preserve held exposure and identify the missing evidence.

OpenRouter's documented generation metadata and stored-content APIs require a generation identifier. Stored content requires input/output logging to have been enabled when the generation occurred. Its Logs dashboard exposes generation and session records; aggregate activity and key balances do not supply a replacement generation receipt. Account permissions can further restrict analytics access.

## Proposed durability work

These are requirements for a future reviewed implementation, not features available today.

### Supervision

Run the approved one-attempt worker under a lifecycle that can durably record its start binding, process identity, and exit status independently of the interactive monitor. The supervisor must not automatically restart, retry, extend authority, or dispatch downstream work. Monitoring availability must not change the approved request or dispatch destination. Supervisor diagnostics are not spend settlement evidence.

### Capture before validation

Add an attempt-bound evidence sink to the provider transport and adapter. Capture allowlisted, non-secret response status and correlation metadata as soon as available. Persist a completed response receipt before normalization and semantic validation. A sanitized attempt checkpoint should bind authority, attempt, exact request and schema hashes, served model, generation identifier, usage/cost state, and content digest.

If bounded raw-body spooling is chosen, require private restrictive permissions, exclusive creation, explicit partial-versus-complete state, size limits, hashes, and durable flushes. Never store authorization headers. Raw content may contain sensitive data or reasoning and must not enter published receipts. A partial spool is diagnostic evidence only; it must not be parsed opportunistically into an accepted result.

Keep immutable transport evidence separate from the validated provider artifact. The validated artifact must reference the evidence digest and pass all existing source, model, schema, citation, upstream, preview, and cost checks. Do not weaken these checks to improve recovery rates.

### Reconciliation

Provide an evidence-only inspector first. Any later ledger-settlement or accepted-output recovery mechanism requires a separately reviewed contract, exact source bindings, exclusive ownership, and deterministic replay without network dispatch. It must distinguish cost reconciliation from research acceptance and refuse missing, partial, conflicting, or unattributable evidence.

No new capture mechanism can recover evidence that was never persisted by an earlier run. HTTP-specific recovery contracts must not be repurposed for a different failure class.

## Synthetic interruption acceptance matrix

Tests must use synthetic transports and controlled process interruption, never paid provider calls.

| Interruption point | Evidence expected | Required outcome |
| --- | --- | --- |
| After reservation, before dispatch event | Reservation and original bindings | Hold exposure; no automatic dispatch or resend |
| After dispatch event, before transport entry | Dispatched journal only | Do not claim network delivery; hold exposure; no resend |
| After response headers, before body | Bound allowlisted metadata checkpoint | No accepted output or cost inference from status alone |
| During bounded body read | Explicit partial capture | Reject as completion; retain unknown exposure |
| After complete body capture, before parsing | Durable complete receipt and digest | Offline inspection allowed; no automatic acceptance |
| After sanitized checkpoint, before semantic validation | Immutable checkpoint with known/unknown telemetry | Strict validation still required; cost and acceptance remain separate |
| After validation, before artifact persistence | Checkpoint survives; validated result may not | Revalidate deterministically; never infer acceptance from transient state |
| After artifact persistence, before settlement | Complete artifact and original journal tip | Governed reconciliation only; no second request |
| After settlement, before workflow submission | Settled receipt and artifact | Existing exact-artifact validation remains mandatory; no provider resend |
| Monitor or supervisor interruption | Worker state/exit observation if available | No automatic restart; unknown state stays unknown |

Additional adversarial checks must reject truncated, oversized, tampered, or symlinked captures; prevent credential leakage; preserve semantic-rejection behavior; and prove that competing monitors/reconcilers cannot duplicate calls, overwrite immutable evidence, release unknown exposure, or admit downstream roles. Existing unknown-cost, artifact-tamper, and no-resend tests must continue to pass unchanged.

## Provider references

- [OpenRouter Logs](https://openrouter.ai/docs/guides/features/logs)
- [Generation request and usage metadata](https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation)
- [Stored generation content](https://openrouter.ai/docs/api/api-reference/generations/get-stored-prompt-completion-and-error-content-for-a-generation)
- [Aggregate user activity](https://openrouter.ai/docs/api/api-reference/analytics/get-user-activity-grouped-by-endpoint)
