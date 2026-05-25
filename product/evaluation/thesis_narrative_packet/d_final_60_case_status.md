# D-Final on the Run 2 60-Case Benchmark — Status Clarification

_Authored 2026-05-21. Clarifies what has and has not been evaluated, why only
15 cases are materialized, and what the official regression result is._

---

## 1. Has D-Final been evaluated on all 60 Run 2 cases?

**No.** D-Final has been evaluated on 15 of the 60 Run 2 benchmark cases.

---

## 2. Why only 15 materialized?

The Run 2 benchmark cases require a fully materialized payload to be evaluated
by any system (C0, D1, D-Final). A "materialized" case means:

1. The experiment runner produced a generator JSONL record for that prompt
   (`experiment/results_RUN1/generator/full-run-v1.jsonl`), AND
2. The resulting payload fields are available for the contract to evaluate
   against.

The `full-run-v1` artifact in `experiment/results_RUN1/` contains outputs from
the Stage A experiment (48 prompts × Solomon-100 + Homberger-200). The Run 2
benchmark was authored with 60 distinct cases derived from operator-style
natural-language prompts. The overlap between the 48 Stage A prompts and the
60 Run 2 cases yields 15 cases whose payloads can be reconstructed from the
local artifact.

The remaining 45 Run 2 cases require either:
- A separate experiment run targeting the Run 2 prompt set specifically, OR
- Manual payload construction for the cases whose prompts don't map to Stage A
  run outputs.

**This is a materialization gap, not an evaluation design gap.** The D-Final
evaluation framework supports all 60 cases; the payload inputs are simply not
locally available for 45 of them.

---

## 3. What blocks the remaining 45 cases?

| Blocker | Category | Count |
|---|---|---|
| Payload not in `full-run-v1` (prompt not in Stage A run) | Payload materialization | 45 |
| API path issues | None identified | 0 |
| Evaluation not yet run | Follows from materialization gap | 45 |

The blocking condition is exclusively **payload materialization**: the generator
JSONL records for the 45 cases do not exist in the local Stage A run artifacts.

The D-Final evaluation code (`run_system_d_final.py`,
`product/evaluation/run2_payloads.py`) is capable of processing all 60 cases
once payloads are provided. Running the full 60-case evaluation requires either
completing a dedicated Run 2 experiment run or constructing payloads for the
45 unmaterialized cases.

---

## 4. What is the official Run 2 D-Final regression result?

**Official result**: **0 regressions on 15 materialized cases (15/15 intent
correct).**

This is the only number that should be cited as the D-Final Run 2 regression
result in the thesis. Specifically:

| Metric | Value |
|---|---|
| Cases evaluated | 15 (materialized subset) |
| D-Final intent accuracy | 15/15 (100.0%) |
| Regressions vs D1 | 0 |
| Source | `d_final_closeout.md §8`, `d_final_core_report.csv` |

---

## 5. How to qualify the 15/15 result in prose

The 15/15 result should be stated with its scope qualifier:

> "D-Final was evaluated on the 15 Run 2 benchmark cases whose payloads
> materialize from the Stage A `full-run-v1` artifact. On this subset,
> D-Final matches D1 exactly: 15/15 cases correct, 0 regressions. The full
> 60-case benchmark evaluation is blocked pending complete payload
> materialization."

Do NOT cite "0 regressions on Run 2" as if it covered all 60 cases. The
holdout set (47/48 on 48 semantic holdout cases) is the primary evidence for
D-Final generalization; the 15-case Run 2 check is a regression gate only.

---

## 6. What the complete 60-case picture requires

To evaluate D-Final on all 60 Run 2 benchmark cases:

1. Run the experiment runner with a prompt set targeting the 45 unmaterialized
   Run 2 cases: `python experiment/src/run_experiment.py --run-id run2-payloads`
2. The runner will produce generator JSONL records for those prompts.
3. Run `run_system_d_final.py` on the full 60-case set using the combined
   artifact.

Alternatively, `product/evaluation/run2_payloads.py` has a manual payload
construction path that can be used for a subset of cases without a full
experiment run.

Until this is done, the 15-case subset result is the authoritative D-Final
Run 2 regression number.
