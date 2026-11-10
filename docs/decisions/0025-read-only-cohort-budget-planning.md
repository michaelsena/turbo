# ADR 0025: Read-only cohort planning with fixed allocations

Status: Accepted for the bounded service-calibration planner.

## Context

The governed evaluation runtime executes one submodel per workunit. V2 shares a
budget among roles inside one authority; placing multiple authorities in a registry
does not create a cross-authority budget. The adopted six-submodel calibration needs
an auditable allocation boundary before separate workunits are initialized.

## Decision

Add a read-only planner that admits exactly the six adopted submodels and binds each
plan and external authority by its canonical hash. Validate child canonical graph,
provider-backed eligibility, evidence, policy and execution contracts through the
existing runtime. Require the same market order, cutoff and exact graph, strategy,
evidence and eligibility artifact bytes across the six units.

Sum the exact child authority ceilings and require that sum to fit the operator's
explicit cohort ceiling. Allocate no authority or budget automatically. The ceiling
is an operator declaration, not authenticated human approval. No unused allocation
is reassigned. Global submodel weights remain unadopted.

Limit admission to fresh units with unique resolved registry paths. Registries may
be absent or initialized but entirely unused. Reject any owner, claim, journal or
unknown state instead of treating historical or unresolved exposure as zero. Prior
spend elsewhere remains outside this allocation and must be accounted for separately.

Return a point-in-time planning receipt with execution disabled. Do not initialize,
mutate, dispatch, schedule, read credentials or call providers. Child execution must
still revalidate state, current authority validity, routes, prices and request fit.

## Alternatives and consequences

A dynamic shared reservation ledger would permit reallocating unused budgets, but
would introduce cross-ledger crash and concurrency boundaries. It is deferred.
A full scheduler is also deferred; this increment is useful before any dispatch and
cannot silently turn planning into execution.

Requiring identical evidence bytes is intentionally stricter than semantic evidence
compatibility. Factor-specific packs and existing-unit accounting need a subsequent
reviewed contract. Adding the module changes the runtime's transitive code hash;
future units must be frozen against the reviewed implementation. Frozen attempts
are never migrated or repaired.
