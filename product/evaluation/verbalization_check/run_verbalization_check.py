"""Verbalization faithfulness check runner.

For each case in verbalization_cases.csv:
  1. Run D-Final on the scenario (client=None → D1 deterministic fallback)
  2. Build evidence items from the contract output
  3. Call verbalization.verbalize() to produce answer_text
  4. Score answer_text using score_verbalization.score_case()
  5. Write results to reports/

Usage:
    .venv/bin/python -m product.evaluation.verbalization_check.run_verbalization_check
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).parent
_CASES_CSV = _HERE / "verbalization_cases.csv"
_REPORTS = _HERE / "reports"

# ---------------------------------------------------------------------------
# Case loader
# ---------------------------------------------------------------------------


def load_cases() -> list[dict]:
    with _CASES_CSV.open() as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Scenario → contract
# ---------------------------------------------------------------------------


def _get_payload_from_source(source: str, scenario_id: str) -> Optional[dict]:
    """Resolve payload from source type."""
    if source.startswith("R2-"):
        # Materialized Run2 case
        from product.evaluation.run2_case_loader import default_cases_path, load_run2_cases
        from product.evaluation.run2_payloads import materialize_case_payload
        cases = load_run2_cases(default_cases_path())
        case = next((c for c in cases if c.case_id == source), None)
        if case is None:
            return None
        mat = materialize_case_payload(case)
        return mat.payload if mat.materialization_status == "materialized" else None
    elif source == "api":
        # API scenario
        if "__" not in scenario_id:
            return None
        iid, pert = scenario_id.split("__", 1)
        from product.api.scenario_store import augmented_payload, get_scenario_row
        try:
            row = get_scenario_row(iid, pert)
            return augmented_payload(row)
        except Exception:
            return None
    return None


def _run_contract(prompt: str, family: str, source: str, scenario_id: str) -> tuple[Any, Optional[dict]]:
    """Run D-Final contract on a verbalization case. Returns (predicted, payload)."""
    from product.evaluation.run2_case_loader import Run2Case
    from product.evaluation.system_d_final.d_final_system_c import run_system_d_final_on_case

    payload = _get_payload_from_source(source, scenario_id)

    case = Run2Case(
        case_id=f"vb::{scenario_id}",
        source_prompt_id=source if source.startswith("R2-") else "",
        family=family,
        prompt_text=prompt,
        payload_condition="clean",
        payload_mutation_needed="",
        expected_intent="",
        expected_answerability="",
        expected_evidence_paths=[],
        expected_missing_fields=[],
        expected_warnings=[],
        expected_next_actions=[],
        expected_behavior_class="",
        implementation_status="verbalization_check",
        difficulty="",
        label_rationale="",
        ambiguity_notes="",
    )

    predicted = run_system_d_final_on_case(case=case, payload=payload, client=None)
    return predicted, payload


def _build_evidence_items(intent: str, payload: Optional[dict], prompt: str) -> list[dict]:
    from product.data import evidence as evidence_mod, product_schema
    if payload is None:
        return []
    augmented = product_schema.augment_payload_for_product(payload)
    items = evidence_mod.build_evidence_items(
        intent=intent, payload=augmented, generator_record=None,
        row={"prompt_text": prompt}
    )
    return [{"field_path": it.field_path, "value": it.value} for it in items]


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run() -> list[dict]:
    from product.copilot.verbalization import verbalize
    from product.evaluation.verbalization_check.score_verbalization import score_case

    _REPORTS.mkdir(exist_ok=True)
    cases = load_cases()
    results = []

    for case in cases:
        cid = case["case_id"]
        source = case["source"]
        scenario_id = case["scenario_id"]
        family = case["family"]
        prompt = case["prompt"]

        try:
            predicted, payload = _run_contract(prompt, family, source, scenario_id)
            evidence_items = _build_evidence_items(predicted.predicted_intent, payload, prompt)

            cd = predicted.compute_decision
            cd_dict = cd.model_dump() if cd is not None else None

            answer_text = verbalize(
                intent=predicted.predicted_intent,
                answerability=predicted.predicted_answerability,
                behavior_class=predicted.predicted_behavior_class,
                evidence_items=evidence_items,
                warnings=list(predicted.predicted_warnings),
                missing_fields=list(predicted.predicted_missing_fields),
                next_actions=list(predicted.predicted_next_actions),
                prompt_text=prompt,
                compute_decision=cd_dict,
            )

            scores = score_case(
                answer_text=answer_text,
                behavior_class=predicted.predicted_behavior_class,
                warnings=list(predicted.predicted_warnings),
                missing_fields=list(predicted.predicted_missing_fields),
                compute_decision_mode=cd_dict.get("mode") if cd_dict else None,
                expected_key_facts=case.get("expected_key_facts", ""),
                expected_must_mention=case.get("expected_must_mention", ""),
                expected_must_not_mention=case.get("expected_must_not_mention", ""),
                expected_warning_mentions=case.get("expected_warning_mentions", ""),
                expected_missing_field_mentions=case.get("expected_missing_field_mentions", ""),
                expected_compute_decision_mentions=case.get("expected_compute_decision_mentions", ""),
                evidence_paths=[ev["field_path"] for ev in evidence_items],
            )

            row = {
                "case_id": cid,
                "source": source,
                "scenario_id": scenario_id,
                "prompt": prompt,
                "behavior_class": predicted.predicted_behavior_class,
                "answer_text": answer_text,
                "warnings": json.dumps(list(predicted.predicted_warnings)),
                "missing_fields": json.dumps(list(predicted.predicted_missing_fields)),
                "compute_decision_mode": cd_dict.get("mode") if cd_dict else "",
                "compute_decision_action": cd_dict.get("recommended_action") if cd_dict else "",
                "evidence_paths": json.dumps([ev["field_path"] for ev in evidence_items]),
                "expected_behavior_class": case.get("expected_behavior_class", ""),
                "expected_must_mention": case.get("expected_must_mention", ""),
                "expected_must_not_mention": case.get("expected_must_not_mention", ""),
                **scores,
                "error": "",
            }

        except Exception as exc:
            row = {
                "case_id": cid,
                "source": source,
                "scenario_id": scenario_id,
                "prompt": prompt,
                "behavior_class": "",
                "answer_text": "",
                "warnings": "",
                "missing_fields": "",
                "compute_decision_mode": "",
                "compute_decision_action": "",
                "evidence_paths": "",
                "expected_behavior_class": case.get("expected_behavior_class", ""),
                "expected_must_mention": case.get("expected_must_mention", ""),
                "expected_must_not_mention": case.get("expected_must_not_mention", ""),
                "faithful_to_contract": False,
                "critical_omission": True,
                "unsupported_addition": False,
                "numeric_or_entity_error": False,
                "warning_preserved": False,
                "missing_field_preserved": False,
                "compute_decision_preserved": False,
                "overall_pass": False,
                "failure_reason": f"runner_error: {type(exc).__name__}: {exc}",
                "error": str(exc),
            }

        results.append(row)
        status = "✓" if row["overall_pass"] else "✗"
        print(f"  {cid} [{row.get('behavior_class','?')}] {status} — {row.get('failure_reason','')[:80]}")

    return results


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def write_raw_csv(results: list[dict], path: Path) -> None:
    if not results:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)


def write_summary_csv(metrics: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in metrics.items():
            w.writerow([k, v])


def compute_summary(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {}

    def rate(key: str) -> float:
        return sum(1 for r in results if r.get(key) is True) / n

    def inv_rate(key: str) -> float:
        return sum(1 for r in results if r.get(key) is True) / n

    by_beh: dict[str, dict] = {}
    for r in results:
        beh = r.get("behavior_class") or r.get("expected_behavior_class", "unknown")
        by_beh.setdefault(beh, {"n": 0, "pass": 0})
        by_beh[beh]["n"] += 1
        by_beh[beh]["pass"] += int(r.get("overall_pass") is True)

    return {
        "n_cases": n,
        "overall_pass_rate": rate("overall_pass"),
        "faithful_to_contract_rate": rate("faithful_to_contract"),
        "critical_omission_rate": inv_rate("critical_omission"),
        "unsupported_addition_rate": inv_rate("unsupported_addition"),
        "numeric_or_entity_error_rate": inv_rate("numeric_or_entity_error"),
        "warning_preservation_rate": rate("warning_preserved"),
        "missing_field_preservation_rate": rate("missing_field_preserved"),
        "compute_decision_preservation_rate": rate("compute_decision_preserved"),
        **{
            f"pass_rate_{beh}": v["pass"] / v["n"] if v["n"] else 0.0
            for beh, v in by_beh.items()
        },
    }


def write_summary_md(results: list[dict], metrics: dict, path: Path) -> None:
    n = metrics["n_cases"]
    opr = metrics["overall_pass_rate"]
    fails = [r for r in results if not r.get("overall_pass")]
    by_beh: dict[str, dict] = {}
    for r in results:
        beh = r.get("behavior_class") or r.get("expected_behavior_class", "unknown")
        by_beh.setdefault(beh, {"n": 0, "pass": 0})
        by_beh[beh]["n"] += 1
        by_beh[beh]["pass"] += int(r.get("overall_pass") is True)

    lines = [
        "# Verbalization Faithfulness Check — Summary",
        "",
        "_2026-05-21. Evaluates whether the template-based verbalization renderer_",
        "_faithfully renders the structured D-Final contract into natural language._",
        "",
        "## Scope note",
        "",
        "This evaluation does not replace the Run 2 product-contract benchmark.",
        "The structured contract remains the primary evaluated artifact.",
        "This check only tests whether the natural-language answer text faithfully",
        "renders the already-produced contract object.",
        "",
        "The retired 48 × 2×2 generator/judge experiment is not used because the",
        "thesis no longer evaluates free-form model answer generation as the primary",
        "object. Instead, the product emits a structured contract, and this smaller",
        "check evaluates whether the final text shown to the operator preserves that",
        "contract.",
        "",
        "**Renderer evaluated**: `product/copilot/verbalization.py` (template-based,",
        "deterministic, no LLM calls).",
        "",
        "## Headline results",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Cases | {n} |",
        f"| **Overall pass rate** | **{opr:.1%} ({sum(1 for r in results if r.get('overall_pass'))}/{n})** |",
        f"| Faithful to contract | {metrics['faithful_to_contract_rate']:.1%} |",
        f"| Critical omission rate | {metrics['critical_omission_rate']:.1%} |",
        f"| Unsupported addition rate | {metrics['unsupported_addition_rate']:.1%} |",
        f"| Numeric/entity error rate | {metrics['numeric_or_entity_error_rate']:.1%} |",
        f"| Warning preservation rate | {metrics['warning_preservation_rate']:.1%} |",
        f"| Missing-field preservation rate | {metrics['missing_field_preservation_rate']:.1%} |",
        f"| Compute-decision preservation rate | {metrics['compute_decision_preservation_rate']:.1%} |",
        "",
        "## Results by behavior class",
        "",
        "| Behavior class | n | Pass |",
        "|---|---:|---:|",
    ]
    for beh, v in sorted(by_beh.items()):
        lines.append(f"| `{beh}` | {v['n']} | {v['pass']}/{v['n']} = {v['pass']/v['n']:.1%} |")

    lines += [
        "",
        "## Failures",
        "",
    ]
    if not fails:
        lines.append("No failures — all 24 cases pass.")
    else:
        lines.append(f"{len(fails)} case(s) failed:\n")
        for r in fails:
            lines.append(f"- **{r['case_id']}** [{r.get('behavior_class','?')}]: {r.get('failure_reason','')}")

    lines += [
        "",
        "## Interpretation",
        "",
        "Thresholds (post-hoc, not pre-registered):",
        "- ≥ 90%: verbalization acceptable for thesis demo",
        "- 75–90%: usable with caveats",
        "- < 75%: prototype-only; structured contract remains the evaluated artifact",
        "",
    ]

    path.write_text("\n".join(lines) + "\n")


def write_failures_md(results: list[dict], path: Path) -> None:
    fails = [r for r in results if not r.get("overall_pass")]
    lines = [
        "# Verbalization Failures",
        "",
        f"_{len(fails)} case(s) with overall_pass = False._",
        "",
    ]
    if not fails:
        lines.append("No failures.")
    else:
        for r in fails:
            lines += [
                f"## {r['case_id']} [{r.get('behavior_class','?')}]",
                "",
                f"**Prompt**: {r['prompt']!r}",
                f"**Answer text**: {r.get('answer_text','')!r}",
                f"**Failure reason**: {r.get('failure_reason','')}",
                f"**Warnings**: {r.get('warnings','')}",
                f"**Missing fields**: {r.get('missing_fields','')}",
                f"**Compute mode**: {r.get('compute_decision_mode','')}",
                "",
            ]
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("Running verbalization check...")
    results = run()
    metrics = compute_summary(results)

    raw_path = _REPORTS / "verbalization_raw.csv"
    write_raw_csv(results, raw_path)
    print(f"\nWrote {raw_path}")

    write_summary_csv(metrics, _REPORTS / "verbalization_summary.csv")
    write_summary_md(results, metrics, _REPORTS / "verbalization_summary.md")
    write_failures_md(results, _REPORTS / "verbalization_failures.md")

    for p in ("verbalization_summary.csv", "verbalization_summary.md", "verbalization_failures.md"):
        print(f"Wrote {_REPORTS / p}")

    n = metrics["n_cases"]
    opr = metrics["overall_pass_rate"]
    print(f"\n=== Verbalization check ===")
    print(f"  overall_pass_rate : {opr:.1%} ({round(opr*n)}/{n})")
    print(f"  faithful          : {metrics['faithful_to_contract_rate']:.1%}")
    print(f"  critical_omission : {metrics['critical_omission_rate']:.1%}")
    print(f"  unsupported_add   : {metrics['unsupported_addition_rate']:.1%}")
    print(f"  numeric_error     : {metrics['numeric_or_entity_error_rate']:.1%}")
    print(f"  warning_pres      : {metrics['warning_preservation_rate']:.1%}")
    print(f"  missing_pres      : {metrics['missing_field_preservation_rate']:.1%}")
    print(f"  compute_pres      : {metrics['compute_decision_preservation_rate']:.1%}")


if __name__ == "__main__":
    main()
