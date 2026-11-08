from __future__ import annotations

from statistics import fmean

from turbo.models import EvidenceGap, EvaluatorScore, FactorScore, MarketEvaluation, MarketNode, SourceRef

POSITIVE_SERVICE = (
    "services", "consulting", "repair", "maintenance", "administration",
    "management", "contractors", "testing", "inspection", "support activities",
)
PHYSICAL_PERSISTENCE = (
    "repair", "maintenance", "waste", "water", "plumbing", "electrical",
    "building", "security", "remediation", "pest", "landscaping", "funeral",
)
CAPITAL_OR_INVENTORY = (
    "manufacturing", "merchant wholesalers", "retailers", "dealers", "mining",
    "oil and gas extraction", "transportation equipment", "warehousing",
)
INFORMATION_VULNERABLE = (
    "publishing", "translation", "data processing", "telemarketing", "news",
)
CONTEXT_RICH = (
    "administration", "management", "consulting", "support", "inspection",
    "travel", "association", "claims", "facilities", "business services",
)

FACTOR_IDS = (
    "service_orientation",
    "lmm_buyability",
    "demand_and_ai_resistance",
    "ambient_context_potential",
    "rollup_scalability",
)


def _has(title: str, phrases: tuple[str, ...]) -> bool:
    value = title.lower()
    return any(phrase in value for phrase in phrases)


def exclusion_reasons(node: MarketNode) -> tuple[str, ...]:
    code, title = node.source_code, node.title.lower()
    reasons: list[str] = []
    if code.startswith(("621", "622", "623")):
        reasons.append("healthcare_delivery")
    if code.startswith("92"):
        reasons.append("government_dependent_revenue")
    if code.startswith(("522", "524")):
        reasons.append("insurance_or_credit_risk")
    if code.startswith(("31", "32", "33", "42", "44", "45")):
        reasons.append("significant_inventory_or_manufacturing")
    if "equipment rental" in title or "heavy and civil engineering" in title:
        reasons.append("heavy_equipment_ownership")
    return tuple(sorted(set(reasons)))


def _base_scores(node: MarketNode) -> dict[str, tuple[float, float, str]]:
    title = node.title
    service = _has(title, POSITIVE_SERVICE)
    capital = _has(title, CAPITAL_OR_INVENTORY)
    persistent = _has(title, PHYSICAL_PERSISTENCE)
    vulnerable = _has(title, INFORMATION_VULNERABLE)
    context = _has(title, CONTEXT_RICH)

    return {
        "service_orientation": (
            78 if service else 28 if capital else 50,
            72 if service else 32 if capital else 48,
            "Title-language proxy for service delivery versus inventory or asset intensity.",
        ),
        "lmm_buyability": (
            68 if service else 35 if capital else 50,
            62 if service else 40 if capital else 48,
            "Structural inference about likely lower-middle-market accessibility; firm-size evidence is pending.",
        ),
        "demand_and_ai_resistance": (
            76 if persistent else 36 if vulnerable else 55,
            70 if persistent else 42 if vulnerable else 52,
            "Physical and recurring work is treated as more demand-persistent; purely informational output is discounted.",
        ),
        "ambient_context_potential": (
            78 if context else 66 if service else 45,
            72 if context else 60 if service else 48,
            "Context-rich coordination and service workflows are provisional proxies for Ambient AI leverage.",
        ),
        "rollup_scalability": (
            72 if service and persistent else 64 if service else 44 if capital else 52,
            68 if service and persistent else 58 if service else 40 if capital else 50,
            "Local service delivery and repeatable operations are provisional fragmentation and roll-up proxies.",
        ),
    }


def _resolve_factor(node: MarketNode, factor_id: str) -> FactorScore:
    first, second, rationale = _base_scores(node)[factor_id]
    evaluators = [
        EvaluatorScore("structural-taxonomy-heuristic-v1", float(first), rationale),
        EvaluatorScore("strategy-fit-heuristic-v1", float(second), rationale),
    ]
    disagreement = abs(first - second)
    if disagreement <= 12:
        raw = fmean((first, second))
        resolution = "bootstrap_heuristic_average"
    else:
        # An adjudicator must issue a usable score even while requesting more evidence.
        raw = 0.45 * first + 0.45 * second + 0.10 * 50
        evaluators.append(
            EvaluatorScore(
                "bootstrap-conservative-resolver-v1",
                raw,
                "Issued a conservative provisional score and retained the disagreement as a research gap.",
            )
        )
        resolution = "bootstrap_conservative_resolution"
    confidence = 0.28
    evidence_quality = 0.25
    downside_penalty = 4.0 if factor_id in {"lmm_buyability", "rollup_scalability"} else 2.0
    risk_adjusted = 50 + confidence * (raw - 50) - downside_penalty
    questions = [f"Replace title-based inference for {factor_id} with market-specific public evidence."]
    if disagreement > 12:
        questions.append(f"Resolve heuristic disagreement of {disagreement:.1f} points.")
    gaps = tuple(
        EvidenceGap(
            gap_id=f"gap-{node.source_code}-{factor_id}-{index}",
            question=question,
            status="open",
            ranking_sensitivity=0.5,
            uncertainty=1 - confidence,
            evidence_probability=0.7,
            estimated_cost=0.5,
            priority=round(0.5 * (1 - confidence) * 0.7 / 0.5, 3),
        )
        for index, question in enumerate(questions, 1)
    )
    return FactorScore(
        factor_id=factor_id,
        raw_score=round(raw, 2),
        confidence=confidence,
        evidence_quality=evidence_quality,
        downside_penalty=downside_penalty,
        risk_adjusted_score=round(risk_adjusted, 2),
        resolution=resolution,
        reasoning_label="inference",
        evaluator_scores=tuple(evaluators),
        rationale=rationale,
        counterevidence=("Title language may not reflect the operating model or acquisition economics.",),
        alternative_estimates=(round(min(first, second), 2), round(max(first, second), 2)),
        sources=(SourceRef("census-naics-2022", f"NAICS {node.source_code}", "fact"),),
        open_gaps=gaps,
    )


def evaluate_market(node: MarketNode) -> MarketEvaluation:
    factors = tuple(_resolve_factor(node, factor_id) for factor_id in FACTOR_IDS)
    exclusions = exclusion_reasons(node)
    raw = fmean(score.raw_score for score in factors)
    confidence = fmean(score.confidence for score in factors)
    adjusted = fmean(score.risk_adjusted_score for score in factors)
    gaps = tuple(gap for score in factors for gap in score.open_gaps)
    return MarketEvaluation(
        market_id=f"candidate-{node.source_code}",
        title=node.title,
        source_code=node.source_code,
        status="provisional_excluded" if exclusions else "provisional_candidate",
        exclusion_reasons=exclusions,
        factor_scores=factors,
        aggregate_raw_score=round(raw, 2),
        aggregate_confidence=round(confidence, 2),
        aggregate_risk_adjusted_score=round(adjusted, 2),
        open_gaps=gaps,
    )

