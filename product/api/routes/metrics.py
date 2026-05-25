"""Run-level product metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from product.data.metrics import compute_replay_metrics

router = APIRouter(prefix="/runs", tags=["metrics"])


@router.get("/{run_id}/product-metrics")
def get_product_metrics(run_id: str) -> dict:
    try:
        return compute_replay_metrics(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
