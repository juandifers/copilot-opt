"""HTTP response envelopes for the dashboard API.

The substantive response shape (`ProductCopilotResponse`) lives in
`product.copilot.contracts`. This module adds list-style wrappers and
re-exports.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from product.copilot.contracts import (
    AnswerabilityResult,
    EvidenceItem,
    GeneratorAnswer,
    ProductCopilotResponse,
    PromptMetadata,
    VisualAction,
)


class ResultsResponse(BaseModel):
    run_id: str
    n_rows: int
    rows: list[dict]


class PromptResponse(BaseModel):
    run_id: str
    prompt_id: str
    prompt: PromptMetadata
    generator_answer: GeneratorAnswer
    judge: Optional[dict] = None
    joined_row: dict
    warnings: list[str] = []


class PayloadResponse(BaseModel):
    run_id: str
    prompt_id: str
    payload: Optional[dict] = None
    payload_augmented: Optional[dict] = None
    available_fields: list[str] = []
    source: str  # "generator_record" or "missing"
    warnings: list[str] = []


class EvidenceResponse(BaseModel):
    run_id: str
    prompt_id: str
    intent: str
    evidence: list[EvidenceItem]
    visual_actions: list[VisualAction]


class AnswerabilityResponse(BaseModel):
    run_id: str
    prompt_id: str
    answerability: AnswerabilityResult


__all__ = [
    "ResultsResponse",
    "PromptResponse",
    "PayloadResponse",
    "EvidenceResponse",
    "AnswerabilityResponse",
    "ProductCopilotResponse",
]
