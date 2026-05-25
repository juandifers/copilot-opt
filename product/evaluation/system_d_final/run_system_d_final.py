"""System D-Final evaluation runner.

Evaluates d_final (hybrid_guarded) and optionally llm_only /
llm_fallback across:

  1. Run 2 core 60-case benchmark
  2. Axis 1–3 semantic stress axes
  3. Semantic holdout set (this directory)

Live LLM calls are gated by ``RUN_LIVE_LLM_TESTS=1`` in the
environment. Without that flag the runner short-circuits to d1_rules
(deterministic fallback) and writes a no-op report annotated with
``llm_skipped=True``.

Usage:
    .venv/bin/python -m product.evaluation.system_d_final.run_system_d_final

Output:
    product/evaluation/system_d_final/reports/d_final_core_report.csv
    product/evaluation/system_d_final/reports/d_final_stress_report.csv
    product/evaluation/system_d_final/reports/d_final_semantic_holdout_report.csv
"""
from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).parent
_REPORTS = _HERE / "reports"
_RUN_LIVE = os.environ.get("RUN_LIVE_LLM_TESTS", "").strip() == "1"


def _load_client() -> Optional[Any]:
    if not _RUN_LIVE:
        return None
    from product.evaluation.model_clients.openai_client import load_openai_client
    return load_openai_client()


def _score_row(predicted, gold_intent: str = "") -> dict:
    return {
        "predicted_intent": predicted.predicted_intent,
        "predicted_answerability": predicted.predicted_answerability,
        "predicted_behavior_class": predicted.predicted_behavior_class,
        "intent_correct": int(predicted.predicted_intent == gold_intent) if gold_intent else None,
        "adapter_source": (
            predicted.adapter_metadata.source if predicted.adapter_metadata else "d1"
        ),
        "adapter_accepted": (
            predicted.adapter_metadata.accepted if predicted.adapter_metadata else True
        ),
        "fallback_used": (
            predicted.adapter_metadata.fallback_used if predicted.adapter_metadata else False
        ),
        "fallback_reason": (
            predicted.adapter_metadata.fallback_reason if predicted.adapter_metadata else None
        ),
        "confidence": (
            predicted.adapter_metadata.confidence if predicted.adapter_metadata else None
        ),
        "latency_ms": (
            predicted.adapter_metadata.latency_ms if predicted.adapter_metadata else None
        ),
        "tokens_prompt": (
            predicted.adapter_metadata.tokens_prompt if predicted.adapter_metadata else None
        ),
        "tokens_completion": (
            predicted.adapter_metadata.tokens_completion if predicted.adapter_metadata else None
        ),
        "schema_valid": (
            predicted.adapter_metadata.schema_valid if predicted.adapter_metadata else None
        ),
        "validation_outcome": (
            predicted.adapter_metadata.validation_outcome if predicted.adapter_metadata else None
        ),
        "llm_skipped": not _RUN_LIVE,
    }


# ---------------------------------------------------------------------------
# Run 2 core evaluation
# ---------------------------------------------------------------------------


def run_core(client: Optional[Any], mode: str = "hybrid_guarded") -> list[dict]:
    from product.evaluation.run2_case_loader import benchmark_cases_path, load_run2_cases
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.system_d_final.d_final_system_c import run_system_d_final_on_case

    cases = load_run2_cases(benchmark_cases_path())
    rows: list[dict] = []
    for case in cases:
        mat = materialize_case_payload(case)
        if mat.materialization_status != "materialized":
            continue
        predicted = run_system_d_final_on_case(
            case=case,
            payload=mat.payload,
            generator_record=mat.generator_record,
            client=client,
            mode=mode,
        )
        row = {
            "case_id": case.case_id,
            "family": case.family,
            "expected_intent": case.expected_intent,
            "mode": mode,
        }
        row.update(_score_row(predicted, gold_intent=case.expected_intent))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Semantic holdout evaluation
