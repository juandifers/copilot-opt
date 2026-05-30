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

import os
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


_LLM_CLIENT_CACHED: Any = None
_LLM_CLIENT_PROBED: bool = False


def _get_llm_client() -> Any:
    """Lazily load an OpenAI client for the live d_final path.

    Returns ``None`` (deterministic D1 fallback) when:
      - ``COPILOT_DISABLE_LLM=1`` is set (kill switch), or
      - ``OPENAI_API_KEY`` is not configured, or
      - The client SDK isn't installed, or
      - Any other error occurs during construction.

    Caches the client on first successful load. Probe-once semantics
    means a missing key is logged once, not on every request.
    """
    global _LLM_CLIENT_CACHED, _LLM_CLIENT_PROBED
    if _LLM_CLIENT_PROBED:
        return _LLM_CLIENT_CACHED
    _LLM_CLIENT_PROBED = True
    if os.environ.get("COPILOT_DISABLE_LLM", "").strip() in {"1", "true", "yes", "on"}:
        return None
    try:
        from product.evaluation.model_clients.openai_client import (
            load_openai_client,
            OpenAIKeyMissingError,
        )
        _LLM_CLIENT_CACHED = load_openai_client()
        import logging
        logging.getLogger(__name__).info(
            "copilot_service: live LLM client loaded (d_final will call the model)"
        )
    except Exception as exc:  # noqa: BLE001 — never break /copilot/ask on client load
        import logging
        logging.getLogger(__name__).warning(
            "copilot_service: LLM client unavailable (%s); falling back to D1",
            type(exc).__name__,
        )
        _LLM_CLIENT_CACHED = None
    return _LLM_CLIENT_CACHED


def _run_d_final_on_case(case, payload, generator_record=None):
    """Wrapper that calls run_system_d_final_on_case with the cached client.

    When the OpenAI client is loadable (OPENAI_API_KEY set, SDK installed,
    kill-switch off), d_final makes real LLM calls in hybrid_guarded mode.
    Otherwise it falls back to deterministic D1.
    """
    return run_system_d_final_on_case(
        case=case,
        payload=payload,
        generator_record=generator_record,
        client=_get_llm_client(),
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
    prompt: str, query_frame: Optional[Any] = None,
    family: str = "", perturbation_id: str = "",
) -> list[EvidenceItem]:
    """Re-run the evidence extractor to attach values to each field path.

    The contract runners return just field paths in `predicted_evidence_paths`.
    The dashboard needs the actual value, so we call the same extractor
    the contract uses internally — no new business logic. ``query_frame``
    is forwarded so the aspectual-fallback path dispatches identically
    here as it did inside the runner. ``family`` is plumbed through so
    the B1 ranking aspect can resolve family-compatibility.
    ``perturbation_id`` is plumbed through so the A-008 evaluation
    aspect can select the OBJ per-perturbation threshold.
    """
    if not isinstance(payload, dict):
        return []
    return evidence_mod.build_evidence_items(
        intent=intent,
        payload=payload,
        generator_record=generator_record,
        row={"prompt_text": prompt, "family": family, "perturbation_id": perturbation_id},
        query_frame=query_frame,
    )


