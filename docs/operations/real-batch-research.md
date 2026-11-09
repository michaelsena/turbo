# Real batch research through local Codex

`scripts/run-codex-batch.py` runs one real research attempt over verified frozen
inputs using the authenticated local Codex CLI. It consumes the account's usage/quota.
This is separate from B1/B2/B4 simulation accounting: it does not use their budget
ledger, settle simulated microdollars, or call the paid OpenRouter adapter. Run only
an explicitly authorized batch with an agreed model/effort and output location.

Prepare 2–8 complete families from one manifest-ordered batch. Build B3 context with
fixed request/invocation IDs and the standard limits: 1,000,000 output bytes and
100,000,000 context bytes. The runner regenerates context from exact preparations
and verifies the prompt/schema hashes before invocation. It makes the entire context
available as a local file for incremental inspection; it does not truncate families
or embed the multi-megabyte evidence file directly in the initial prompt.

From the intended frozen checkout, with dependencies installed:

```bash
PYTHONPATH=src .venv/bin/python scripts/run-codex-batch.py path/to/context.json \
  path/to/preparation-1 path/to/preparation-2 \
  --output-root path/to/real-batch-runs --timeout-seconds 3600
```

Optional `--model` and `--reasoning-effort` select the agreed settings; otherwise the
CLI's configured defaults are retained. The worker uses an ephemeral, read-only
sandbox with approval mode `never`, the pinned output schema, and local evidence.
External research, credential access, repository edits, and further model dispatch
are outside this invocation's instructions.

Keep one fixed output root for this work. Before dispatch, the runner exclusively
creates `<output-root>/<invocation-hex>/`, persists `run-receipt.json`, and copies the
exact `context.json`. An existing directory blocks resend, including after a crash.
Do not delete it, change the output root, or mint another invocation merely to bypass
that protection. This is local directory-based admission, not global deduplication
across independent output roots.

The receipt records input bindings, code/runner/prompt/schema hashes, selected model
settings, CLI version, timestamps, available token usage, and validation outcome.
A bounded final answer is retained as `output.json`. Raw stdout/stderr and private
reasoning are not persisted; only their hashes and extracted usage are retained.
`model_invoked` may remain `unknown` after failures; a nonzero exit does not prove
that no account usage occurred.

Timeout or interruption retains the attempt and may record `uncertain`. Inspect its
receipt and available final output before deciding next steps. There is no automatic
retry, refund, or repair. Do not infer success from process exit alone: `valid` means
B3 structural validation passed, not that citations substantively support the claims
or that a market boundary is accepted. Independent evidence review and the existing
activation/governance path still precede accepted research, graph movement, or scores.

The [first pilot bundle](../../data/research_pilots/anchored-20261109/README.md)
preserves exact inputs, output, review, provenance, and failed CLI receipts.
Its independent review permits provisional publication only. Future attempts must
likewise preserve exact inputs and results before they are used beyond a local session.

The first approved CLI attempt on 2026-11-09 exited without output or reported
usage in the managed executor. Startup filesystem restrictions are suspected;
successful authentication alone does not verify execution. Its receipt retains
`model_invoked: unknown`. Research authored by a collaboration agent must carry
separate provenance and must never be reported as a successful CLI invocation.