# ---------------------------------------------------------------------------


def run_semantic_holdout(client: Optional[Any], mode: str = "hybrid_guarded") -> list[dict]:
    from product.evaluation.run2_case_loader import Run2Case
    from product.evaluation.run2_payloads import materialize_case_payload
    from product.evaluation.system_d_final.d_final_system_c import run_system_d_final_on_case

    holdout_path = _HERE / "semantic_holdout_cases.csv"
    with holdout_path.open() as f:
        reader = csv.DictReader(f)
        holdout_cases = list(reader)

    rows: list[dict] = []
    for hc in holdout_cases:
        # Build a synthetic case using the base_case_id's payload
        base_case_id = hc.get("base_case_id", "")
        family = hc.get("family", "OBJ")
        prompt_text = hc.get("prompt_text", "")
        gold_intent = hc.get("gold_intent", "unknown")

        # Synthetic case — use the base case's payload path via loader
        case = Run2Case(
            case_id=hc["case_id"],
            source_prompt_id=base_case_id,
            family=family,
            prompt_text=prompt_text,
            payload_condition="clean",
            payload_mutation_needed="",
            expected_intent=gold_intent,
            expected_answerability="",
            expected_evidence_paths=[],
            expected_missing_fields=[],
            expected_warnings=[],
            expected_next_actions=[],
            expected_behavior_class="",
            implementation_status="holdout",
            difficulty="",
            label_rationale="",
            ambiguity_notes="",
        )

        try:
            mat = materialize_case_payload(case)
            payload = mat.payload if mat.materialization_status == "materialized" else None
            gen_record = mat.generator_record if mat.materialization_status == "materialized" else None
        except Exception:
            payload = None
            gen_record = None

        predicted = run_system_d_final_on_case(
            case=case,
            payload=payload,
            generator_record=gen_record,
            client=client,
            mode=mode,
        )

        row = {
            "case_id": hc["case_id"],
            "split": hc.get("split", "dev"),
            "subtype": hc.get("subtype", ""),
            "family": family,
            "gold_intent": gold_intent,
            "mode": mode,
        }
        row.update(_score_row(predicted, gold_intent=gold_intent))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _REPORTS.mkdir(exist_ok=True)
    client = _load_client()
    mode = "hybrid_guarded"

    print(f"D-Final evaluation — live_llm={_RUN_LIVE}, mode={mode}")

    # Core
    t0 = time.monotonic()
    core_rows = run_core(client, mode)
    print(f"  core: {len(core_rows)} cases in {time.monotonic()-t0:.1f}s")
    _write_csv(_REPORTS / "d_final_core_report.csv", core_rows)

    # Semantic holdout
    t0 = time.monotonic()
    holdout_rows = run_semantic_holdout(client, mode)
    print(f"  semantic holdout: {len(holdout_rows)} cases in {time.monotonic()-t0:.1f}s")
    _write_csv(_REPORTS / "d_final_semantic_holdout_report.csv", holdout_rows)

    # Summary
    _print_summary(core_rows, holdout_rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path}")


def _print_summary(core: list[dict], holdout: list[dict]) -> None:
    def _pct(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return "n/a"
        return f"{sum(v for v in vals if v)/len(vals)*100:.1f}%"

    print("\n=== D-Final summary ===")
    print(f"Core intent accuracy    : {_pct(core, 'intent_correct')}")
    print(f"Holdout intent accuracy : {_pct(holdout, 'intent_correct')}")
    n_fallback = sum(1 for r in core + holdout if r.get("fallback_used"))
    n_total = len(core) + len(holdout)
    print(f"Fallback rate           : {n_fallback}/{n_total}")
    if not _RUN_LIVE:
        print("NOTE: LLM calls skipped (RUN_LIVE_LLM_TESTS not set). All results are D1 fallback.")


if __name__ == "__main__":
    main()
