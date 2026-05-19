"""LLM-driven prompt construction for the LLM-generated half of the
locked 48-prompt set.

For each cell flagged source_planned=llm_generated in
cell_selection.csv, we ask Claude Sonnet 4.6 (via Claude Code headless
with `bare: false` per the same auth pattern as the locked configs) to
emit one operator-style question that asks about the cell's intended
claim family.

This is NOT the locked Haiku generator; it is a prompt-construction
tool. Sonnet is chosen for its tighter adherence to natural operator
phrasing.

Filter pipeline (per spec Prompt 5 step 4):
  (a) Sounds like a real operator (heuristic regex on benchmark-register
      phrases)
  (b) Asks the intended claim family (verified by running the locked
      classifier on the generated prompt)
  (c) Does not include answer leakage (heuristic regex on numeric
      patterns that look like cost / count / clock-time answers)
  (d) Not a near-duplicate of an already-accepted LLM-generated prompt
      in the same family (Levenshtein-style edit distance ratio < 0.85)

Up to 3 attempts per cell. Each retry adds a "Previous attempt failed
for reason X; provide a different phrasing." instruction. After 3
failures the cell falls through to a same-family synthetic template
fallback, logged at llm_prompt_rejections.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'experiment' / 'src'))

from classifier import classify_prompt, FAMILIES, ClassifierError  # noqa: E402

MODEL = "claude-sonnet-4-6"
MODEL_PREFIX = "claude-sonnet-4-6"
LOG_DIR = REPO / "experiment" / "logs" / "prompt_construction"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CLAIM_DESC = {
    "OBJ": "total cost or objective value (absolute or change from baseline)",
    "PLAN_VALIDITY": (
        "whether the plan is feasible given constraints, or which customers cannot be served"
    ),
    "STRUCT": (
        "number of routes, vehicles used, route-to-customer assignment, or visit order on a route"
    ),
    "SCHEDULE": "arrival times, lateness, or time-window adherence",
}

SYSTEM_PROMPT_TEMPLATE = """You are simulating a route-planning operator about to ask one question about a specific routing plan. Write ONE operator-style question that asks about {claim_type}. Use natural operator phrasing — short, direct, no jargon. Do not include the answer in the question. Do not name the claim family. Output only the question.

Context (for grounding only — DO NOT echo specific numbers or values in the question):
- Instance class: {instance_class}
- Perturbation: {perturbation_description}
- Action taken: {action_taken}
- Situation: {situation}

If a prior attempt was rejected, the reason will appear in the user message. Provide a different phrasing in that case."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"prompt": {"type": "string", "minLength": 5}},
    "required": ["prompt"],
}


def perturbation_phrase(pid: str) -> str:
    """Free-text perturbation description, no specific values quoted."""
    from vrp_copilot_bench.vrptw_perturbations.types import (
        PERTURBATION_FAMILY_OF, PERTURBATION_MAGNITUDES,
    )
    fam = PERTURBATION_FAMILY_OF[pid]
    m = PERTURBATION_MAGNITUDES[pid]
    if fam == "TRAVEL_TIME":
        return f"travel times increased by about {round((m - 1) * 100)}%"
    if fam == "SERVICE_TIME":
        return f"service times increased by about {round((m - 1) * 100)}%"
    if fam == "TIME_WINDOW":
        return "customer time windows tightened"
    if fam == "ORDER_CHANGE":
        if pid in ("OC_1", "OC_2"):
            return "one new customer was added to the plan"
        return "several new customers were added to the plan"
    raise ValueError(fam)


def situation_summary(cell: dict) -> str:
    if cell["policy_decision"] == "accept":
        verb = "the cheap action ran"
    else:
        verb = "the planner escalated to a 10-second PyVRP solve"
    if cell["sufficiency_label"] == "sufficient":
        return f"{verb} and the result is close to a fresh full re-solve"
    return f"{verb} and the result is not close to a fresh full re-solve"


def build_system_prompt(cell: dict) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        claim_type=CLAIM_DESC[cell["family"]],
        instance_class=cell["instance_class"],
        perturbation_description=perturbation_phrase(cell["perturbation_id"]),
        action_taken=cell["action_taken"],
        situation=situation_summary(cell),
    )


