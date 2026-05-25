"""Query frame for the System D1 semantic intent adapter.

A `QueryFrame` is a small structured record that bundles the
classifier's intent decision with the metadata D1 evaluation reports
need (which adapter produced the intent, why, what entities were
spotted, what comparator semantics were detected, whether the result
was overridden). The downstream contract pipeline only consumes the
`intent` field; the rest is bookkeeping.

This file is types-only — no I/O, no model calls, no imports from
sibling intent/refusal/evidence modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


ClassifierSource = Literal["c0", "semantic_adapter", "llm_adapter", "fallback"]

ComparisonType = Literal[
    "none",
    "baseline",
    "previous_solution",
    "reference_solver",
    "implicit",
]


@dataclass
class AmbiguitySignal:
    is_ambiguous: bool = False
    reason: Optional[str] = None


@dataclass
class QueryFrameEntities:
    customer_ids: list[int] = field(default_factory=list)
    route_labels: list[str] = field(default_factory=list)


@dataclass
class QueryFrame:
    """One classifier decision with provenance.

    `intent` is the canonical intent string consumed by downstream
    contract code. Every other field is metadata.
    """

    intent: str
    source: ClassifierSource = "c0"
    confidence: float = 1.0
    entities: QueryFrameEntities = field(default_factory=QueryFrameEntities)
    requires_baseline: bool = False
    comparison_type: ComparisonType = "none"
    ambiguity: AmbiguitySignal = field(default_factory=AmbiguitySignal)
    adapter_notes: list[str] = field(default_factory=list)
    c0_intent: Optional[str] = None
    overridden: bool = False
    model_name: Optional[str] = None


__all__ = [
    "AmbiguitySignal",
    "ClassifierSource",
    "ComparisonType",
    "QueryFrame",
    "QueryFrameEntities",
]
