from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    snapshot_id: str
    locator: str
    evidence_label: str


@dataclass(frozen=True)
class EvaluatorScore:
    evaluator_id: str
    score: float
    rationale: str


@dataclass(frozen=True)
class FactorScore:
    factor_id: str
    raw_score: float
    confidence: float
    evidence_quality: float
    downside_penalty: float
    risk_adjusted_score: float
    resolution: str
    reasoning_label: str
    evaluator_scores: tuple[EvaluatorScore, ...]
    rationale: str
    counterevidence: tuple[str, ...]
    alternative_estimates: tuple[float, ...]
    sources: tuple[SourceRef, ...]
    open_gaps: tuple[EvidenceGap, ...] = ()


@dataclass(frozen=True)
class EvidenceGap:
    gap_id: str
    question: str
    status: str
    ranking_sensitivity: float
    uncertainty: float
    evidence_probability: float
    estimated_cost: float
    priority: float


@dataclass(frozen=True)
class MarketNode:
    node_id: str
    source_code: str
    title: str
    raw_title: str
    source_indicator: str | None
    level: int
    parent_id: str | None
    node_type: str
    lineage: tuple[str, ...]


@dataclass(frozen=True)
class MarketEvaluation:
    market_id: str
    title: str
    source_code: str
    status: str
    exclusion_reasons: tuple[str, ...]
    factor_scores: tuple[FactorScore, ...]
    aggregate_raw_score: float
    aggregate_confidence: float
    aggregate_risk_adjusted_score: float
    open_gaps: tuple[EvidenceGap, ...] = field(default_factory=tuple)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)

