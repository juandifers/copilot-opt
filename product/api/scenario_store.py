"""Scenario registry and shaping for the dashboard API.

A "scenario" here is one (instance_id, perturbation_id) cell from the
Run 1 prompt set, paired with its locked payload_snapshot. Scenarios
are read-only: we never compute a solution, we never re-derive
business facts. We only assemble what already exists into a shape the
frontend can render.

Sources (read-only):
- ``experiment/data/prompts.csv``        — locked prompt set
- ``experiment/results_RUN1/generator/full-run-v1.jsonl``
                                          — per-prompt payload_snapshot
- ``product.data.instance_geom``         — VRPTW instance coordinates
- ``product.data.product_schema``        — display-label augmentation

Multiple prompts can share a single (instance_id, perturbation_id);
we keep the first payload_snapshot we see for that cell.
"""
from __future__ import annotations

import copy
import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from product.data import product_schema
from product.evaluation.run2_payloads import (
    _load_generator_records,
    _normalize_prompt_id,
    _repo_root,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScenarioRow:
    """One row of the scenario registry.

    Carries the underlying prompt context (family, dataset, action_taken)
    so the copilot adapter can default to a sensible ``family`` and so
    instance metadata can be filled out without re-parsing CSV.
    """

    instance_id: str
    perturbation_id: str
    family: str
    perturbation_family: str
    instance_class: str
    dataset: str
    prompt_id: str
    prompt_text: str
    payload_snapshot: Optional[dict]
    generator_record: Optional[dict]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _prompts_csv_path() -> Path:
    return _repo_root() / "experiment" / "data" / "prompts.csv"


# Run 1 artifacts may live under ``results`` or ``results_RUN1``; the
# `_load_generator_records` helper already handles that fallback.
_DEFAULT_RUN_ID = "full-run-v1"


# ---------------------------------------------------------------------------
# Registry build
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_registry(run_id: str = _DEFAULT_RUN_ID) -> dict[str, ScenarioRow]:
    """Return ``{scenario_id: ScenarioRow}`` for the locked Run 1 set.

    A scenario id is ``"{instance_id}__{perturbation_id}"``. The first
    prompt seen for a cell wins; later prompts are ignored.
    """
    out: dict[str, ScenarioRow] = {}
    generator_records = _load_generator_records(run_id)

    with _prompts_csv_path().open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            instance_id = (row.get("instance_id") or "").strip()
            perturbation_id = (row.get("perturbation_id") or "").strip()
            if not instance_id or not perturbation_id:
                continue
            scenario_id = f"{instance_id}__{perturbation_id}"
            if scenario_id in out:
                continue
            pid = _normalize_prompt_id(row.get("prompt_id"))
            gen_rec = generator_records.get(pid)
            payload = None
            if isinstance(gen_rec, dict):
                ps = gen_rec.get("payload_snapshot")
                if isinstance(ps, dict):
                    payload = ps
            out[scenario_id] = ScenarioRow(
                instance_id=instance_id,
                perturbation_id=perturbation_id,
                family=(row.get("family") or "").strip(),
                perturbation_family=(row.get("perturbation_family") or "").strip(),
                instance_class=(row.get("instance_class") or "").strip(),
                dataset=(row.get("dataset") or "").strip(),
                prompt_id=pid,
                prompt_text=(row.get("prompt_text") or "").strip(),
                payload_snapshot=payload,
                generator_record=gen_rec,
            )
    return out


def list_instances(run_id: str = _DEFAULT_RUN_ID) -> list[dict]:
    """Return one entry per instance with its available perturbations.

    Instance family is inferred from instance id (``..._2_...`` → 200-customer
    Homberger; otherwise Solomon). ``n_customers`` is derived from instance
    geometry; if geometry cannot be loaded we report ``None`` instead of
    guessing.
    """
    from product.data.instance_geom import load_instance_geometry

    registry = load_registry(run_id)
    by_instance: dict[str, dict] = {}
    for scenario in registry.values():
        inst = by_instance.setdefault(
            scenario.instance_id,
            {
                "instance_id": scenario.instance_id,
                "family": "homberger200"
                if "_2_" in scenario.instance_id
                else "solomon100",
                "n_customers": None,
                "available_perturbations": [],
            },
        )
        if scenario.perturbation_id not in inst["available_perturbations"]:
            inst["available_perturbations"].append(scenario.perturbation_id)

    # Fill in n_customers lazily; missing geometry is non-fatal.
    for inst in by_instance.values():
        try:
            geom = load_instance_geometry(inst["instance_id"])
            inst["n_customers"] = int(geom.get("n_customers")) if geom else None
        except FileNotFoundError:
            inst["n_customers"] = None
        except Exception:  # noqa: BLE001 — geometry is decorative metadata
            inst["n_customers"] = None
        inst["available_perturbations"].sort()

    return sorted(by_instance.values(), key=lambda d: d["instance_id"])


# ---------------------------------------------------------------------------
# Scenario assembly
# ---------------------------------------------------------------------------


_PERTURBATION_SUMMARIES = {
    "TT": "Travel times scaled",
    "TW": "Time windows perturbed",
    "ST": "Service times scaled",
    "OC": "Customer-orders perturbed (new orders inserted)",
}


def _perturbation_summary(perturbation_id: str, perturbation_family: str) -> str:
    fam = (perturbation_family or "").upper()
    if fam:
        base = {
            "TRAVEL_TIME": "Travel-time perturbation",
            "TIME_WINDOW": "Time-window perturbation",
            "SERVICE_TIME": "Service-time perturbation",
            "CUSTOMER_ORDERS": "Customer-orders perturbation (new orders)",
        }.get(fam)
        if base:
            return f"{base} ({perturbation_id})"
    code = (perturbation_id or "").split("_", 1)[0]
    base = _PERTURBATION_SUMMARIES.get(code)
    if base:
        return f"{base} ({perturbation_id})"
    return f"Perturbation {perturbation_id}"


def _build_instance_block(instance_id: str) -> Optional[dict]:
    """Return the depot/customers/capacity block, or None if unavailable."""
    from product.data.instance_geom import load_instance_geometry

    try:
        geom = load_instance_geometry(instance_id)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 — instance geometry is decorative
        return None

    def _customer_row(c: dict) -> dict:
        return {
            "customer_id": int(c["customer_id"]),
            "x": float(c["x"]),
            "y": float(c["y"]),
            "demand": int(c["demand"]),
            "time_window_start": float(c["tw_early"]),
            "time_window_end": float(c["tw_late"]),
            "service_time": float(c["service_time"]),
        }

    depot = geom.get("depot") or {}
    return {
        "depot": {"x": float(depot.get("x", 0.0)), "y": float(depot.get("y", 0.0))},
        "customers": [_customer_row(c) for c in geom.get("customers", [])],
        "vehicle_capacity": int(geom.get("capacity")) if geom.get("capacity") else None,
    }


def _route_label_for(row: dict, fallback_idx: int) -> str:
    label = row.get("route_label")
    if isinstance(label, str) and label:
        return label
    return f"Route {fallback_idx + 1}"


def _route_load_for(route_idx: int, payload: dict) -> Optional[int]:
    """Sum demands of customers on this route from the augmented payload."""
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return None
    customer_ids: list[int] = []
    for r in routes:
        if not isinstance(r, dict):
            continue
        try:
            if int(r.get("route_idx")) != route_idx:
                continue
        except (TypeError, ValueError):
            continue
        for cid in r.get("customer_ids") or []:
            try:
                customer_ids.append(int(cid))
            except (TypeError, ValueError):
                continue
        break
    if not customer_ids:
        return None
    # Demand map is in the instance geometry; we leave load=None if we
    # cannot resolve it (e.g. geometry missing). The frontend treats
    # None as "unknown".
    return None


def _build_routes_block(payload: dict) -> Optional[list[dict]]:
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        return None
    end_time_by_idx: dict[int, float] = {}
    for r in payload.get("route_end_times") or []:
        if not isinstance(r, dict):
            continue
        try:
            end_time_by_idx[int(r.get("route_idx"))] = float(r.get("end_time"))
        except (TypeError, ValueError):
            continue

    out: list[dict] = []
    for r in routes:
        if not isinstance(r, dict) or "route_idx" not in r:
            continue
        try:
            route_idx = int(r["route_idx"])
        except (TypeError, ValueError):
            continue
        try:
            customer_ids = [int(c) for c in (r.get("customer_ids") or [])]
        except (TypeError, ValueError):
            customer_ids = []
        out.append(
            {
                "route_idx": route_idx,
                "route_label": _route_label_for(r, route_idx),
                "customer_ids": customer_ids,
                "load": None,
                "capacity": None,
                "distance": None,
                "end_time": end_time_by_idx.get(route_idx),
            }
        )
    out.sort(key=lambda d: d["route_idx"])
    return out


def _build_customer_schedule_block(payload: dict) -> Optional[list[dict]]:
    schedule = payload.get("customer_schedule")
    if not isinstance(schedule, list) or not schedule:
        return None
    out: list[dict] = []
    counters: dict[int, int] = {}
    for row in schedule:
        if not isinstance(row, dict):
            continue
        try:
            route_idx = int(row["route_idx"])
            customer_id = int(row["customer_id"])
        except (KeyError, TypeError, ValueError):
            continue
        pos = counters.get(route_idx, 0)
        counters[route_idx] = pos + 1
        arrival = row.get("arrival")
        start = row.get("start_service") if "start_service" in row else arrival
        end = row.get("end_service")
        tw_early = row.get("tw_early")
        tw_late = row.get("tw_late")
        is_late = bool(row.get("is_late"))
        late_min = row.get("lateness_minutes")
        out.append(
            {
                "customer_id": customer_id,
                "route_idx": route_idx,
                "route_label": _route_label_for(row, route_idx),
                "position_in_route": pos,
                "arrival": float(arrival) if arrival is not None else None,
                "service_start": float(start) if start is not None else None,
                "service_end": float(end) if end is not None else None,
                "time_window_start": float(tw_early) if tw_early is not None else None,
                "time_window_end": float(tw_late) if tw_late is not None else None,
                "is_late": is_late,
                "lateness_minutes": float(late_min) if late_min is not None else 0.0,
                "waiting_minutes": None,
            }
        )
    return out


def _build_solution_block(payload: dict) -> Optional[dict]:
    """Compose the solution sub-object from payload fields. Returns None
    if there is nothing solution-shaped to show."""
    has_anything = any(
        k in payload
        for k in (
            "action_objective",
            "feasible",
            "n_routes",
            "routes",
            "customer_schedule",
            "route_end_times",
        )
    )
    if not has_anything:
        return None

    routes_block = _build_routes_block(payload)
    schedule_block = _build_customer_schedule_block(payload)

    feasible = payload.get("feasible")
    if feasible is None and "feasibility_breakdown" in payload:
        # If a breakdown is present but no top-level boolean, treat as
        # unknown rather than guessing.
        feasible = None

    objective = payload.get("action_objective")
    n_routes = payload.get("n_routes")
    if n_routes is None and isinstance(routes_block, list):
        n_routes = len(routes_block)

    return {
        "feasible": bool(feasible) if feasible is not None else None,
        "objective": float(objective) if isinstance(objective, (int, float)) else None,
        "n_routes": int(n_routes) if isinstance(n_routes, (int, float)) else None,
        "routes": routes_block,
        "customer_schedule": schedule_block,
    }


def _available_fields_block(payload: Optional[dict]) -> dict:
    if not isinstance(payload, dict):
        return {
            "solution": False,
            "routes": False,
            "customer_schedule": False,
            "route_end_times": False,
            "baseline_solution": False,
            "diff": False,
            "objective_delta": False,
            "causal_diagnostics": False,
        }
    has_obj_delta = any(
        k in payload
        for k in (
            "baseline_objective",
            "objective_delta_absolute",
            "objective_delta_percent",
        )
    )
    return {
        "solution": any(
            k in payload
            for k in (
                "action_objective",
                "feasible",
                "n_routes",
                "routes",
                "customer_schedule",
            )
        ),
        "routes": isinstance(payload.get("routes"), list)
        and len(payload["routes"]) > 0,
        "customer_schedule": isinstance(payload.get("customer_schedule"), list)
        and len(payload["customer_schedule"]) > 0,
        "route_end_times": isinstance(payload.get("route_end_times"), list)
        and len(payload["route_end_times"]) > 0,
        "baseline_solution": "baseline_solution" in payload,
        "diff": "diff" in payload,
        "objective_delta": has_obj_delta,
        "causal_diagnostics": "causal_diagnostics" in payload,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ScenarioNotFound(KeyError):
    """Raised when an (instance_id, perturbation_id) is not in the registry."""


def get_scenario_row(
    instance_id: str, perturbation_id: str, run_id: str = _DEFAULT_RUN_ID
) -> ScenarioRow:
    scenario_id = f"{instance_id}__{perturbation_id}"
    registry = load_registry(run_id)
    if scenario_id not in registry:
        raise ScenarioNotFound(scenario_id)
    return registry[scenario_id]


def augmented_payload(row: ScenarioRow) -> Optional[dict]:
    """Return the payload_snapshot augmented with display route labels."""
    if not isinstance(row.payload_snapshot, dict):
        return None
    return product_schema.augment_payload_for_product(row.payload_snapshot)


def build_scenario_response(
    instance_id: str, perturbation_id: str, run_id: str = _DEFAULT_RUN_ID
) -> dict:
    row = get_scenario_row(instance_id, perturbation_id, run_id)
    scenario_id = f"{instance_id}__{perturbation_id}"
    payload = augmented_payload(row)

    instance_block = _build_instance_block(instance_id)
    solution_block = _build_solution_block(payload) if payload else None
    available = _available_fields_block(payload)
    if not instance_block:
        available["solution"] = available["solution"] and False

    return {
        "scenario_id": scenario_id,
        "instance_id": instance_id,
        "perturbation_id": perturbation_id,
        "perturbation_summary": _perturbation_summary(
            perturbation_id, row.perturbation_family
        ),
        "instance": instance_block,
        "solution": solution_block,
        "baseline_solution": (payload or {}).get("baseline_solution"),
        "diff": (payload or {}).get("diff"),
        "available_fields": available,
    }


def build_diff_response(
    instance_id: str, perturbation_id: str, run_id: str = _DEFAULT_RUN_ID
) -> Optional[dict]:
    """Return a diff object if the payload exposes baseline/diff, else None.

    We only format fields the payload already contains; we never infer
    customer movement or route deltas ourselves.
    """
    row = get_scenario_row(instance_id, perturbation_id, run_id)
    payload = augmented_payload(row)
    if not payload:
        return None
    has_baseline = "baseline_solution" in payload
    has_diff = "diff" in payload
    if not (has_baseline or has_diff):
        return None
    diff_block: dict[str, Any] = {
        "scenario_id": f"{instance_id}__{perturbation_id}",
        "objective_delta_absolute": payload.get("objective_delta_absolute"),
        "objective_delta_percent": payload.get("objective_delta_percent"),
        "feasibility_changed": None,
        "customer_changes": [],
        "route_changes": [],
    }
    diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else None
    if diff:
        if "customer_changes" in diff and isinstance(diff["customer_changes"], list):
            diff_block["customer_changes"] = copy.deepcopy(diff["customer_changes"])
        if "route_changes" in diff and isinstance(diff["route_changes"], list):
            diff_block["route_changes"] = copy.deepcopy(diff["route_changes"])
        if "feasibility_changed" in diff:
            diff_block["feasibility_changed"] = bool(diff["feasibility_changed"])
    return diff_block


__all__ = [
    "ScenarioRow",
    "ScenarioNotFound",
    "augmented_payload",
    "build_diff_response",
    "build_scenario_response",
    "get_scenario_row",
    "list_instances",
    "load_registry",
]
