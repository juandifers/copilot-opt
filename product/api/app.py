"""FastAPI app for the VRPTW copilot dashboard.

This app is a thin wrapper around the existing c0/d1/d2/d3 runners
and Run 1 scenario artifacts. It does not run the solver, does not
persist state, and does not introduce any new business logic.

Run locally:

    uvicorn product.api.app:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import subprocess
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from product.api import copilot_service, recompute_service, scenario_store, telemetry
from product.api.models import (
    ApiError,
    ApiErrorBody,
    CopilotAskRequest,
    CopilotAskResponse,
    DiffResponse,
    HealthResponse,
    InstanceSummary,
    InstancesResponse,
    RecomputeRequest,
    RecomputeResponseModel,
    ScenarioResponse,
)


RUN2_CONTRACT_BASE_COMMIT = "18b4811a1f85c166ea3ba8c777dfc021b2a5f747"
RUN2_CONTRACT_BASE_TAG = "run2-contract-extended"


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _error_response(status_code: int, code: str, message: str, **detail) -> JSONResponse:
    body = ApiError(error=ApiErrorBody(code=code, message=message, detail=detail or {}))
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _current_git_commit() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("ascii").strip()
    except Exception:  # noqa: BLE001 — non-git checkouts must still serve
        return None


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------


app = FastAPI(
    title="VRPTW Copilot Dashboard API",
    description=(
        "Read-only HTTP layer over the c0/d1/d2/d3 copilot contracts. "
        "Wraps existing Run 2 contract runners; no business logic in the "
        "API layer."
    ),
    version="1.0.0",
)

# Localhost dev origins only. Vite (5173), Next.js (3000), CRA (3000),
# and Storybook (6006) are the four the frontend repo is likely to use.
_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:6006",
    "http://127.0.0.1:6006",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handler for raised HTTPException with structured detail
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return _error_response(
        exc.status_code,
        code="http_error",
        message=str(detail) if detail is not None else "error",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        run2_contract_base_commit=RUN2_CONTRACT_BASE_COMMIT,
        run2_contract_base_tag=RUN2_CONTRACT_BASE_TAG,
        current_git_commit=_current_git_commit(),
        available_systems=list(copilot_service.AVAILABLE_SYSTEMS),
        default_system=copilot_service.DEFAULT_SYSTEM,
    )


@app.get("/instances", response_model=InstancesResponse)
def instances() -> InstancesResponse:
    rows = scenario_store.list_instances()
    return InstancesResponse(instances=[InstanceSummary(**r) for r in rows])


@app.get(
    "/scenarios/{instance_id}/{perturbation_id}",
    response_model=ScenarioResponse,
)
def scenario(instance_id: str, perturbation_id: str) -> ScenarioResponse:
    try:
        data = scenario_store.build_scenario_response(instance_id, perturbation_id)
    except scenario_store.ScenarioNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "scenario_not_found",
                    "message": (
                        f"No scenario for instance {instance_id!r} and "
                        f"perturbation {perturbation_id!r}."
                    ),
                    "detail": {"scenario_id": str(exc)},
                }
            },
        ) from exc
    return ScenarioResponse(**data)


@app.post("/copilot/ask", response_model=CopilotAskResponse)
def copilot_ask(req: CopilotAskRequest) -> CopilotAskResponse:
    import time as _time
    request_id = telemetry.new_request_id()
    started_at = _time.time()
    if "__" not in req.scenario_id:
        telemetry.log_copilot_ask(
            request_id=request_id,
            scenario_id=req.scenario_id,
            prompt=req.prompt,
            result=None,
            error_code="invalid_scenario_id",
            started_at=started_at,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "invalid_scenario_id",
                    "message": (
                        "scenario_id must be '<instance_id>__<perturbation_id>'."
                    ),
                    "detail": {"scenario_id": req.scenario_id},
                }
            },
        )
    instance_id, perturbation_id = req.scenario_id.split("__", 1)
    result: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    try:
        result = copilot_service.ask(
            instance_id=instance_id,
            perturbation_id=perturbation_id,
            prompt=req.prompt,
            system=req.system,
            family=req.family,
        )
    except copilot_service.UnknownSystemError as exc:
        error_code = "unknown_system"
        telemetry.log_copilot_ask(
            request_id=request_id,
            scenario_id=req.scenario_id,
            prompt=req.prompt,
            result=None,
            error_code=error_code,
            error_message=str(exc),
            started_at=started_at,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "unknown_system",
                    "message": (
                        f"Unknown system {str(exc)!r}; allowed: "
                        f"{list(copilot_service.AVAILABLE_SYSTEMS)}."
                    ),
                    "detail": {
                        "requested": str(exc),
                        "available": list(copilot_service.AVAILABLE_SYSTEMS),
                    },
                }
            },
        ) from exc
    except scenario_store.ScenarioNotFound as exc:
        error_code = "scenario_not_found"
        telemetry.log_copilot_ask(
            request_id=request_id,
            scenario_id=req.scenario_id,
            prompt=req.prompt,
            result=None,
            error_code=error_code,
            error_message=str(exc),
            started_at=started_at,
        )
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "scenario_not_found",
                    "message": f"Scenario {str(exc)!r} is not in the registry.",
                    "detail": {"scenario_id": str(exc)},
                }
            },
        ) from exc
    telemetry.log_copilot_ask(
        request_id=request_id,
        scenario_id=req.scenario_id,
        prompt=req.prompt,
        result=result,
        started_at=started_at,
    )
    return CopilotAskResponse(**result)


@app.post("/scenarios/{instance_id}/{perturbation_id}/diff", response_model=DiffResponse)
def scenario_diff(instance_id: str, perturbation_id: str) -> DiffResponse:
    try:
        diff = scenario_store.build_diff_response(instance_id, perturbation_id)
    except scenario_store.ScenarioNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "scenario_not_found",
                    "message": f"Scenario {str(exc)!r} is not in the registry.",
                    "detail": {"scenario_id": str(exc)},
                }
            },
        ) from exc
    if diff is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "diff_not_available",
                    "message": (
                        "This scenario does not include baseline/diff fields."
                    ),
                    "detail": {
                        "missing_fields": ["baseline_solution", "diff"],
                    },
                }
            },
        )
    return DiffResponse(**diff)


@app.post(
    "/scenarios/{instance_id}/{perturbation_id}/recompute",
    response_model=RecomputeResponseModel,
)
def scenario_recompute(
    instance_id: str, perturbation_id: str, req: RecomputeRequest
) -> RecomputeResponseModel:
    """D5 — operator-authorized recompute.

    Only executed when the request carries ``confirm == true`` and the
    requested action matches D4's recommendation. Never invoked by
    ``/copilot/ask``.
    """
    scenario_id = f"{instance_id}__{perturbation_id}"
    try:
        result = recompute_service.run_recompute(
            scenario_id=scenario_id,
            prompt=req.prompt,
            requested_action=req.requested_action,
            perturbation=req.perturbation,
            confirm=req.confirm,
        )
    except recompute_service.RecomputeError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.to_envelope()
        ) from exc
    return RecomputeResponseModel(**result.to_dict())


@app.get("/recompute_runs/{new_scenario_id}")
def runtime_scenario(new_scenario_id: str) -> dict:
    """Load a recomputed runtime scenario by its new_scenario_id.

    Returns the scenario doc materialized by the recompute service.
    Lives under ``/recompute_runs/`` so it does not collide with the
    canonical ``/scenarios/{instance_id}/{perturbation_id}`` path.
    """
    try:
        return recompute_service.load_runtime_scenario(new_scenario_id)
    except recompute_service.RecomputeError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.to_envelope()
        ) from exc


@app.get("/verification/cases")
def verification_cases() -> dict:
    """Optional debug endpoint exposing the Run 2 calibration case ids.

    Returns the list of case ids and their gold-label headline columns,
    so the dashboard can show a small verification view. If the
    calibration CSV is unavailable, returns an empty list rather than
    failing.
    """
    try:
        from product.evaluation.run2_case_loader import (
            default_cases_path,
            load_run2_cases,
        )

        cases = load_run2_cases(default_cases_path())
    except FileNotFoundError:
        return {"cases": []}
    except Exception:  # noqa: BLE001
        return {"cases": []}

    out: list[dict[str, Any]] = []
    for c in cases:
        out.append(
            {
                "case_id": c.case_id,
                "source_prompt_id": c.source_prompt_id,
                "family": c.family,
                "expected_intent": c.expected_intent,
                "expected_answerability": c.expected_answerability,
                "expected_behavior_class": c.expected_behavior_class,
                "difficulty": c.difficulty,
            }
        )
    return {"cases": out}


__all__ = ["app"]
