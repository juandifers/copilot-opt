"""System D-Final — LLM semantic intent adapter + deterministic contract.

D-Final layers an LLM-based semantic intent adapter in front of the
existing D2/D3/D4 deterministic contract pipeline.

The LLM maps natural-language prompts to a structured query frame;
all downstream contract logic (answerability, evidence, warnings,
refusals, compute decisions) remains deterministic and unchanged.

Adapter modes:
  hybrid_guarded  — recommended production path (d_final default)
  llm_only        — evaluation-only
  llm_fallback    — evaluation-only
"""
from __future__ import annotations

from product.evaluation.system_d_final.d_final_system_c import (
    PredictedContractDFinal,
    run_system_d_final_on_case,
    run_system_d_final_on_materialized,
)

__all__ = [
    "PredictedContractDFinal",
    "run_system_d_final_on_case",
    "run_system_d_final_on_materialized",
]
