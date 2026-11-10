# Read-only six-submodel cohort planning

The planner validates a fixed budget allocation across the six adopted service
calibration submodels. It creates no authority, registry, journal, score or provider
request and never schedules or dispatches work. A successful receipt is not approval
to spend. The manifest's ceiling is an operator-declared allocation; the planner
cannot authenticate the human approval behind it.

Prepare six fresh evaluation plans and six external authorization JSON files using
the existing governed runtime contracts. Each plan must already pass real canonical
graph and provider-backed eligibility admission. A compiled eligibility projection
or manually supplied `eligible` flag is insufficient. Use the exact adopted factor
bytes, model policies, four independent actors and canonical task schemas. Freeze
against the current source: this new module is included in the runtime's transitive
code hashes, so earlier frozen plans cannot silently adopt it.

The external authority files exist before `initialize`, which later stores their
exact contents inside the workunits. The planner reads those external files; it does
not call `initialize` or create them. Each unit must have a unique resolved path and
registry path. A registry may be absent or explicitly initialized with its exact
standard layout and empty `claims` and `journals` directories. Any existing child
owner, journal, claim or unknown registry state is rejected, including unrelated
prior-authority state. This intentionally excludes recovery and historical accounting.
Prior trial charges in other registries remain outside this fresh allocation;
they are not erased or reported as zero lifetime spend.

Invoke the read-only module with an operator-prepared manifest:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m turbo.agents.evaluation_cohort /absolute/cohort.json
```

The manifest has exactly these fields:

- `schema_version`: integer `1`.
- `kind`: `governed-six-submodel-cohort-plan-v1`.
- `calibration_manifest_sha256`: exact file-byte SHA256 of
  `config/evaluation/calibration/service-cohort-v0.1/calibration-manifest.json`.
- `max_cost_microusd`: nonnegative integer ceiling for these six fresh authorities.
- `units`: exactly six objects, one for each registered submodel, each containing
  `submodel_version_id`, absolute resolved `work_unit_dir`, canonical-JSON
  `plan_sha256`, absolute resolved `authority_path`, and canonical-JSON
  `authority_sha256`. Use the existing runtime hash functions for the latter two;
  do not hash pretty-printed JSON file bytes instead.

Every authority must exactly bind its child plan, code, role configurations and
four-call maximum. The sum of the six authority cost ceilings must not exceed the
manifest ceiling. Allocation is fixed; unused budget is not transferred. Duplicate
submodels, plan hashes or authority hashes are rejected. The child authorities must
have overlapping validity intervals; the planner does not claim those intervals
include the present moment.

All units must share exact graph, strategy, evidence and eligibility artifact bytes,
ordered market-version IDs and evidence cutoff. This first version intentionally
requires one common evidence pack; factor-specific packs need a separately designed
compatibility contract. Every source file is checked by child admission, not just
the top-level evidence JSON. Registered factor hashes and task model policies must
match the adopted catalog.

Successful output is `VALIDATED_FRESH_COHORT_PLAN` with `execution_enabled: false`,
fixed allocation totals and child bindings. It is a point-in-time observation,
not a lock. Subsequent initialization/dispatch must revalidate all child contracts,
current authority validity, registry state, provider endpoints, prices and exact
request bounds. No automatic six-unit scheduler, shared dynamic spend pool,
reallocation, global weights, global ranking or publication is implemented.

Tests use synthetic transport with genuine provider/journal eligibility replay;
synthetic graph fixtures never become accepted real-market evidence. They cover
read-only operation, scope/model/factor drift, forged eligibility, stale contracts,
budget overflow, aliases and existing exposure.
