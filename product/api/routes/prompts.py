"""Per-prompt endpoints: metadata, payload, copilot context, evidence, answerability.

Each handler is a thin wrapper around `product.copilot.response_builder`
and `product.data.*`. No business logic lives in this file.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from product.api.schemas import (
    AnswerabilityResponse,
    EvidenceResponse,
    PayloadResponse,
    PromptResponse,
    ProductCopilotResponse,
)
from product.copilot.response_builder import (
    _generator_answer_from_record,
    _prompt_metadata_from_bundle,
    build_replay_response,
)
from product.data import loaders, payloads, product_schema

router = APIRouter(prefix="/prompts", tags=["prompts"])

_DEFAULT_RUN = "full-run-v1"


def _bundle_or_404(prompt_id: str, run_id: str) -> dict:
    try:
        return loaders.load_prompt_bundle(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{prompt_id}", response_model=PromptResponse)
def get_prompt(prompt_id: str, run_id: str = _DEFAULT_RUN) -> PromptResponse:
    bundle = _bundle_or_404(prompt_id, run_id)
    return PromptResponse(
        run_id=bundle["run_id"],
        prompt_id=bundle["prompt_id"],
        prompt=_prompt_metadata_from_bundle(bundle),
        generator_answer=_generator_answer_from_record(bundle.get("generator_record")),
        judge=bundle.get("judge_record"),
        joined_row=bundle["joined_row"],
        warnings=bundle.get("warnings", []),
    )


@router.get("/{prompt_id}/payload", response_model=PayloadResponse)
def get_payload(prompt_id: str, run_id: str = _DEFAULT_RUN) -> PayloadResponse:
    bundle = _bundle_or_404(prompt_id, run_id)
    payload = payloads.parse_payload_snapshot(bundle.get("generator_record"))
    augmented = product_schema.augment_payload_for_product(payload)
    fields = payloads.available_payload_fields(augmented)
    return PayloadResponse(
        run_id=bundle["run_id"],
        prompt_id=bundle["prompt_id"],
        payload=payload,
        payload_augmented=augmented,
        available_fields=fields,
        source="generator_record" if payload is not None else "missing",
        warnings=bundle.get("warnings", []),
    )


@router.get("/{prompt_id}/copilot-context", response_model=ProductCopilotResponse)
def get_copilot_context(prompt_id: str, run_id: str = _DEFAULT_RUN) -> ProductCopilotResponse:
    try:
        return build_replay_response(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{prompt_id}/evidence", response_model=EvidenceResponse)
def get_evidence(prompt_id: str, run_id: str = _DEFAULT_RUN) -> EvidenceResponse:
    try:
        response = build_replay_response(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvidenceResponse(
        run_id=response.run_id,
        prompt_id=response.prompt_id,
        intent=response.intent,
        evidence=response.evidence,
        visual_actions=response.visual_actions,
    )


@router.get("/{prompt_id}/answerability", response_model=AnswerabilityResponse)
def get_answerability(prompt_id: str, run_id: str = _DEFAULT_RUN) -> AnswerabilityResponse:
    try:
        response = build_replay_response(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnswerabilityResponse(
        run_id=response.run_id,
        prompt_id=response.prompt_id,
        answerability=response.answerability,
    )
