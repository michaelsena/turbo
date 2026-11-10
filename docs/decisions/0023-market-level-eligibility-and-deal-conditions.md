# ADR 0023: Separate market feasibility from transaction facts

Status: implementation pending integrated review for issue #86.

The original strategy is retained exactly. Its Target Market projection evaluates
market-level U.S. scope, acquisition-population size, buyability feasibility under
the price ceiling and ownership models, and every excluded exposure. It does not
claim that an unresearched company has a known EV, purchase price, ownership status,
or completed due diligence. Those constraints remain explicit mandatory deal
conditions after a market passes.

Unknown market-level evidence holds eligibility. Evidence-backed inference or
assumption remains possible, with reduced confidence and a retained gap, as required
by ADR 0004; an unknown cannot silently become a pass. No excluded exposure receives
a waiver, including unionized workforces. A failed gate excludes a market from the
Target projection without deleting it from the canonical universe.

Eligibility inputs bind replayed published market versions, exact strategy and
source bytes. A pure compiler result is not an accepted judgment: evaluation admission
also verifies the successful provider artifact and its independent durable accounting
journal. This prevents a caller from converting hand-authored JSON into eligibility.

No production Target projection or real-market score is established by the synthetic
verification fixtures. Integration, full-suite validation, and independent review
remain required before execution.
