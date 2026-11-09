# Documentation index

[README](../README.md) is the executive guide to current results, system boundaries,
local operation, and next work. These documents hold the detailed contracts. Update
the README and the relevant document whenever behavior or architecture changes.

## Purpose and research design

- [Product vision](product/vision.md)
- [Universe methodology](universe/methodology.md)
- [Ambient AI thesis](ambient-ai/thesis.md)
- [Scoring model](scoring/model.md) — design for the later evaluation stage
- [AI-first autonomous operation](governance/ai-first.md)
- [Public and interview communication](governance/public-communication.md)

## Architecture and operation

- [System architecture](architecture/system.md)
- [Data contracts](architecture/data-contracts.md)
- [Read API and React research console](application/read-api-dashboard.md)
- [Local operating runbook](operations/runbook.md)
- [App/UI GM worker charter](operations/app-gm-worker.md)
- [Local App/UI issue dispatcher](operations/app-dispatcher.md)
- [Issue 14: deterministic family partition and scheduler](issues/0014-family-partition-scheduler.md)
- [Issue 15: batch-native family research](issues/0015-batch-native-family-research.md)
- [Family-preparation correction audit](operations/receipts/2026-11-09-family-pack-corrections.json)
- [Dashboard verification](operations/receipts/2026-11-09-dashboard-corrections.json)
- [Batch-ledger simulation verification](operations/receipts/2026-11-09-batch-ledger-verification.json)
- [Shared-registry simulation verification](operations/receipts/2026-11-09-shared-registry-verification.json)
- [Batch-output contract verification](operations/receipts/2026-11-09-batch-output-verification.json)

## Architecture decisions

- [ADR 0001: Architecture and operating model](decisions/0001-architecture-and-operating-model.md)
- [ADR 0002: Universe before scoring](decisions/0002-universe-before-scoring.md)
- [ADR 0003: Typed market identity graph](decisions/0003-typed-market-identity-graph.md)
- [ADR 0004: Separate universe, filtering, and evaluation](decisions/0004-separate-universe-filtering-and-evaluation.md)
- [ADR 0005: Model-agnostic boundary harness](decisions/0005-model-agnostic-boundary-harness.md)
- [ADR 0006: OpenRouter model-provider layer](decisions/0006-openrouter-model-provider.md)
- [ADR 0007: Schedule-driven family preparations](decisions/0007-schedule-driven-family-preparations.md)
- [ADR 0008: Batch authorization and execution ledger](decisions/0008-batch-authorization-execution-ledger.md)
- [ADR 0009: Trusted local execution registry](decisions/0009-trusted-local-execution-registry.md)
- [ADR 0010: Standalone batch-output contract](decisions/0010-batch-output-contract.md)
- [ADR 0011: Batch-output artifacts and managed settlement](decisions/0011-batch-output-artifacts.md)
- [Prior-model crosswalk](decisions/prior-model-crosswalk.md)
