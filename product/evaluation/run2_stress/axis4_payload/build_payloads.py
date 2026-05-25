"""Build SCHEDULE payloads for every unsampled Homberger-200 cell.

Reads the pyvrp_10s checkpoint JSON files at
``data/homberger_probe_checkpoints/pyvrp10s/{cell_id}.json`` and projects
them into the canonical SCHEDULE payload shape from
``experiment/src/payload_projector.py`` (the same shape Run 1 emitted).

Output: one ``{cell_id}.json`` per cell under
``product/evaluation/run2_stress/axis4_payload/payloads/`` plus a
``manifest.json`` indexing every cell with n_routes and n_customers.
"""
from __future__ import annotations

import json
from pathlib import Path

SCALING = 10  # PyVRP ×10 integer units → solomon_minutes


def _project_schedule_from_checkpoint(j: dict) -> dict:
    """Mirror experiment/src/payload_projector.py:_project_schedule."""
    pcs = j["per_customer_schedule"]
    customers = sorted((int(k), v) for k, v in pcs.items())
    late_ids = sorted(cid for cid, v in customers if int(v["time_warp"]) > 0)

    route_end_times = []
    for rs in j["route_summaries"]:
        if rs["n_customers"] == 0:
            continue
        route_end_times.append({
            "route_idx": int(rs["route_idx"]),
            "end_time": round(float(rs["end_time"]) / SCALING, 1),
            "has_time_warp": bool(rs["has_time_warp"]),
        })

    customer_schedule = []
    for cid, v in customers:
        customer_schedule.append({
            "customer_id": cid,
            "route_idx": int(v["route_idx"]),
            "arrival": round(float(v["arrival"]) / SCALING, 1),
            "start_service": round(float(v["start_service"]) / SCALING, 1),
            "end_service": round(float(v["end_service"]) / SCALING, 1),
            "tw_early": round(float(v["tw_early"]) / SCALING, 1),
            "tw_late": round(float(v["tw_late"]) / SCALING, 1),
            "is_late": bool(int(v["time_warp"]) > 0),
            "lateness_minutes": round(float(v["time_warp"]) / SCALING, 1),
        })

    return {
        "units": {"time": "solomon_minutes"},
        "n_late_customers": len(late_ids),
        "late_customer_ids": late_ids,
        "route_end_times": route_end_times,
        "customer_schedule": customer_schedule,
    }


RUN1_CELLS = {
    "C2_2_2__TW_5", "C1_2_2__TT_5", "C1_2_1__TT_5", "C2_2_1__TW_6",
    "RC1_2_1__TW_5", "C1_2_1__ST_3", "C1_2_2__TW_5", "R2_2_1__OC_5",
    "RC1_2_2__TT_5", "RC2_2_1__OC_5", "C2_2_2__ST_3", "RC1_2_1__ST_4",
}


def main() -> None:
    repo = Path(__file__).resolve().parents[4]
    ckpt_dir = repo / "data" / "homberger_probe_checkpoints" / "pyvrp10s"
    out_dir = Path(__file__).resolve().parent / "payloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for f in sorted(ckpt_dir.glob("*.json")):
        cell_id = f.stem
        if cell_id in RUN1_CELLS:
            continue
        with f.open() as fh:
            j = json.load(fh)
        payload = _project_schedule_from_checkpoint(j)
        with (out_dir / f"{cell_id}.json").open("w") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        manifest.append({
            "cell_id": cell_id,
            "instance": cell_id.split("__")[0],
            "pid": cell_id.split("__")[1],
            "n_routes": j["n_routes"],
            "n_customers": len(payload["customer_schedule"]),
            "feasible": j["feasible"],
            "n_late_customers": payload["n_late_customers"],
        })

    with (out_dir / "manifest.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"wrote {len(manifest)} payloads to {out_dir}")


if __name__ == "__main__":
    main()
