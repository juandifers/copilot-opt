"""Copilot dispatch: route an ad-hoc question to c0/d1/d2/d3.

Thin adapter that constructs a synthetic ``Run2Case`` for the
operator-style question, calls the requested contract pipeline, and
reshapes the result into the dashboard's expected JSON envelope.

No business logic is added here. The API enriches each evidence item
with a frontend display anchor and tries to resolve the evidence
value from the augmented payload if the contract layer only emitted a
field path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from product.api import evidence_anchors
from product.api.scenario_store import (
    ScenarioRow,
    augmented_payload,
    get_scenario_row,
)
from product.copilot.contracts import EvidenceItem
from product.copilot.explanation_context import (
    build_explanation_context,
    context_card_to_evidence_items,
)
from product.copilot.llm_query_frame import OVERVIEW_INTENTS
from product.data import evidence as evidence_mod

from product.evaluation.run2_case_loader import Run2Case
from product.evaluation.run2_system_c import (
    PredictedContract,
    run_system_c_on_case,
)
from product.evaluation.system_d1.d1_system_c import (
    PredictedContractD1,
    run_system_d1_on_case,
)
from product.evaluation.system_d2.d2_system_c import (
    PredictedContractD2,
    run_system_d2_on_case,
)
from product.evaluation.system_d3.d3_system_c import (
    PredictedContractD3,
    run_system_d3_on_case,
)
from product.evaluation.system_d4 import (
    PredictedContractD4,
    run_system_d4_on_case,
)
from product.evaluation.system_d_final import (
    PredictedContractDFinal,
    run_system_d_final_on_case,
)


AVAILABLE_SYSTEMS: tuple[str, ...] = ("c0", "d1", "d2", "d3", "d4", "d_final")
# d_final passed all acceptance criteria on 2026-05-21 (97.9% semantic
# holdout, 100% heldout, 0 regressions). Promoted to frontend default.
DEFAULT_SYSTEM: str = "d_final"


class UnknownSystemError(ValueError):
    """Raised when a request asks for a system we do not expose."""


@dataclass
class _Dispatch:
    runner: Callable[..., PredictedContract]


def _run_d_final_on_case(case, payload, generator_record=None):
    """Wrapper that calls run_system_d_final_on_case without an LLM client.

    In API context without an explicit client object, d_final falls back
    to D1 deterministically. Pass a real client via the async pathway
    (not yet wired) for live LLM intent resolution.
    """
    return run_system_d_final_on_case(
        case=case,
        payload=payload,
        generator_record=generator_record,
        client=None,          # deterministic D1 fallback unless client injected
        mode="hybrid_guarded",
    )


_DISPATCH: dict[str, _Dispatch] = {
    "c0": _Dispatch(run_system_c_on_case),
    "d1": _Dispatch(run_system_d1_on_case),
    "d2": _Dispatch(run_system_d2_on_case),
    "d3": _Dispatch(run_system_d3_on_case),
    "d4": _Dispatch(run_system_d4_on_case),
    "d_final": _Dispatch(_run_d_final_on_case),
}


def _normalise_system(system: Optional[str]) -> str:
    if not system:
        return DEFAULT_SYSTEM
    s = str(system).strip().lower()
    # Tolerate the legacy alias "c-extended" for c0.
    if s in ("c-extended", "c_extended"):
        return "c0"
    if s not in _DISPATCH:
        raise UnknownSystemError(s)
    return s


def _build_case(scenario_row: ScenarioRow, prompt: str, family: str) -> Run2Case:
    """Build a synthetic Run2Case for an ad-hoc operator question.

    Required fields per ``Run2Case`` are filled with neutral defaults
    appropriate for an ad-hoc query (no calibration label, no gold).
    """
    case = Run2Case(
        case_id=f"api::{scenario_row.instance_id}__{scenario_row.perturbation_id}",
        source_prompt_id=scenario_row.prompt_id,
        family=family or scenario_row.family or "OBJ",
        prompt_text=prompt,
        payload_condition="clean",
        payload_mutation_needed="",
        expected_intent="",
        expected_answerability="",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="",
        implementation_status="api",
        difficulty="",
        label_rationale="",
        ambiguity_notes="",
    )
    return case


def _resolve_evidence_items(
    intent: str, payload: Optional[dict], generator_record: Optional[dict],
    prompt: str,
) -> list[EvidenceItem]:
    """Re-run the evidence extractor to attach values to each field path.

    The contract runners return just field paths in `predicted_evidence_paths`.
    The dashboard needs the actual value, so we call the same extractor
    the contract uses internally — no new business logic.
    """
    if not isinstance(payload, dict):
        return []
    return evidence_mod.build_evidence_items(
        intent=intent,
        payload=payload,
        generator_record=generator_record,
        row={"prompt_text": prompt},
    )


def _behavior_to_answer_text(
    predicted: PredictedContract,
    evidence_out: list[dict],
    prompt: str,
    compute_decision: Optional[dict],
) -> Optional[str]:
    """Render answer_text via the deterministic template verbalization renderer.

    Delegates entirely to ``product.copilot.verbalization.verbalize``, which
    is template-driven and makes no LLM calls. The structured contract fields
    (evidence, warnings, missing_fields, compute_decision) remain the source
    of truth; answer_text is a display convenience derived from them.

    On any rendering exception the function returns ``None`` so the caller
    still receives a complete structured response.
    """
    import logging

    from product.copilot.verbalization import verbalize

    try:
        return verbalize(
            intent=predicted.predicted_intent,
            answerability=predicted.predicted_answerability,
            behavior_class=predicted.predicted_behavior_class,
            # evidence_out already carries field_path + value from the
            # resolved evidence extractor; display_anchor is ignored by verbalize.
            evidence_items=evidence_out,
            warnings=list(predicted.predicted_warnings),
            missing_fields=list(predicted.predicted_missing_fields),
            next_actions=list(predicted.predicted_next_actions),
            prompt_text=prompt,
            compute_decision=compute_decision,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "verbalization failed for intent=%r; answer_text=null",
            predicted.predicted_intent,
        )
        return None


def ask(
    instance_id: str,
    perturbation_id: str,
    prompt: str,
    system: Optional[str] = None,
    family: Optional[str] = None,
) -> dict:
    """Run the chosen system on the scenario + prompt and shape the result."""
    sys_name = _normalise_system(system)
    row = get_scenario_row(instance_id, perturbation_id)
    payload = augmented_payload(row)

    case = _build_case(row, prompt=prompt, family=(family or "").strip() or row.family)

    runner = _DISPATCH[sys_name].runner
    predicted: PredictedContract = runner(
        case=case,
        payload=payload,
        generator_record=row.generator_record,
    )

    # Pull evidence values + display anchors. The runner emits paths
    # only; build_evidence_items gives us {path, value, supports}.
    evidence_items = _resolve_evidence_items(
        intent=predicted.predicted_intent,
        payload=payload,
        generator_record=row.generator_record,
        prompt=prompt,
    )
    evidence_by_path: dict[str, EvidenceItem] = {
        it.field_path: it for it in evidence_items
    }

    evidence_out: list[dict] = []
    seen: set[str] = set()
    for path in predicted.predicted_evidence_paths:
        if path in seen:
            continue
        seen.add(path)
        item = evidence_by_path.get(path)
        evidence_out.append(
            {
                "field_path": path,
                "value": (item.value if item is not None else None),
                "display_anchor": evidence_anchors.field_path_to_display_anchor(
                    path, payload
                ),
            }
        )
    # Surface any extra evidence the extractor produced but the runner
    # did not list (rare; helps the dashboard show all grounded values).
    for item in evidence_items:
        if item.field_path in seen:
            continue
        seen.add(item.field_path)
        evidence_out.append(
            {
                "field_path": item.field_path,
                "value": item.value,
                "display_anchor": evidence_anchors.field_path_to_display_anchor(
                    item.field_path, payload
                ),
            }
        )

    # Overview intents read from a payload-derived explanation-context
    # card rather than from raw payload field paths. The card is
    # appended to evidence_out as ``explanation_context.*`` items; the
    # downstream verbalization renderer consumes them via the same
    # ``_ev_value`` / ``_ev_all`` helpers used for normal evidence.
    if predicted.predicted_intent in OVERVIEW_INTENTS:
        scenario_id_local = f"{row.instance_id}__{row.perturbation_id}"
        card = build_explanation_context(
            scenario_payload=payload,
            intent=predicted.predicted_intent,
            scenario_id=scenario_id_local,
            instance_id=row.instance_id,
            perturbation_id=row.perturbation_id,
            perturbation_family=row.perturbation_family,
            prompt=prompt,
        )
        for item in context_card_to_evidence_items(card):
            if item["field_path"] in seen:
                continue
            seen.add(item["field_path"])
            evidence_out.append(item)

        # The locked Run-2 behaviour-class inference (run2_system_c
        # ``_infer_behavior_class``) collapses partially_answerable + no
        # evidence to ``useful_refusal``. For overview intents, the
        # context card IS the evidence — adjust the behaviour class so
        # the renderer dispatches to the overview path instead of the
        # generic useful_refusal text.
        status = predicted.predicted_answerability
        warnings_list = list(predicted.predicted_warnings)
        if status == "answerable":
            predicted.predicted_behavior_class = (
                "direct_answer_with_warning" if warnings_list else "direct_answer"
            )
        elif status == "partially_answerable":
            predicted.predicted_behavior_class = "partial_answer_with_warning"
        # not_answerable keeps useful_refusal — that's the right
        # behaviour when even the context card cannot be built.

    # D4 and D-Final enrich the response with a compute_decision object.
    compute_decision = None
    if isinstance(predicted, (PredictedContractD4, PredictedContractDFinal)):
        if predicted.compute_decision:
            compute_decision = predicted.compute_decision.model_dump()

    # D-Final includes semantic adapter metadata.
    semantic_adapter = None
    if isinstance(predicted, PredictedContractDFinal) and predicted.adapter_metadata:
        am = predicted.adapter_metadata
        semantic_adapter = {
            "mode": am.mode,
            "source": am.source,
            "accepted": am.accepted,
            "fallback_used": am.fallback_used,
            "confidence": am.confidence,
            "model_name": am.model_name,
            "latency_ms": am.latency_ms,
            "schema_valid": am.schema_valid,
            "validation_outcome": am.validation_outcome,
        }

    scenario_id = f"{row.instance_id}__{row.perturbation_id}"
    ui_actions = _build_ui_actions(compute_decision, scenario_id)

    result = {
        "system": sys_name,
        "scenario_id": scenario_id,
        "intent": predicted.predicted_intent,
        "answerability": {
            "status": predicted.predicted_answerability,
            "missing_fields": list(predicted.predicted_missing_fields),
        },
        "behavior_class": predicted.predicted_behavior_class,
        "answer_text": _behavior_to_answer_text(
            predicted, evidence_out, prompt, compute_decision
        ),
        "evidence": evidence_out,
        "warnings": list(predicted.predicted_warnings),
        "useful_refusal": None,
        "suggested_next_actions": list(predicted.predicted_next_actions),
        "compute_decision": compute_decision,
        "ui_actions": ui_actions,
    }
    if semantic_adapter is not None:
        result["semantic_adapter"] = semantic_adapter
    return result


def _build_ui_actions(
    compute_decision: Optional[dict],
    scenario_id: str,
) -> list[dict]:
    """Emit a frontend-facing ``ui_actions`` list.

    Currently emits a single ``recompute`` action when D4's
    ``compute_decision.mode == "needs_recompute"`` and the recommended
    action is one of the D5-deployable rungs. ``/copilot/ask`` never
    runs the solver itself; the recompute is performed only after the
    operator clicks the affordance and the explicit recompute endpoint
    receives a confirmed request.
    """
    # Imported lazily to avoid a circular import on package init.
    from product.api.recompute_service import ALLOWED_ACTIONS

    if not isinstance(compute_decision, dict):
        return []
    if compute_decision.get("mode") != "needs_recompute":
        return []
    action = compute_decision.get("recommended_action")
    if action not in ALLOWED_ACTIONS:
        return []
    return [
        {
            "type": "recompute",
            "label": "Run recompute",
            "action": action,
            "enabled": True,
            "requires_confirmation": True,
            "endpoint": f"/scenarios/{scenario_id}/recompute",
            "method": "POST",
            "reason": compute_decision.get("reason", ""),
            "expected_runtime_seconds": compute_decision.get(
                "expected_runtime_seconds"
            ),
        }
    ]


__all__ = ["AVAILABLE_SYSTEMS", "DEFAULT_SYSTEM", "UnknownSystemError", "ask"]
