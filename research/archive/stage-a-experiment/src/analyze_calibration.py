"""Step 4 — calibration analysis.

Reads the filled human-rating sheet and writes the analysis writeup at
experiment/pilot/calibration_analysis.md. Implements the six sections
from the run brief and pilot_protocol.md:

(a) Cohen's quadratic-weighted kappa on faithfulness (with bootstrap 95% CI).
(b) Faithfulness disagreement breakdown (|diff|>=2 in detail; |diff|=1 summarised).
(c) Op-validity binary agreement (among gradable prompts).
(d) Refusal-handling agreement.
(e) Per-family/source/quadrant disagreement pattern.
(f) 3 vs 4 boundary confusion (the pre-registered weak point).

This script does NOT propose rubric edits. On kappa < 0.7 it
surfaces descriptive patterns and candidate ambiguities; design
decisions remain with the candidate.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score

REPO = Path(__file__).resolve().parents[2]


def _parse_int(s: str | None):
    if s is None or s == "":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_bool(s: str | None):
    if s is None:
        return None
    s_l = str(s).strip().lower()
    if s_l in ("true", "t", "yes", "y", "1", "pass"):
        return True
    if s_l in ("false", "f", "no", "n", "0", "fail"):
        return False
    if s_l in ("", "null", "none", "n/a", "na"):
        return None
    return None


def load_sheet(path: Path) -> list[dict]:
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError(f"empty sheet: {path}")
    return rows


def bootstrap_kappa_ci(y_judge, y_human, n_iter=2000, alpha=0.05, seed=2026):
    rng = np.random.default_rng(seed)
    n = len(y_judge)
    values = []
    j = np.array(y_judge)
    h = np.array(y_human)
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        try:
            k = cohen_kappa_score(j[idx], h[idx], weights="quadratic")
            if not np.isnan(k):
                values.append(k)
        except ValueError:
            continue
    if not values:
        return (float("nan"), float("nan"))
    lo, hi = np.quantile(values, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def section_a(judge_scores, human_scores) -> dict:
    """Return kappa + CI + degeneracy diagnostic.

    Quadratic-weighted Cohen's kappa is undefined when one rater is
    constant (zero variance). sklearn returns 0 (with a divide-by-zero
    warning); that 0 means 'kappa not computable', not 'no agreement'.
    Detect and report the constant-rater case explicitly so the verdict
    can be interpreted correctly.
    """
    j_unique = sorted(set(judge_scores))
    h_unique = sorted(set(human_scores))
    judge_constant = len(j_unique) == 1
    human_constant = len(h_unique) == 1
    raw_agreement = sum(
        1 for j, h in zip(judge_scores, human_scores) if j == h
    ) / len(judge_scores) if judge_scores else float("nan")
    if judge_constant or human_constant:
        kappa = float("nan")
        ci = (float("nan"), float("nan"))
    else:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            kappa = float(
                cohen_kappa_score(judge_scores, human_scores, weights="quadratic")
            )
        ci = bootstrap_kappa_ci(judge_scores, human_scores)
    return {
        "kappa": kappa,
        "ci": ci,
        "judge_constant": judge_constant,
        "human_constant": human_constant,
        "judge_score_set": j_unique,
        "human_score_set": h_unique,
        "raw_agreement": raw_agreement,
    }


def section_b_disagreements(rows: list[dict]) -> dict:
    big = []
    one = []
    same = 0
    for r in rows:
        j = _parse_int(r["judge_faithfulness_score"])
        h = _parse_int(r["human_faithfulness_score"])
        if j is None or h is None:
            continue
        d = abs(j - h)
        if d == 0:
            same += 1
        elif d == 1:
            one.append((r, j, h))
        else:
            big.append((r, j, h))
    return {"big": big, "one": one, "same": same}


def section_c_op_validity(rows: list[dict]) -> dict:
    """Binary agreement on op_validity_pass among gradable prompts."""
    n_gradable = 0
    n_agree = 0
    disagreements = []
    for r in rows:
        if str(r.get("op_validity_gradable", "")).strip().lower() != "true":
            continue
        n_gradable += 1
        j = _parse_bool(r["judge_op_validity_pass"])
        h = _parse_bool(r["human_op_validity_pass"])
        if j is None or h is None:
            # missing human op-validity rating on a gradable prompt — flag separately
            disagreements.append((r, j, h, "human op-validity missing"))
            continue
        if j == h:
            n_agree += 1
        else:
            disagreements.append((r, j, h, "value mismatch"))
    return {
        "n_gradable": n_gradable,
        "n_agree": n_agree,
        "agreement_rate": (n_agree / n_gradable) if n_gradable else float("nan"),
        "disagreements": disagreements,
    }


def section_d_refusal(rows: list[dict]) -> dict:
    disagreements = []
    n_compared = 0
    n_agree = 0
    for r in rows:
        j = _parse_bool(r["judge_refusal_detected"])
        h_raw = (r["human_refusal_assessment"] or "").strip()
        if not h_raw:
            continue
        h = _parse_bool(h_raw)
        if h is None:
            disagreements.append((r, j, h_raw, "human refusal assessment unparseable"))
            continue
        n_compared += 1
        if j == h:
            n_agree += 1
        else:
            disagreements.append((r, j, h, "value mismatch"))
    return {
        "n_compared": n_compared,
        "n_agree": n_agree,
        "agreement_rate": (n_agree / n_compared) if n_compared else float("nan"),
        "disagreements": disagreements,
    }


def section_e_per_axis(rows: list[dict]) -> dict:
    axes = {"family": Counter(), "source": Counter(), "quadrant": Counter()}
    totals = {"family": Counter(), "source": Counter(), "quadrant": Counter()}
    for r in rows:
        j = _parse_int(r["judge_faithfulness_score"])
        h = _parse_int(r["human_faithfulness_score"])
        if j is None or h is None:
            continue
        d = abs(j - h)
        for axis in axes:
            totals[axis][r[axis]] += 1
            if d != 0:
                axes[axis][r[axis]] += d  # weight by magnitude of disagreement
    breakdown = {}
    for axis, t in totals.items():
        breakdown[axis] = {
            k: {
                "n": t[k],
                "total_disagreement_score": axes[axis][k],
                "mean_abs_diff": axes[axis][k] / t[k] if t[k] else 0,
            }
            for k in sorted(t)
        }
    return breakdown


def section_f_3_vs_4(rows: list[dict]) -> dict:
    confusion = Counter()
    examples = []
    for r in rows:
        j = _parse_int(r["judge_faithfulness_score"])
        h = _parse_int(r["human_faithfulness_score"])
        if j is None or h is None:
            continue
        confusion[(j, h)] += 1
        if {j, h} == {3, 4}:
            examples.append((r, j, h))
    return {"confusion": dict(confusion), "examples_3_4": examples}


def confusion_matrix_md(confusion: dict) -> str:
    vals = sorted({k for jh in confusion for k in jh})
    if not vals:
        return "(no data)"
    header = "| judge\\human | " + " | ".join(str(v) for v in vals) + " |"
    sep = "|---" * (len(vals) + 1) + "|"
    lines = [header, sep]
    for j in vals:
        row = [f"**{j}**"]
        for h in vals:
            row.append(str(confusion.get((j, h), 0)))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_report(sheet_path: Path, out_path: Path) -> str:
    rows = load_sheet(sheet_path)
    judge_scores = []
    human_scores = []
    missing_human = []
    for r in rows:
        j = _parse_int(r["judge_faithfulness_score"])
        h = _parse_int(r["human_faithfulness_score"])
        if h is None:
            missing_human.append(r["prompt_id"])
            continue
        if j is None:
            continue
        judge_scores.append(j)
        human_scores.append(h)
    if missing_human:
        print(
            f"WARN: {len(missing_human)} prompts missing human_faithfulness_score: "
            f"{missing_human}",
            file=sys.stderr,
        )

    sec_a = section_a(judge_scores, human_scores)
    kappa = sec_a["kappa"]
    ci = sec_a["ci"]
    b = section_b_disagreements(rows)
    c = section_c_op_validity(rows)
    d = section_d_refusal(rows)
    e = section_e_per_axis(rows)
    f = section_f_3_vs_4(rows)

    out: list[str] = []
    out.append("# Calibration pilot analysis (calibration-pilot-v1)")
    out.append("")
    out.append(
        f"- Prompts rated: {len(judge_scores)} / {len(rows)} "
        f"(human missing on {len(missing_human)})"
    )
    out.append("")
    out.append("## (a) Cohen's quadratic-weighted kappa")
    out.append("")
    if sec_a["judge_constant"] or sec_a["human_constant"]:
        constant_side = []
        if sec_a["judge_constant"]:
            constant_side.append(
                f"judge constant at {sec_a['judge_score_set'][0]}"
            )
        if sec_a["human_constant"]:
            constant_side.append(
                f"human constant at {sec_a['human_score_set'][0]}"
            )
        out.append(
            "- **kappa: undefined (degenerate)** — "
            + "; ".join(constant_side)
            + ". With one rater's variance = 0, the kappa formula evaluates "
            "0/0; sklearn returns 0 with a warning. The substantive read is "
            "'one rater has no discrimination at this scale', not "
            "'raters disagree by chance'."
        )
        out.append(
            f"- Observed raw agreement: {sec_a['raw_agreement']:.2%} "
            f"({sum(1 for j, h in zip(judge_scores, human_scores) if j == h)} "
            f"of {len(judge_scores)}) — note this is the chance-expected "
            f"rate when one rater is constant, so it does **not** constitute "
            f"evidence of inter-rater agreement."
        )
        out.append(
            "- Pre-registered gate: kappa ≥ 0.70 ⇒ **FAIL (gate not "
            "satisfiable while one rater is constant)** — rubric/judge "
            "revision required before kappa is meaningful."
        )
    else:
        out.append(f"- **kappa = {kappa:.3f}** (quadratic weights, faithfulness 1–5)")
        out.append(
            f"- Bootstrap 95% CI (n=2000, seed=2026): "
            f"[{ci[0]:.3f}, {ci[1]:.3f}]"
        )
        out.append(f"- Observed raw agreement: {sec_a['raw_agreement']:.2%}")
        out.append(
            f"- Pre-registered gate: kappa ≥ 0.70 "
            f"⇒ {'PASS' if kappa >= 0.70 else 'FAIL — rubric revision required'}"
        )
    out.append("")
    out.append("### Confusion matrix (judge × human, faithfulness 1–5)")
    out.append("")
    out.append(confusion_matrix_md(f["confusion"]))
    out.append("")
    out.append("## (b) Faithfulness disagreement breakdown")
    out.append("")
    out.append(f"- Exact agreement: {b['same']} / {len(judge_scores)}")
    out.append(f"- |diff|=1: {len(b['one'])} prompts (one-line summary below)")
    out.append(f"- |diff|≥2: {len(b['big'])} prompts (full rationales below)")
    out.append("")
    if b["big"]:
        out.append("### |diff|≥2 cases")
        out.append("")
        for (r, j, h) in b["big"]:
            out.append(
                f"#### Prompt {r['prompt_id']} ({r['family']}/{r['source']}/"
                f"{r['quadrant']}) — judge={j} human={h}"
            )
            out.append("")
            out.append("- **Judge rationale**:")
            out.append(f"  > {(r['judge_rationale'] or '').strip()}")
            out.append("- **Human rationale**:")
            out.append(f"  > {(r['human_rationale'] or '').strip()}")
            out.append("")
    if b["one"]:
        out.append("### |diff|=1 cases (summary)")
        out.append("")
        for (r, j, h) in b["one"]:
            out.append(
                f"- Prompt {r['prompt_id']} ({r['family']}/{r['source']}/"
                f"{r['quadrant']}): judge={j} human={h} — "
                f"{(r['human_notes'] or '').strip()[:120]}"
            )
        out.append("")
    out.append("## (c) Op-validity binary agreement (gradable only)")
    out.append("")
    out.append(
        f"- Agreement: {c['n_agree']} / {c['n_gradable']} "
        f"= {c['agreement_rate']:.2%}" if c["n_gradable"] else "- (no gradable prompts)"
    )
    if c["disagreements"]:
        out.append("")
        out.append("### Op-validity disagreements")
        out.append("")
        for (r, j, h, reason) in c["disagreements"]:
            out.append(
                f"- Prompt {r['prompt_id']} ({r['family']}): "
                f"judge={j} human={h} — {reason}"
            )
            out.append(f"  - Judge rationale: {(r['judge_rationale'] or '').strip()[:200]}")
            out.append(f"  - Human notes: {(r['human_notes'] or '').strip()[:200]}")
    out.append("")
    out.append("## (d) Refusal-handling agreement")
    out.append("")
    if d["n_compared"]:
        out.append(
            f"- Compared on {d['n_compared']} prompts where human_refusal_assessment "
            f"was set; agreement {d['n_agree']}/{d['n_compared']} = "
            f"{d['agreement_rate']:.2%}"
        )
    else:
        out.append("- No prompts had human_refusal_assessment filled.")
    for (r, j, h_raw, reason) in d["disagreements"]:
        out.append(
            f"- Prompt {r['prompt_id']}: judge={j} human={h_raw} — {reason}"
        )
    out.append("")
    out.append("## (e) Per-axis disagreement pattern")
    out.append("")
    for axis, table in e.items():
        out.append(f"### By {axis}")
        out.append("")
        out.append(f"| {axis} | n | total |diff| | mean |diff| |")
        out.append("|---|---|---|---|")
        for k, v in table.items():
            out.append(
                f"| {k} | {v['n']} | {v['total_disagreement_score']} | "
                f"{v['mean_abs_diff']:.2f} |"
            )
        out.append("")
    out.append("## (f) 3-vs-4 boundary (pre-registered weak point)")
    out.append("")
    n34 = (f["confusion"].get((3, 4), 0)
           + f["confusion"].get((4, 3), 0))
    out.append(
        f"- Judge=3 ∧ human=4: {f['confusion'].get((3, 4), 0)} "
        f"· Judge=4 ∧ human=3: {f['confusion'].get((4, 3), 0)} "
        f"· combined: {n34}"
    )
    if f["examples_3_4"]:
        out.append("")
        out.append("### 3↔4 cases (all of them)")
        out.append("")
        for (r, j, h) in f["examples_3_4"]:
            out.append(
                f"#### Prompt {r['prompt_id']} ({r['family']}/{r['source']}) "
                f"— judge={j} human={h}"
            )
            out.append("")
            out.append(f"- Judge rationale: {(r['judge_rationale'] or '').strip()}")
            out.append(f"- Human rationale: {(r['human_rationale'] or '').strip()}")
            out.append("")
    out.append("## (g) Candidate rubric/judge-prompt ambiguities surfaced")
    out.append("")
    out.append(
        "Descriptive only — the rubric/judge-prompt revision is a design "
        "decision belonging to the candidate. The following are observed "
        "points where the disagreements suggest the locked instruments "
        "admit more than one defensible reading. This section is "
        "data-derived: if a category has no observed disagreements it is "
        "omitted."
    )
    out.append("")

    bullet_idx = 0

    # Faithfulness disagreements
    if b["big"] or b["one"]:
        bullet_idx += 1
        n_big = len(b["big"])
        n_one = len(b["one"])
        big_ids = ", ".join(r["prompt_id"] for (r, _, _) in b["big"])
        out.append(
            f"{bullet_idx}. **Faithfulness disagreements** "
            f"(|diff|≥2: {n_big}; |diff|=1: {n_one}). "
            f"Prompts with |diff|≥2: {big_ids or '(none)'}. "
            f"The judge's and human's rationales above (section (b)) "
            f"name the specific axis of disagreement on each prompt; "
            f"shared patterns there indicate where rubric.md (a) admits "
            f"more than one defensible read."
        )
        out.append("")

    # Op-validity disagreements
    op_disagreements = [
        d for d in c["disagreements"]
        if d[3] == "value mismatch"
    ]
    if op_disagreements:
        bullet_idx += 1
        families_affected = sorted({d[0]["family"] for d in op_disagreements})
        ids = ", ".join(d[0]["prompt_id"] for d in op_disagreements)
        out.append(
            f"{bullet_idx}. **Op-validity binary disagreements** "
            f"({len(op_disagreements)} of {c['n_gradable']} gradable; "
            f"families: {families_affected}; prompts: {ids}). "
            f"The runner's op_validity.py applies the rubric §b "
            f"thresholds programmatically; where the judge disagrees, "
            f"the rubric's exact set-semantics for that family's "
            f"membership/equality check is the likely ambiguity. The "
            f"human_notes for the disagreeing rows (section (c)) "
            f"give the specific interpretive split."
        )
        out.append("")

    # Internal judge contradiction: any row where judge rationale says
    # "matches" while op_validity_pass is False.
    judge_contradictions = []
    for r in rows:
        try:
            j_pass = _parse_bool(r["judge_op_validity_pass"])
        except KeyError:
            j_pass = None
        rationale = (r.get("judge_rationale") or "").lower()
        if j_pass is False and ("matches the payload exactly" in rationale
                                or "every claim" in rationale and "match" in rationale):
            judge_contradictions.append(r["prompt_id"])
    if judge_contradictions:
        bullet_idx += 1
        out.append(
            f"{bullet_idx}. **Internal judge inconsistency** "
            f"(prompts: {', '.join(judge_contradictions)}). The judge "
            f"emitted `op_validity_pass=False` while writing rationale "
            f"text asserting the answer matches the payload. The judge "
            f"is applying different semantics to its prose rationale "
            f"and its structured op-validity check. Visible without "
            f"any human cross-rating."
        )
        out.append("")

    # Refusal disagreements
    if d["disagreements"]:
        bullet_idx += 1
        out.append(
            f"{bullet_idx}. **Refusal-handling disagreements** "
            f"({len(d['disagreements'])} cases). See section (d) for "
            f"the per-prompt detail. The refusal-detection threshold "
            f"in rubric.md (d) is the likely source."
        )
        out.append("")

    # Score-distribution diagnostics (always emitted)
    j_dist = Counter(_parse_int(r["judge_faithfulness_score"]) for r in rows)
    h_dist = Counter(_parse_int(r["human_faithfulness_score"]) for r in rows)
    score4_used = (j_dist.get(4, 0) + h_dist.get(4, 0)) > 0
    score3_used = (j_dist.get(3, 0) + h_dist.get(3, 0)) > 0
    bullet_idx += 1
    if not score4_used and not score3_used:
        out.append(
            f"{bullet_idx}. **Score range not exercised.** Neither rater "
            f"assigned score 3 or 4 on any prompt. The pre-registered "
            f"3-vs-4 boundary anticipated as the calibration weak point "
            f"was not tested; the calibration sample produced only "
            f"score-5 ratings, providing no signal on the rubric's "
            f"discrimination capacity."
        )
    elif not score4_used:
        out.append(
            f"{bullet_idx}. **Score 4 not exercised.** Neither rater "
            f"assigned score 4; the pre-registered 3-vs-4 boundary "
            f"was anticipated as the calibration weak point but the "
            f"observed disagreements are on the 5-vs-3 boundary, a "
            f"different failure mode."
        )
    elif not score3_used:
        out.append(
            f"{bullet_idx}. **Score 3 not exercised.** Neither rater "
            f"assigned score 3; the disagreements are at other "
            f"boundaries."
        )
    else:
        out.append(
            f"{bullet_idx}. **Score range exercised.** Both rubric "
            f"scores 3 and 4 were used by at least one rater across "
            f"the sample, so the 3-vs-4 boundary anticipated at "
            f"pre-registration was tested."
        )
    out.append("")
    out.append("## Verdict")
    out.append("")
    if sec_a["judge_constant"] or sec_a["human_constant"]:
        out.append(
            "**FAIL (degenerate).** Kappa is mathematically undefined "
            "because one rater is constant across the 20-prompt sample. "
            "The pre-registered gate kappa ≥ 0.70 cannot be satisfied "
            "until the constant rater shows discrimination on at least "
            "one prompt. Per pilot_protocol.md, this requires rubric "
            "and/or judge-prompt revision and a re-pilot from a fresh "
            "20-prompt sample (re-seeded). The disagreement and "
            "op-validity patterns above are descriptive only — design "
            "decisions belong to the candidate."
        )
    elif kappa >= 0.70:
        out.append(
            f"**PASS.** kappa = {kappa:.3f} ≥ 0.70. Calibration evidence is "
            f"sufficient to authorise the full LLM-as-judge run on all 48 "
            f"prompts."
        )
    else:
        out.append(
            f"**FAIL.** kappa = {kappa:.3f} < 0.70. Per pilot_protocol.md, "
            f"this requires rubric revision and a re-pilot from a fresh "
            f"20-prompt sample (re-seeded). Surfaced patterns above are "
            f"descriptive only — design decisions belong to the candidate."
        )
    out.append("")
    out.append(
        "_(Generated by `experiment/src/analyze_calibration.py` from "
        f"`{sheet_path.relative_to(REPO)}`.)_"
    )

    out_path.write_text("\n".join(out) + "\n")
    return f"kappa={kappa:.3f} ci=[{ci[0]:.3f},{ci[1]:.3f}] verdict={'PASS' if kappa >= 0.70 else 'FAIL'}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sheet",
        default=str(REPO / "experiment" / "pilot" / "calibration_human_sheet.csv"),
    )
    ap.add_argument(
        "--out",
        default=str(REPO / "experiment" / "pilot" / "calibration_analysis.md"),
    )
    args = ap.parse_args()
    summary = render_report(Path(args.sheet), Path(args.out))
    print(f"Wrote → {args.out}")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
