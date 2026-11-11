# Approved lease boundary publication

The reviewed activation adds **Occupier-side commercial lease administration** as
one provisional canonical market and one provisional NAICS 531390 mapping.
It does not establish acquisition eligibility or an investment score. Unknown
workforce and acquisition-universe evidence and five explicit gaps remain visible.

The accepted preview is
`2fb624d01b356c63327fc5e930113f8c7ae3a76fbdca40a8cb56bec7db09c6f3`;
the exact independent release-review submission is
`0e2333ac360a4b50887894c94329cb5dae31b757c89ca5e9a20035213beade20`.
Activation `batch-activation-8074059a637690090858` and the cumulative release config
preserve those bindings. The cumulative graph was generated from exact GitHub source commit
`bb4d96cf88a6ba9bcf1ff75e6d15dc4cdf6157f1` and contains six markets and nine mappings.
Its release is `graph-release-5e509cb21490ef9930ea`.

## Replay boundary

This increment contains the compact canonical activation and release configuration,
plus a [hash-bound canonical replay archive](replay/RESTORE.md). The archive preserves
accepted workflow records, frozen preparations, and exact historical source objects.
Raw provider responses, spending authorities and account journals remain privately
retained and are not included. Canonical replay and provider-accounting replay are
separate: the archive supports the former, not the latter.

The workflow locator is `/private/tmp/turbo-service-qualified-v2-ember/workflow`.
Follow the restoration guide to preserve each workflow's original input and
preparation paths. Do not supply one global input/preparation override to the
cumulative validator. Transport hashes have been checked. The cumulative graph and its closure replay
against the preserved original inputs. Complete clean-environment archive restoration
remains a separate qualification; the archive inventory check alone does not establish it.

## Validation provenance

[The validation receipt](validation-receipt.json) distinguishes the unchanged
research approval runtime from the prospective guard fix. The original runtime
suite failed two legacy guard tests and remains recorded as FAILED. The separately
reviewed guard-fixed source passed all 538 discovered tests in 63 modules with
exact executed-ID coverage and unchanged shared readonly inputs; its byte-identical
[summary](guard-fixed-suite-summary.json) is hash-bound by the receipt.
Publication and deterministic replay make no additional model calls.

## Workload accounting manifest

[The publication manifest](publication-manifest.json) uses schema version 2 to bind
six accepted workflow records directly to their existing replay-archive members.
The `workflow_dir` names a virtual repository-relative namespace; it does not claim
that extracted workflow files exist there. Each `archived_files` entry binds the
archive path, exact member name, and member-byte SHA-256. The `files` inventory
binds the original archive bytes and transport inventory, the published closure,
and cumulative canonical release and activation artifacts. Original workflow
bytes, historical source bindings, and accepted review outputs are unchanged.

This manifest lets the offline workload report verify the accepted preview,
review, closure, and still-active graph lineage without restoring historical
absolute paths or duplicating the workflow payload. It supplies binding-only
workload accounting, not full research replay, provider-accounting replay, new
research, acquisition eligibility, or evaluation scores. Completion does not
resolve the lease boundary's retained gaps or its unresolved dispositions.
