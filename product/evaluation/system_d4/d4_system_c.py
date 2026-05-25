"""System D4 — wrapper around D3 that emits a ``compute_decision``.

D4 strictly delegates the contract pipeline to
``run_system_d3_on_case`` and then enriches the resulting
``PredictedContractD3`` with a ``ComputeDecision``. Every D3 field is
forwarded verbatim — no warning is added, no intent is changed, no
answerability is rewritten.

The wrapper never runs a solver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_payloads import MaterializedPayload
from product.evaluation.system_d3.d3_system_c import (
    PredictedContractD3,
    run_system_d3_on_case,
)
from product.evaluation.system_d4.compute_decision import (
    ComputeDecision,
    decide_compute,
)


@dataclass
class PredictedContractD4(PredictedContractD3):
    """D3 contract enriched with the D4 compute-decision object."""

    compute_decision: Optional[ComputeDecision] = None


def run_system_d4_on_case(
    case: Run2Case,
    payload: Optional[dict],
    generator_record: Optional[dict] = None,
) -> PredictedContractD4:
    """Run the D3 pipeline, then attach a deterministic compute decision."""
    d3 = run_system_d3_on_case(
        case=case, payload=payload, generator_record=generator_record
    )
    decision = decide_compute(
        prompt_text=case.prompt_text,
        intent=d3.predicted_intent,
        answerability_status=d3.predicted_answerability,
        warnings=list(d3.predicted_warnings),
        payload=payload,
        answerability_missing_fields=list(d3.predicted_missing_fields),
    )
    return PredictedContractD4(
        case_id=d3.case_id,
        predicted_intent=d3.predicted_intent,
        predicted_answerability=d3.predicted_answerability,
        predicted_evidence_paths=list(d3.predicted_evidence_paths),
        predicted_missing_fields=list(d3.predicted_missing_fields),
        predicted_warnings=list(d3.predicted_warnings),
        predicted_next_actions=list(d3.predicted_next_actions),
        predicted_behavior_class=d3.predicted_behavior_class,
        notes=list(d3.notes),
        query_frame=d3.query_frame,
        compute_decision=decision,
    )


def run_system_d4_on_materialized(
    case: Run2Case, mat: MaterializedPayload
) -> Optional[PredictedContractD4]:
    if mat.materialization_status != "materialized":
        return None
    return run_system_d4_on_case(
        case=case,
        payload=mat.payload,
        generator_record=mat.generator_record,
    )


__all__ = [
    "PredictedContractD4",
    "run_system_d4_on_case",
    "run_system_d4_on_materialized",
]
