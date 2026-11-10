# Literal navigation for managed research assignments

Issue [89](https://github.com/michaelsena/turbo/issues/89) adds a deterministic
navigation block to the existing optional lossless model view. The complete
encoded assignment remains unchanged. Plain/default requests and the independent
readable-reviewer view retain their previous rendering.

The block copies exact B3 payload bindings and each family's local required and
context-only identifiers from the verified assignment. Required-subject cards copy
original labels, owner/global-role fields and exact card evidence anchors. Global
`assignment_role` values on context cards do not create local disposition
obligations. Actor IDs and workflow-role invocation IDs do not replace payload
request/invocation IDs. The block introduces no new evidence or score judgments.

Use `batch_provider.render_assignment` for offline request sizing as well as
managed dispatch. Manually concatenating `role_prompt` and the encoded assignment
omits navigation and produces an obsolete request measurement. The navigation
instructions flow through prompt bindings; implementation is covered by existing
provider execution-contract hashes. The literal block is included before the
existing request byte bound is checked.

Changed code requires a fresh frozen runtime, regenerated complete preparations,
fresh workflow and explicit authority. Existing failed attempts and their pinned
runtime remain unchanged. No output rewriting, ID repair, selector, validator
relaxation, budget change or new execution path is introduced.

Focused checks cover exact bindings, required/context separation, original labels,
owned card anchors, unchanged full evidence and blind inputs, missing/ambiguous
anchor refusal, plain compatibility and continued rejection of actor-as-request
or extra-context dispositions. Existing provider/model-view tests cover bounded
admission, controlled transport and replay. Semantic review remains mandatory:
better navigation does not establish correct market boundaries or evidence use.