def call_sonnet(cell: dict, retry_reason: str | None, log_path: Path) -> tuple[str, dict]:
    """One Sonnet headless call. Returns (prompt_text, raw_payload)."""
    binary = shutil.which("claude")
    if not binary:
        raise RuntimeError("`claude` CLI not on PATH")

    system_prompt = build_system_prompt(cell)
    user_message = "Write the question now."
    if retry_reason:
        user_message = (
            f"The previous attempt was rejected because: {retry_reason}. "
            f"Provide a different phrasing that avoids that failure mode. "
            f"Write the question now."
        )

    # Write system prompt to temp file so we can use --system-prompt-file.
    sp_tmp = LOG_DIR / f"_sp_{cell['cell_id']}_{int(time.time()*1000)}.txt"
    sp_tmp.write_text(system_prompt)

    try:
        cmd = [
            binary, "-p", "--model", MODEL,
            "--system-prompt-file", str(sp_tmp),
            "--output-format", "json",
            "--json-schema", json.dumps(OUTPUT_SCHEMA),
            "--allowedTools", "",
        ]
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, input=user_message, capture_output=True, text=True, timeout=180)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
    finally:
        sp_tmp.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(f"sonnet headless rc={proc.returncode}: {proc.stderr[:300]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"failed to parse JSON: {e}; head: {proc.stdout[:200]!r}")
    if payload.get("is_error"):
        raise RuntimeError(f"sonnet is_error=true: {payload.get('result')!r}")

    served = {k: v for k, v in payload.get("modelUsage", {}).items() if k.startswith(MODEL_PREFIX)}
    if not served:
        raise RuntimeError(f"served model not {MODEL_PREFIX}*: modelUsage keys = {list(payload.get('modelUsage', {}).keys())}")

    structured = payload.get("structured_output") or {}
    prompt_text = structured.get("prompt", "")
    if not prompt_text:
        result_str = payload.get("result", "")
        try:
            parsed = json.loads(result_str) if result_str else {}
            prompt_text = parsed.get("prompt", "")
        except json.JSONDecodeError:
            pass
    if not prompt_text:
        raise RuntimeError(f"no prompt field in response: structured={structured!r} result={payload.get('result')!r}")

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cell_id": cell["cell_id"],
        "family": cell["family"],
        "retry_reason": retry_reason,
        "prompt_text": prompt_text,
        "model_served": next(iter(served.keys())),
        "wallclock_ms": elapsed_ms,
        "session_id": payload.get("session_id"),
        "raw_response": payload,
    }
    with log_path.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return prompt_text.strip(), payload


# ---- filters ---------------------------------------------------------------

BENCHMARK_REGISTER_PATTERNS = [
    r"\baccording to the data\b",
    r"\bthe instance has\b",
    r"\bgiven the (input|data|solution)\b",
    r"\bthe test case\b",
    r"\bbenchmark\b",
    r"\bevaluate the\b",
    r"\bcompute\b",
]

ANSWER_LEAKAGE_PATTERNS = [
    # currency-like patterns: $123, 123 dollars, etc.
    r"\$\s*\d+",
    r"\b\d+\s*(?:dollars?|usd|eur)\b",
    # specific counts: "11 routes", "8 trucks" — but only if 2+ digits or if the digit is followed by a count noun
    r"\b\d{2,}\s*(?:routes?|trucks?|vehicles?|cars?|drivers?|customers?|stops?|minutes?|hours?)\b",
    # clock-times: 9am, 12:30, 3:45pm
    r"\b\d{1,2}\s*(?:am|pm)\b",
    r"\b\d{1,2}:\d{2}\b",
    # decimal numbers (likely answer values): 1023.5, 0.92
    r"\b\d+\.\d+\b",
]


def filter_operator_register(text: str) -> str | None:
    for pat in BENCHMARK_REGISTER_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return f"benchmark register phrase matched: {pat}"
    return None


def filter_answer_leakage(text: str) -> str | None:
    for pat in ANSWER_LEAKAGE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return f"answer-leakage pattern matched ({pat}): {m.group(0)!r}"
    return None


def filter_family_alignment(text: str, intended_family: str) -> str | None:
    """Run the locked classifier on the generated prompt; reject if
    family doesn't match."""
    try:
        result = classify_prompt(text)
    except ClassifierError as exc:
        return f"classifier halted: {exc}"
    if result.family != intended_family:
        return f"classifier says {result.family}, intended {intended_family}"
    return None


def filter_duplicate(text: str, accepted_in_family: list[str], threshold: float = 0.85) -> str | None:
    norm = re.sub(r"\W+", " ", text.lower()).strip()
    for prev in accepted_in_family:
        prev_norm = re.sub(r"\W+", " ", prev.lower()).strip()
        ratio = SequenceMatcher(None, norm, prev_norm).ratio()
        if ratio >= threshold:
            return f"near-duplicate of accepted prompt ({ratio:.2f} ratio): {prev!r}"
    return None


def filter_all(text: str, intended_family: str, accepted_in_family: list[str]) -> list[tuple[str, str]]:
    """Return list of (filter_code, reason) for every failure."""
    failures = []
    r = filter_operator_register(text)
    if r: failures.append(("a", r))
    r = filter_family_alignment(text, intended_family)
    if r: failures.append(("b", r))
    r = filter_answer_leakage(text)
    if r: failures.append(("c", r))
    r = filter_duplicate(text, accepted_in_family)
    if r: failures.append(("d", r))
    return failures


# ---- driver ---------------------------------------------------------------