def _behavior_to_answer_text(
    predicted: PredictedContract,
    evidence_out: list[dict],
    prompt: str,
    compute_decision: Optional[dict],
    perturbation_type: Optional[str] = None,
) -> Optional[str]:
    """Render answer_text via the deterministic template verbalization renderer.

    Delegates entirely to ``product.copilot.verbalization.verbalize``, which
    is template-driven and makes no LLM calls. The structured contract fields
    (evidence, warnings, missing_fields, compute_decision) remain the source
    of truth; answer_text is a display convenience derived from them.

    ``perturbation_type`` (e.g. ``"TT_4"`` or ``"TRAVEL_TIME"``) is plumbed
    through so the B4 causal narration can render perturbation-aware "this
    change occurred because…" sentences on delta/comparison responses.

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
            perturbation_type=perturbation_type,
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
    qf_for_resolve = (
        predicted.query_frame
        if isinstance(predicted, PredictedContractDFinal)
        else None
    )
    evidence_items = _resolve_evidence_items(
        intent=predicted.predicted_intent,
        payload=payload,
        generator_record=row.generator_record,
        prompt=prompt,
        query_frame=qf_for_resolve,
        family=case.family or row.family or "",
        perturbation_id=row.perturbation_id or "",
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
                "supports": (item.supports if item is not None else None),
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
                "supports": item.supports,
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
        qf = predicted.query_frame
        entities_block: Optional[dict] = None
        if qf is not None and qf.entities is not None:
            cids = list(qf.entities.customer_ids or [])
            rlabels = list(qf.entities.route_labels or [])
            if cids or rlabels:
                entities_block = {
                    "customer_ids": cids,
                    "route_labels": rlabels,
                }
        semantic_adapter = {
            "mode": am.mode,
            "source": am.source,
            "accepted": am.accepted,
            "fallback_used": am.fallback_used,
            "fallback_reason": am.fallback_reason,
            "confidence": am.confidence,
            "model_name": am.model_name,
            "latency_ms": am.latency_ms,
            "schema_valid": am.schema_valid,
            "validation_outcome": am.validation_outcome,
            "d1_intent": am.d1_intent,
            "llm_intent": am.llm_intent,
            "rejected_llm_entities": am.rejected_llm_entities,
            "entities": entities_block,
            "validation_error_details": am.validation_error_details,
            "counterfactual_guard_fired": am.counterfactual_guard_fired,
            "ranking_guard_fired": am.ranking_guard_fired,
            "evaluation_guard_fired": am.evaluation_guard_fired,
            # A-008.5 R2 retry telemetry
            "retry_fired": am.retry_fired,
            "retry_success": am.retry_success,
            "retry_reason": am.retry_reason,
            "retry_latency_ms": am.retry_latency_ms,
        }

    scenario_id = f"{row.instance_id}__{row.perturbation_id}"
    ui_actions = _build_ui_actions(compute_decision, scenario_id)

    # Aspectual-dispatch metadata (lateness pilot).
    #
    # When the intent classifier returned "unknown" but the evidence layer
    # surfaced field paths via the within-family aspectual fallback, the
    # frontend needs a signal to (a) suppress the compute_decision banner
    # which will read "clarification_needed" and clash with the
    # aspect-grounded answer, and (b) render the response with an
    # appropriate "I couldn't classify but here's what I see" framing.
    aspectual_dispatch = None
    # A-008: evaluation aspect — when an evaluation intent fires, emit
    # the verdict, per-check details, and PV-exception flag so the UI
    # / telemetry has the threshold story alongside the prose.
    if predicted.predicted_intent in (
        "evaluate_plan_acceptability",
        "evaluate_dimension_acceptability",
    ):
        from product.copilot.evaluation import (
            detect_dimension, evaluate_plan, evaluate_dimension,
        )
        _pert = row.perturbation_id or ""
        if predicted.predicted_intent == "evaluate_dimension_acceptability":
            dim = detect_dimension(prompt) or ""
            _ev_result = evaluate_dimension(payload or {}, _pert, dim)
        else:
            _ev_result = evaluate_plan(payload or {}, _pert)
        aspectual_dispatch = {
            "triggered": True,
            "intent_at_dispatch": predicted.predicted_intent,
            "family": (case.family or row.family or "").upper(),
            "aspect": "evaluation",
            "verdict": _ev_result.verdict,
            "pv_exception_applied": _ev_result.pv_exception_applied,
            "conservative_bias_applied": _ev_result.conservative_bias_applied,
            "failing_dimensions": list(_ev_result.failing_dimensions),
            "checks": [
                {
                    "dimension": f"{c.threshold.family.lower()}.{c.threshold.metric}",
                    "observed": c.observed_value,
                    "threshold": c.threshold.threshold_value,
                    "passes": c.passes,
                    "margin_pct": c.margin_pct,
                    "conservative_bias_applied": c.conservative_bias_applied,
                    "rationale_ref": c.threshold.rationale_ref,
                }
                for c in _ev_result.checks
            ],
        }

    # B1 (A-006): ranking aspect — detected via the prompt text. Runs
    # before the lateness/timing detection because a ranking prompt may
    # also lexically match the lateness pattern.
    rspec = evidence_mod.derive_ranking_spec(
        prompt, case.family or row.family or ""
    )
    if (
        predicted.predicted_intent == "unknown"
        and evidence_out
        and rspec is not None
        and rspec.family_compatible
    ):
        aspectual_dispatch = {
            "triggered": True,
            "intent_at_dispatch": "unknown",
            "family": (case.family or row.family or "").upper(),
            "aspect": "ranking",
            "ranking_target": rspec.target,
            "ranking_dimension": rspec.dimension,
            "top_k": rspec.top_k,
            "family_constraint_hit": False,
            "ambiguity_note": rspec.ambiguity_note,
            # R3 (A-008.5): structured ambiguity surface. ``ambiguity_detected``
            # is True iff the prompt had a bare superlative without an
            # explicit dimension keyword; ``alternatives`` is the structured
            # rephrasing list the verbalizer renders. Empty list when the
            # R3 flag is disabled or when no alternative dimensions apply.
            "ambiguity_detected": rspec.ambiguity_note is not None,
            "alternatives": [
                {
                    "dimension": alt.dimension,
                    "label": alt.label,
                    "example_phrasing": alt.example_phrasing,
                }
                for alt in (getattr(rspec, "alternatives", None) or [])
            ],
            "field_paths_surfaced": [ev.get("field_path") for ev in evidence_out],
        }
    if (
        aspectual_dispatch is None
        and predicted.predicted_intent == "unknown"
        and evidence_out
        and evidence_mod.is_schedule_payload(payload)
    ):
        # Re-derive the same aspect the dispatcher used. Cheap regex on
        # the prompt; the resolved entity sets are reconstructed from the
        # field paths actually surfaced.
        resolved_cids: list[int] = []
        resolved_route_idxs: list[int] = []
        for ev in evidence_out:
            path = ev.get("field_path") or ""
            import re as _re_local
            m_c = _re_local.search(r"customer_id=(\d+)", path)
            if m_c:
                v = int(m_c.group(1))
                if v not in resolved_cids:
                    resolved_cids.append(v)
            m_r = _re_local.search(r"route_idx=(\d+)", path)
            if m_r:
                v = int(m_r.group(1))
                if v not in resolved_route_idxs:
                    resolved_route_idxs.append(v)
        aspect = evidence_mod.derive_aspect(
            prompt, has_entities=bool(resolved_cids or resolved_route_idxs)
        )
        if aspect is not None:
            aspectual_dispatch = {
                "triggered": True,
                "intent_at_dispatch": "unknown",
                "family": "SCHEDULE",
                "aspect": aspect,
                "entities_resolved": {
                    "customer_ids": resolved_cids,
                    "route_labels": [f"Route {idx + 1}" for idx in resolved_route_idxs],
                },
                "field_paths_surfaced": [ev.get("field_path") for ev in evidence_out],
            }

    # Derive highlight hints from (intent, evidence_items). Empty for
    # refusal_or_insufficient_payload / unknown so the frontend keeps the
    # operator's current lens. See docs/highlight_contract.md.
    visual_actions = evidence_mod.infer_visual_actions(
        predicted.predicted_intent, evidence_items
    )

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
            predicted, evidence_out, prompt, compute_decision,
            perturbation_type=row.perturbation_id,
        ),
        "evidence": evidence_out,
        "warnings": list(predicted.predicted_warnings),
        "useful_refusal": None,
        "suggested_next_actions": list(predicted.predicted_next_actions),
        "compute_decision": compute_decision,
        "ui_actions": ui_actions,
        "visual_actions": [va.model_dump() for va in visual_actions],
    }
    if semantic_adapter is not None:
        result["semantic_adapter"] = semantic_adapter
    if aspectual_dispatch is not None:
        result["aspectual_dispatch"] = aspectual_dispatch
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
