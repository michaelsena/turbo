# ADR 0024: Bound release review successor

Status: implemented under [Issue101](https://github.com/michaelsena/turbo/issues/101); live execution requires explicit authority.

A completed primary and verifier can remain valid when a release-review request is
rejected before producing a verdict. The existing HTTP400 recovery retained unknown
exposure but supported only historical plain requests. It cannot silently treat a
model-view/citation request as that older contract.

Extend the existing recovery adapter with one explicit checkpoint kind. Its original
runtime is pinned to a clean commit and tree; an isolated interpreter replays that
runtime's complete assignment, source contracts, raw/canonical citation provenance,
upstream submissions and exact preview. Only an independently configured Luna high
release reviewer can replace the failed reviewer. The original model-view and citation
policy stay unchanged. No upstream role is dispatched by the successor.

The existing V2 journal and unique predecessor claim enforce one replacement attempt.
Original physical calls, ledger charges and unresolved reservation reduce the successor
allowance. An HTTP400 is not proof of zero cost. Unresolved replacement outcomes stop.

The original controller remains stopped. A separate read-only recovery approval proof
verifies the settled successor artifact and exact approved preview; existing activation
and graph validators remain mandatory. Publication uses the original clean reviewed
execution commit in a separate clone, never the frozen input checkout.
