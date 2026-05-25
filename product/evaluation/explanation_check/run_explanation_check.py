"""Run the explanation_check evaluation harness.

For each row in ``explanation_cases.csv``:
1. Build a synthetic ``/copilot/ask`` request from the prompt.
2. Call the API via fastapi.testclient (no live LLM).
3. Record observed intent, answerability, behavior_class,
   compute_decision.mode, answer_text, and the field-paths cited as
   evidence.

Writes ``reports/explanation_raw.csv``. The scorer in
``score_explanation.py`` consumes that file.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from product.api.app import app


_HERE = Path(__file__).resolve().parent
_CASES_CSV = _HERE / "explanation_cases.csv"
_REPORTS_DIR = _HERE / "reports"
_RAW_CSV = _REPORTS_DIR / "explanation_raw.csv"


_RAW_COLUMNS: list[str] = [
    "case_id",
    "scenario_id",
    "prompt",
    "expected_intent",
    "expected_answerability",
    "expected_behavior_class",
    "expected_compute_mode",
    "must_mention",
    "must_not_mention",
    "required_limitations",
    "observed_intent",
    "observed_answerability",
    "observed_behavior_class",
    "observed_compute_mode",
    "observed_compute_action",
    "answer_text",
    "evidence_paths",
    "warnings",
    "missing_fields",
    "status_code",
    "notes",
]


def _load_cases() -> list[dict[str, str]]:
    with _CASES_CSV.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _ask(client: TestClient, scenario_id: str, prompt: str) -> dict[str, Any]:
    r = client.post(
        "/copilot/ask",
        json={"scenario_id": scenario_id, "prompt": prompt},
    )
    body: dict[str, Any]
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = {}
    body["__status_code"] = r.status_code
    return body


def _record_row(case: dict[str, str], body: dict[str, Any]) -> dict[str, str]:
    cd = body.get("compute_decision") or {}
    evidence = body.get("evidence") or []
    paths = [ev.get("field_path", "") for ev in evidence if isinstance(ev, dict)]
    return {
        "case_id": case["case_id"],
        "scenario_id": case["scenario_id"],
        "prompt": case["prompt"],
        "expected_intent": case["expected_intent"],
        "expected_answerability": case["expected_answerability"],
        "expected_behavior_class": case["expected_behavior_class"],
        "expected_compute_mode": case["expected_compute_mode"],
        "must_mention": case.get("must_mention", ""),
        "must_not_mention": case.get("must_not_mention", ""),
        "required_limitations": case.get("required_limitations", ""),
        "observed_intent": body.get("intent", ""),
        "observed_answerability": (body.get("answerability") or {}).get("status", ""),
        "observed_behavior_class": body.get("behavior_class", ""),
        "observed_compute_mode": cd.get("mode", ""),
        "observed_compute_action": cd.get("recommended_action", ""),
        "answer_text": body.get("answer_text") or "",
        "evidence_paths": "|".join(paths),
        "warnings": "|".join(body.get("warnings") or []),
        "missing_fields": "|".join(
            (body.get("answerability") or {}).get("missing_fields") or []
        ),
        "status_code": str(body.get("__status_code", "")),
        "notes": case.get("notes", ""),
    }


def run() -> Path:
    """Run the harness and return the path to the raw CSV."""
    _REPORTS_DIR.mkdir(exist_ok=True)
    client = TestClient(app)
    cases = _load_cases()
    rows: list[dict[str, str]] = []
    for case in cases:
        body = _ask(client, case["scenario_id"], case["prompt"])
        rows.append(_record_row(case, body))
    with _RAW_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RAW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return _RAW_CSV


if __name__ == "__main__":
    out = run()
    print(json.dumps({"raw_csv": str(out), "n_cases": len(_load_cases())}))
