# Bounded serial batch controller

The controller advances one fresh, frozen workflow through the existing V2
execution harness. It uses the supplied authority and trusted registry, preserves
stable attempt IDs across restarts, and never creates retry or recovery authority.
It performs primary and verifier calls, the two blind specialists and adjudicator
only when the workflow requires them, then an exact compiled-preview review.

**Approval is not publication.** The terminal success state is
`APPROVED_PENDING_PUBLICATION`, with `canonical_published: false`. Use the existing
clean, pinned batch-closure publication path before freezing the next batch.
This controller does not publish pointers, reconcile unknown calls, rebase inputs,
or schedule another batch.

## Initialize and inspect

Use the reviewed execution checkout containing this script. A new controller
requires an unused, explicit V2 authorization, a fresh workflow, an initialized
registry, and a frozen input checkout with the same canonical base pointer as
this execution checkout. Paths are resolved at initialization and remain bound.
The preparation directories must match the workflow's frozen inputs.

```sh
python scripts/run-batch-controller.py /absolute/controller --initialize \
  --workflow /absolute/workflow --registry /absolute/registry \
  --authorization /absolute/authorization.json \
  --input-root /absolute/frozen-checkout \
  --preparation-dirs /absolute/preparation-one /absolute/preparation-two
python scripts/run-batch-controller.py /absolute/controller
```

The default command reads status only: it does not claim provider authority,
create a provider journal, settle requests, restore workflow submissions, or make
HTTP calls. Initialization writes only controller identity and registry ownership.
Status is derived from the existing workflow and verified journal, not the cached
`status.json` file.

## Execute and supply release decisions

```sh
python scripts/run-batch-controller.py /absolute/controller --execute
python scripts/run-batch-controller.py /absolute/controller --execute \
  --release-config /absolute/reviewed-release-config.json
```

Execution reads `OPENROUTER_API_KEY` from the process environment; do not put keys
in configuration files or command arguments. Provider transport is the existing
one-shot OpenRouter harness. No background daemon or polling model calls are used.
The controller holds its lock while advancing the finite role sequence. A second
controller status command waits for that execution lock; during an in-flight call,
inspect the existing V2 provider journal independently for progress. Do not launch
another execute command to poll progress.

Without explicit semantic release configuration it returns
`WAITING_RELEASE_CONFIG`. The GM supplies the existing batch-closure configuration
schema: schema version, recording timestamp, exact execution commit, graph base
hash, and each family's explicit outcome, reason, proposals and mappings. The
controller does not infer outcomes or relationships. It binds the supplied JSON
hash in both the controller directory and trusted registry, compiles a preview,
and submits that exact preview for independent review. Configuration cannot be
replaced after binding, including with a self-consistently rehashed local file.

## Restart and stops

Repeat the same `--execute` command to resume. A successful settled attempt whose
workflow submission was interrupted replays its stored, validated artifact using
its original attempt ID; it does not dispatch again. Already completed role
submissions must exactly match their successful immutable provider artifacts.
Repeating execution after approval performs no additional model calls.

`STOPPED` covers reserved, dispatched, unresolved and failed attempts, rejected
review, exhausted or expired authorization, changed canonical base, failed
preflight, and invalid bindings. The CLI also returns `STOPPED` and exit code 1
for validation exceptions, exposing only the exception class. Raw exceptions,
provider bodies and credentials are never emitted by this controller. Inspect
the existing governed evidence before deciding any separately authorized recovery;
this controller never retries those attempts or invents new authority.

The manifest binds its own code hash, workflow plan, input tree and paths,
authorization, canonical base, and every role's attempt ID. One immutable registry
owner prevents another controller directory from taking the same authorization;
a second workflow-plan owner also prevents attaching a fresh authority to the same
workflow.
Changed code requires an explicit operational decision; do not edit the manifest
to force continuation. Partial initialization/configuration/status writes fail
closed and require inspection. Keep the registry and controller directory together
on durable storage. Do not delete them to restart execution.

## Verification

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_batch_controller.py -v
```

Focused tests use synthetic transport only. They exercise serial completion,
release waiting, crash-after-settlement replay without duplicate dispatch,
completed-review provenance, immutable bindings, expiry and failed/unknown attempt
stops, and conditional blind-role routing. The full repository suite remains the
integration gate before deployment.