def main():
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_path = LOG_DIR / f"prompt_construction_{ts}.jsonl"

    cs = list(csv.DictReader((REPO / 'experiment' / 'data' / 'cell_selection.csv').open()))
    cells = [r for r in cs if r["source_planned"] == "llm_generated"]
    print(f"Loaded {len(cells)} llm_generated cells; logging to {log_path.relative_to(REPO)}")

    accepted = []  # list of {prompt_id, family, cell_id, prompt_text, attempts}
    rejections = []  # list of {prompt_id, family, cell_id, attempt, reason_code, reason_text, prompt_text}

    for cell in cells:
        prompt_id = int(cell["prompt_id"])
        family = cell["family"]
        family_accepted_texts = [a["prompt_text"] for a in accepted if a["family"] == family]
        print(f"\n--- prompt {prompt_id:03d} {family} {cell['cell_id']} ---")
        attempt = 0
        retry_reason = None
        prompt_text = None
        last_failures = None
        while attempt < 3:
            attempt += 1
            print(f"  attempt {attempt}", end=" ", flush=True)
            try:
                prompt_text, _ = call_sonnet(cell, retry_reason, log_path)
            except Exception as e:
                print(f"ERR {e}")
                rejections.append({
                    "prompt_id": prompt_id, "family": family, "cell_id": cell["cell_id"],
                    "attempt": attempt, "reason_code": "x",
                    "reason_text": f"call failed: {e}", "prompt_text": "",
                })
                retry_reason = f"call error ({e})"
                continue
            print(f"-> {prompt_text!r}")
            failures = filter_all(prompt_text, family, family_accepted_texts)
            last_failures = failures
            if not failures:
                print(f"  ACCEPT")
                accepted.append({
                    "prompt_id": prompt_id, "family": family, "cell_id": cell["cell_id"],
                    "prompt_text": prompt_text, "attempts": attempt,
                })
                break
            print(f"  REJECT: {failures}")
            for code, reason in failures:
                rejections.append({
                    "prompt_id": prompt_id, "family": family, "cell_id": cell["cell_id"],
                    "attempt": attempt, "reason_code": code,
                    "reason_text": reason, "prompt_text": prompt_text,
                })
            retry_reason = "; ".join(reason for _, reason in failures)
        else:
            # 3 attempts failed; keep the last prompt anyway and flag for manual review.
            print(f"  FALLTHROUGH after 3 attempts; keeping last prompt with manual_review flag")
            accepted.append({
                "prompt_id": prompt_id, "family": family, "cell_id": cell["cell_id"],
                "prompt_text": prompt_text or "(generation failed)", "attempts": 3,
                "manual_review_required": True,
                "last_failures": last_failures,
            })

    out_csv = REPO / "experiment" / "data" / "_llm_generated_draft.csv"
    with out_csv.open("w") as fh:
        w = csv.writer(fh)
        w.writerow(["prompt_id", "family", "cell_id", "prompt_text", "attempts", "manual_review_required"])
        for a in accepted:
            w.writerow([
                a["prompt_id"], a["family"], a["cell_id"], a["prompt_text"], a["attempts"],
                str(a.get("manual_review_required", False)),
            ])
    print(f"\nAccepted: {len(accepted)}; rejection events: {len(rejections)}")
    print(f"Wrote {out_csv.relative_to(REPO)}")

    rej_md = REPO / "experiment" / "data" / "llm_prompt_rejections.md"
    md = ["# LLM-generated prompt rejections\n"]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    md.append(f"Log: `{log_path.relative_to(REPO)}`\n")
    md.append(f"\n## Summary\n")
    md.append(f"- Total rejection events: {len(rejections)}")
    md.append(f"- Accepted prompts: {len(accepted)}")
    n_review = sum(1 for a in accepted if a.get("manual_review_required"))
    md.append(f"- Prompts kept with manual_review_required: {n_review}")
    if rejections:
        from collections import Counter
        c = Counter(r["reason_code"] for r in rejections)
        md.append(f"- Rejection counts by code: {dict(c)}")
    md.append(f"\n## Rejection events (chronological)\n")
    if not rejections:
        md.append("None.")
    else:
        md.append("| prompt_id | family | cell_id | attempt | code | reason | rejected_text |")
        md.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in rejections:
            txt = r["prompt_text"].replace("|", "\\|")[:200]
            reason = r["reason_text"].replace("|", "\\|")[:200]
            md.append(f"| {r['prompt_id']:03d} | {r['family']} | {r['cell_id']} | {r['attempt']} | {r['reason_code']} | {reason} | {txt} |")
    md.append("")
    if n_review:
        md.append(f"## Manual-review-required prompts\n")
        for a in accepted:
            if a.get("manual_review_required"):
                md.append(f"- {a['prompt_id']:03d} {a['family']} {a['cell_id']}: {a['prompt_text']!r}")
                md.append(f"  last_failures: {a['last_failures']}")
    rej_md.write_text("\n".join(md))
    print(f"Wrote {rej_md.relative_to(REPO)}")


if __name__ == "__main__":
    main()
