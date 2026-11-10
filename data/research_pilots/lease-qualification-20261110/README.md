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
preserve those bindings. The cumulative graph will be published from the exact
GitHub source commit containing this activation and config.

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
cumulative validator. Transport hashes have been checked; complete graph and closure
replay follows after the exact source commit is published and outputs are generated.

## Validation provenance

[The validation receipt](validation-receipt.json) distinguishes the unchanged
research approval runtime from the prospective guard fix. The original runtime
suite failed two legacy guard tests and remains recorded as FAILED. The separately
reviewed guard-fixed source passed all 538 discovered tests in 63 modules with
exact executed-ID coverage and unchanged shared readonly inputs; its byte-identical
[summary](guard-fixed-suite-summary.json) is hash-bound by the receipt.
Publication and deterministic replay make no additional model calls.
