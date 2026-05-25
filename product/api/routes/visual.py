"""Visual-context and perturbation-context endpoints.

Both handlers are thin wrappers around ``product.data.visual_context``
and ``product.data.perturbation_context``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from product.data import loaders
from product.data.perturbation_context import build_perturbation_context
from product.data.visual_context import build_visual_context

router = APIRouter(prefix="/prompts", tags=["visual"])

_DEFAULT_RUN = "full-run-v1"


@router.get("/{prompt_id}/visual-context")
def get_visual_context(prompt_id: str, run_id: str = _DEFAULT_RUN) -> dict:
    try:
        return build_visual_context(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{prompt_id}/perturbation-context")
def get_perturbation_context(prompt_id: str, run_id: str = _DEFAULT_RUN) -> dict:
    try:
        bundle = loaders.load_prompt_bundle(prompt_id, run_id=run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_perturbation_context(bundle)
