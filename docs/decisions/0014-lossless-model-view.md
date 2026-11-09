# Optional lossless model view

Status: implemented for explicit new-run qualification; not quality-qualified for rollout.
Issue: [52](https://github.com/michaelsena/turbo/issues/52).

## Problem and decision

The anchored primary request repeats long identifiers, object field names, and
provenance structures. Removing evidence to reduce cost could hide exclusions,
conflicts, or uncertainty. Instead, an optional reversible JSON view uses ordered
object-key tables and a table of repeated long strings. The encoder locally decodes
its result and requires exact equality with the complete original assignment.
Every evidence ID and hexadecimal hash remains literal. No identity, candidate,
source observation, relationship, research gap, or upstream submission is selected
away. Original context files and receipts remain unchanged.

The view is a representation change, not a compressed transport file. Models must
interpret the included encoding instructions. An original object is represented
as `{"o":[schema_index,value,...]}` and repeated strings as `{"s":string_index}`.
All original objects are encoded, including ones with literal `o` or `s` keys;
therefore original data cannot collide with these markers. Output must still be
the existing canonical role JSON with full original IDs. There is no automatic
output decoding, repair, or relaxed evidence validation.

## Explicit authorization and compatibility

Default `model_view=None` keeps the existing plain prompt/assignment shape. To
preregister a fresh encoded run, obtain both role bindings and execution hashes
with the same version:

```python
from turbo.agents import batch_provider, model_view
bindings = batch_provider.contract_bindings(
    input_root=frozen_input, model_view=model_view.VERSION)
contracts = batch_provider.execution_contract_hashes(
    model_view=model_view.VERSION)
# Include these bindings in each role and contracts in build_authorization.
# Model configuration, limits, scope and human authorization remain explicit.
```

The existing execution-contract map pins encoder source and the versioned
policy/instruction digest. Role prompt hashes bind the interpretation instructions.
Dispatch recognizes only the explicit supported policy marker, validates the exact
contract map, and renders the assignment once. Request-size admission and actual
one-shot transport receive identical rendered text. Schema and canonical workflow
checks remain unchanged. Unknown policy, changed policy digest, or unbound prompt
instructions fail before HTTP. Existing journal authorization hashes prevent
switching representation on replay.

Changing process code is not permission to reinterpret an old run: source-contract
changes require new authority. The optional view is explicitly rejected on recovery
checkpoints, so the active payment-rejection continuation cannot silently adopt it.
Use the original frozen process checkout to replay historical runs.

## Measured scope and limits

Offline measurement on the existing anchored pair, with all content retained:

| Quantity | Plain bytes | Encoded bytes |
|---|---:|---:|
| Complete assignment | 2,458,585 | 1,424,702 |
| Runtime prompt including instructions | 2,468,100 | 1,435,450 |
| Complete serialized provider request | 2,637,383 | 1,553,623 |

The complete request is **41.1% smaller in bytes**. This is not measured token
savings, actual provider cost, or demonstrated model quality. Dictionary lookup
may affect reasoning, output length, or citation accuracy. The user target remains
5x lower total workflow cost, with 3x acceptable if quality is sufficient; encoding
alone does not establish that target. The next qualification must compare the same
scope/evidence and count verification, review, retries, and escalation costs.
No paid call was used for this measurement.

## Acceptance before rollout

Preserve exact roundtrip, canonical IDs, all exclusions/conflicts/gaps and coverage.
Compare plain versus encoded behavior using the same substantive acceptance gates.
Do not combine the first encoding qualification with evidence pruning. A model
returning encoded output or a guessed citation fails the existing validators.
