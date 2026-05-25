"""Instance-geometry endpoint.

Thin handler around ``product.data.instance_geom.load_instance_geometry``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from product.data.instance_geom import load_instance_geometry

router = APIRouter(prefix="/instances", tags=["instances"])


@router.get("/{instance_id}/geometry")
def get_instance_geometry(instance_id: str) -> dict:
    try:
        return load_instance_geometry(instance_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
