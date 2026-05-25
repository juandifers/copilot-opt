"""Run-level results listing.

Thin handler. Loads cached joined CSV via `product.data.loaders` and
returns the rows as native dicts. No inference happens here.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from product.api.schemas import ResultsResponse
from product.data import loaders

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}/results", response_model=ResultsResponse)
def list_run_results(run_id: str) -> ResultsResponse:
    try:
        rows = loaders.joined_records(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
    return ResultsResponse(run_id=run_id, n_rows=len(rows), rows=rows)
