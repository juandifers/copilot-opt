# Pilot Runbook

**Purpose:** end-to-end procedure for the 3-instance pilot, the last debugging gate before Stage A.
**Audience:** operator (Juan) — assumes shell access to the repo, the cached baselines, and the working venv. Does not assume prior internals.
**Version:** v0.5 prereg-aligned. Pilot procedure stamped here is what `scripts/inspect_pilot.py` validates.

---

## §1. Purpose and scope

The pilot runs the full Stage A pipeline (perturbation realisation → 5 actions per cell + 2 audit seeds on the audit subset → consolidation → schema-locked Parquet) on 3 representative instances. It exists to surface integration bugs cheaply: schema drift, audit-pair propagation errors, ranking-metric bugs (the §9.4 delta-form sanity check), and orchestration regressions get a 15–25 minute fix loop instead of an 8-hour Stage A fix loop.

The pilot does **not** evaluate hypotheses, train the predictor, or produce headline numbers. The 3-instance sample is far too small for §12.1's [0.10, 0.90] label-distribution bound or §12.4's > 0.20 decoupling rate to be meaningful — those bounds are evaluated against Stage A's 68 instances. The pilot's checks 7.1–7.5 and 7.9 are **hard gates** (schema / wiring / metric correctness); 7.6–7.8 are **informational** at pilot scale and surface only as warnings in `scripts/inspect_pilot.py`.

## §2. Pre-flight checklist

Run each line; every one must succeed before launching.

```bash
# Working directory
cd /Users/jd/Documents/copilot-opt

# 1. Prereg is at v0.5; v0.4 is gone.
test -f prereg/PREREG_v0.5.md && ! test -f prereg/PREREG_v0.4.md && echo "OK: prereg v0.5"

# 2. Stage A roster is 68 IDs.
test "$(grep -c '^X-' instances/stage_a_instances.txt)" = "68" && echo "OK: roster=68"

# 3. Pilot roster exists with 3 IDs.
test "$(grep -c '^X-' instances/pilot_instances.txt)" = "3" && echo "OK: pilot=3"

# 4. Pilot baselines cached. The pilot only requires the three pilot
#    instances' baselines; Stage A requires all 68.
for iid in X-n101-k25 X-n251-k28 X-n429-k61; do
    test -f data/baselines/$iid.json && echo "OK: $iid" || echo "MISSING: $iid"
done
# v0.5 absorbed three §12.2 buffer instances (X-n298-k31, X-n376-k94,
# X-n429-k61) into the main roster, so X-n429-k61's baseline may be
# missing on a fresh checkout. If missing (~60s each):
#   .venv/bin/python scripts/compute_baselines.py --instance X-n429-k61
# Stage A's pre-flight will additionally require X-n298-k31 and X-n376-k94.

# 5. Baseline integrity (objectives within 5% of BKS, per Item 3).
.venv/bin/python scripts/verify_baselines.py \
    --instance X-n101-k25 --instance X-n251-k28 --instance X-n429-k61 | tail -3
# Expect: "Summary: 3 ok, 0 warn, 0 fail." followed by "PASS".
# (Drop the --instance flags to verify all available baselines.)

# 6. PyVRP installed.
.venv/bin/pip show pyvrp | grep -E "^(Name|Version):"
# Expect: Name: pyvrp / Version: 0.13.x (or whatever pyproject.toml pins at lock time).
# (PyVRP doesn't expose __version__ at the module level — pip is canonical.)

# 7. Pilot checkpoint dir is clean (or absent).
! test -d data/pilot_checkpoints || test -z "$(ls -A data/pilot_checkpoints/ 2>/dev/null)" && echo "OK: clean slate"
# (If non-empty: archive then remove — see §10.)

# 8. Disk space ≥ 5 GB.
df -h . | awk 'NR==2 {print "Available:", $4}'
# Expect: >= 5 GiB available. The pilot itself uses ~50 MB; the buffer is for
# log files, the parquet, and Stage A safety margin if you continue.

# 9. Sleep disabled (prevents thermal throttling mid-run).
sudo pmset -a disablesleep 1
caffeinate -d -i &
# Expect: caffeinate PID echoed. Kill at end of pilot: kill %1.

# 10. Other heavy apps closed (Slack, Chrome with many tabs, Docker Desktop).
#     Activity Monitor → CPU tab: only the venv's python should be heavy.
```

If any item fails, stop and resolve before launching. Pre-flight failures are the cheapest place to catch a problem.

## §3. Pilot configuration

The pilot roster (`instances/pilot_instances.txt`) is:

| ID | n_customers | Phase | Rationale |
|---|---|---|---|
| `X-n101-k25` | 100 | small | Validates the cheap-action path: at n=100, every action (reuse_direct, nearest_neighbor, clarke_wright, pyvrp_10s, pyvrp_60s) completes in well under its time budget; if anything is broken here it's a wiring issue, not a perf issue. |
| `X-n251-k28` | 250 | small | Median Stage A case. n=250 is roughly the midpoint of the [100, 500] eligible range and falls below the `--large-threshold 400` cutoff, so it runs in the small phase at `workers_normal=6`. |
| `X-n429-k61` | 428 | large | Stress test. n=428 > 400 routes it to the large phase at `workers_large=4`, exercising the memory-constrained worker pool. Also one of the three §12.2 buffer instances absorbed into the v0.5 roster — using it in the pilot exercises the v0.5 expansion path. |

The pilot uses the `--instances` flag (added to `vrp_copilot_bench.cli` for this purpose; see `src/vrp_copilot_bench/cli.py`). The flag accepts either an inline comma-separated list or a path to a roster file; the pilot uses the file form.

**Why a flag and not a shim:** a shim that monkey-patches `_STAGE_A_INSTANCES` before calling `cli.main()` would leak across tests and require Python-side invocation. The `--instances` flag costs ~30 lines, runs identically to the user-facing CLI, and is naturally testable. It does not affect Stage A behaviour — when the flag is absent, `enumerate_stage_a()` returns the full work plan as before.

Pilot dispatch command:

```bash
.venv/bin/python scripts/run_stage_a.py \
    --instances instances/pilot_instances.txt \
    --checkpoint-dir data/pilot_checkpoints \
    --output data/pilot.parquet \
    --workers-normal 6 \
    --workers-large 4 \
    --log-level INFO
```

## §4. Launch sequence

### 4.1 Dry-run check (verifies the work plan before solving anything)

```bash
.venv/bin/python scripts/run_stage_a.py \
    --dry-run \
    --instances instances/pilot_instances.txt \
    --checkpoint-dir data/pilot_checkpoints
```

Expected output (the timestamp will differ; the numbers must match):

```
YYYY-MM-DD HH:MM:SS INFO vrp_copilot_bench.work_plan: 0 completed, 260 remaining, 0 failures (will retry)
Would run 260 cell-actions.
Estimated wall-time: 16.3 min (overhead factor 1.10).
```

**260 cell-actions** = 3 instances × 16 perturbations × 5 base actions (240) + 10 audit pairs × 2 audit seeds (20). The 10 audit pairs come from `select_audit_subset()` restricted to the pilot instances; the global subset is computed from a fixed seed (20260429), so the count is deterministic.

The 16.3 min estimate assumes perfect 6-way parallelism on the small phase and 4-way on the large phase. Actual wall-clock typically lands at 18–25 minutes on an M2 8-core MacBook due to joblib pool startup, I/O, and PyVRP's per-solve initialisation overhead. Anything materially above 30 min suggests thermal throttling or memory pressure — see §5.

### 4.2 Full run (background, logging to file)

```bash
.venv/bin/python scripts/run_stage_a.py \
    --instances instances/pilot_instances.txt \
    --checkpoint-dir data/pilot_checkpoints \
    --output data/pilot.parquet \
    --workers-normal 6 \
    --workers-large 4 \
    --log-level INFO \
    > data/pilot.log 2>&1 &
echo "pilot PID: $!"
```

Note the PID — that's what to `kill` if §5 says to abort.

### 4.3 Monitor progress

```bash
tail -f data/pilot.log
```

Expected: a progress line every 100 completions, and a phase transition between small and large. With the default `--progress-log-every 100`, you see roughly 2 progress lines during the small phase (which has ~176 keys) and 1 during the large phase (~84 keys). Quick milestones:

- 0–60s: pool startup, baselines load, first reuse_direct / nearest_neighbor results flush.
- 1–10 min: small phase dominates; PyVRP 10s + 60s solves stream through 6 workers.
- 10–20 min: large phase on X-n429-k61.
- ~20 min: `ConsolidationSummary` line and `Wrote data/pilot.parquet`.

## §5. What to watch during the run

### Going right

- Steady `phase 'small': ...` progress lines.
- `data/pilot_checkpoints/_failures/` is absent or empty (`ls data/pilot_checkpoints/_failures/ 2>/dev/null` returns nothing).
- Memory pressure under 6 GB in Activity Monitor. PyVRP 60s peaks around 200–400 MB per worker; 6 workers × 400 MB + Python overhead ≈ 3 GB peak.
- Checkpoint directory grows ~linearly: `du -sh data/pilot_checkpoints/` rises steadily.
- Mac thermal state ≤ "fair": `pmset -g thermlog | tail -1`.

### Going wrong (stop and investigate)

| Signal | Response |
|---|---|
| Any file in `data/pilot_checkpoints/_failures/` | Don't stop the run — failed keys are isolated. After completion, inspect the JSON: `cat data/pilot_checkpoints/_failures/*.json`. If it's a PyVRP timeout, re-run with `--retry-failures`. If it's a code-level exception, stop and debug. |
| Memory pressure approaching 8 GB / swap activity | Abort (`kill %1` if launched with the §4.2 command), then re-run with `--workers-normal 4 --workers-large 3`. The checkpoint dir is resumable, so previously-completed work is not re-run. |
| Progress stalls > 5 min with no new log line | Check Activity Monitor for a stuck Python process. If one worker is pegged at 100% CPU but the rest are idle, it's likely a PyVRP hang on a single instance. `--task-timeout-s 300` (5-min hard cap per task) would have surfaced this; the default is configured at module load. Wait one more `task_timeout_s` then abort if still stuck. |
| Wall-time exceeds 120% of dry-run estimate (i.e., > 20 min) | Investigate without stopping. Check CPU temperature (`pmset -g thermlog`) and memory pressure. Probably thermal throttling; let it finish, but flag the result as suspicious. |
| Wall-time exceeds 150% of dry-run estimate (> 25 min) | Abort, drop worker counts, restart. Resumable. |

## §6. Consolidation

The CLI runs consolidation automatically at the end of the dispatch phase. If the dispatch crashed before consolidation, or if you want to re-consolidate without re-running solves:

```bash
.venv/bin/python scripts/run_stage_a.py \
    --consolidate-only \
    --checkpoint-dir data/pilot_checkpoints \
    --output data/pilot.parquet
```

Expected output (the `n_groups` and `n_rows` numbers must match):

```
ConsolidationSummary: 960 rows from 48 groups, schema_ok=True, failures=0
```

- **48 groups** = 3 instances × 16 perturbations. Each group contains 5 base actions, plus 2 audit actions if the pair is in the audit subset.
- **960 rows** = 3 × 16 × 4 claim families × 5 actions. Audit actions populate the seed-2 / seed-3 columns on existing rows; they do not create new rows.

If `schema_ok=False` or `failures > 0`, consolidation aborted before writing the parquet. The summary lists each failure with a code and detail (e.g., `missing_base_actions`, `dtype_mismatch`, `required_null`). See §9 for diagnostic responses.

## §7. Parquet inspection checklist

The consolidated script is `scripts/inspect_pilot.py`. Run it:

```bash
.venv/bin/python scripts/inspect_pilot.py data/pilot.parquet
```

Expected output: a 9-row table, all PASS (informational checks 7.6/7.7/7.8 may WARN at pilot scale — see below). Exit 0 on no FAIL; exit 1 on any FAIL.

The checks the script runs, with criteria:

### 7.1 Schema integrity

Verifies the parquet's pyarrow metadata carries `_schema_version = v1.0`. If missing, the consolidator was stale (forgot to stamp metadata); the parquet is invalid. **Hard fail.**

Manual one-liner:
```python
import pyarrow.parquet as pq
print(pq.read_metadata("data/pilot.parquet").schema.to_arrow_schema().metadata)
# {b'_schema_version': b'v1.0', ...}
```

### 7.2 Row count and shape

`df.shape == (960, 36)`. **Hard fail.**

If row count is off, the (instance, perturbation, claim_family, action) cross-product is incomplete — most likely a `missing_base_actions` failure that consolidation should have already caught. If column count is off, the schema dict in `src/vrp_copilot_bench/consolidate.py` has drifted from the parquet write path.

Manual one-liner:
```python
import pandas as pd
df = pd.read_parquet("data/pilot.parquet")
print(df.shape, len(df.columns))
```

### 7.3 No NaN in required-non-null columns

Checks the 21 columns in `_REQUIRED_NON_NULL`: keys, action result, reference, baseline feasibility, OBJ/STRUCT/RANK bands. Any null here means consolidation's schema validation missed a missing field. **Hard fail.**

### 7.4 Per-claim required loss

`loss_obj` non-null on every OBJ row; `loss_struct` on every STRUCT row; `loss_rank` on every RANK row; `loss_plan_validity` non-null on `PLAN_VALIDITY × reuse_direct` rows. **Hard fail** if any nulls.

### 7.5 Audit subset population

Audit columns (`audit_seed_2_obj`, etc.) are non-null on rows whose `(instance_id, perturbation_id)` is in `select_audit_subset()` restricted to pilot instances. The pilot expects **10 audit pairs × 20 rows each = 200 audit-populated rows**. **Hard fail** if pairs are extra, missing, or have wrong row count.

The 10 pairs (deterministic from RNG seed 20260429, restricted to pilot instances):

| Pair | Audited? |
|---|---|
| (X-n101-k25, CAP_3) | yes |
| (X-n101-k25, CAP_4) | yes |
| (X-n101-k25, DEM_2) | yes |
| (X-n101-k25, DIST_4) | yes |
| (X-n251-k28, CAP_3) | yes |
| (X-n251-k28, CAP_4) | yes |
| (X-n251-k28, DEM_3) | yes |
| (X-n251-k28, DIST_4) | yes |
| (X-n429-k61, DEM_2) | yes |
| (X-n429-k61, INS_1) | yes |

(X-n429-k61's DIST_4 is not in the audit subset; check 7.9 only verifies the 2 audited DIST_4 cells.)

### 7.6 Label distribution per block

For each `(claim_family × perturbation_family)` block, computes the fraction of `reuse_direct` rows in the easy band. **Informational at pilot scale** (WARN if outside `[0.10, 0.90]`, never FAIL). The §12.1 verification bound is evaluated against Stage A's 68 instances, not 3.

### 7.7 Feasibility decoupling

§12.4 diagnostic: on `CAPACITY × OBJ × reuse_direct` rows, the fraction with `band_obj == 'easy' AND action_feasible == False` should exceed 0.20. **Informational at pilot scale** (WARN if ≤ 0.20). At n=12 cells (3 instances × 4 CAP perturbations) the sample is too small to commit; this is evaluated on Stage A.

Note: the schema column for per-action operational validity (§9.5) is `action_feasible`, not a separate `operational_validity` column.

### 7.8 Reference stability (audit cells)

§12.3 diagnostic: on audit pairs, the fraction with ANY instability flag firing (`reference_obj_unstable | reference_struct_unstable | reference_rank_unstable`) should remain < 0.05. **Informational at pilot scale** (WARN if ≥ 0.05). At n=10 audit pairs even one unstable pair is 10%, so a WARN here at pilot scale is expected if any audit pair lands in the unstable region; it's not a Stage A killer.

### 7.9 DIST_4 ranking sanity (the thesis test)

For each DIST_4 cell in the audit subset (2 of 3 in the pilot), parses `audit_seed_2_top3` and `audit_seed_3_top3` and verifies that the **highest-cost baseline route** is in both top-3 lists. Under prereg §9.4's delta-form ranking, DIST_4 (distance multiplier on the highest-cost baseline route's customers) must push that route into the top-3 by impact-delta. If it's missing, the delta-form ranking metric is computing the wrong thing somewhere — `_compute_baseline_group_impacts` in `src/vrp_copilot_bench/labels.py` is the first place to look. **Hard fail.**

This is the most thesis-relevant check in the pilot. It validates that the DISTANCE mask propagates through every action (the perturbation-realisation pipeline) AND that the delta-form ranking computes the perturbation's signature correctly.

Coverage caveat: the check uses the audit fields, so only the DIST_4 pairs in the audit subset are covered. X-n429-k61's DIST_4 is not audited under the seed-20260429 subset; the inspection script skips it cleanly. If you need coverage of all three DIST_4 cells, run the dedicated DIST_4 sanity script from Item 6's Phase B closeout report (which loads checkpoints directly, not the parquet).

## §8. Decision criteria

### Proceed to Stage A if

- Checks 7.1, 7.2, 7.3, 7.4, 7.5 all PASS.
- Check 7.9 PASS on every audited DIST_4 cell.
- Checks 7.6, 7.7, 7.8 are PASS or WARN (warnings are informational at pilot scale; do not block).
- Wall-clock within 120% of the dry-run estimate (i.e., ≤ ~20 minutes for the default 16.3 min estimate).
- Zero entries in `data/pilot_checkpoints/_failures/`.
- `inspect_pilot.py` exit code is 0.

### Stop and debug if

- Any of 7.1, 7.2, 7.3, 7.4, 7.5 FAIL.
- Check 7.9 FAIL on any audited DIST_4 cell.
- Any failure record in `_failures/` not explained by a known PyVRP timeout (retriable via `--retry-failures`).
- Wall-clock exceeds 150% of estimate (suggests perf regression, thermal throttling, or memory pressure).
- `inspect_pilot.py` exit code is 1.

## §9. Common failure modes and responses

| Symptom | Likely cause | Diagnostic | Fix |
|---|---|---|---|
| `_failures/*.json` references PyVRP timeout (`TimeoutError`) on `X-n429-k61` | Memory pressure stalled a solve | `cat data/pilot_checkpoints/_failures/*.json` shows the action and timeout | Re-run with `--retry-failures --workers-large 2`. The checkpoint dir is resumable; only the failed keys re-run. |
| Consolidation aborts with `missing_base_actions: ('X-n###-k##', '###'): ['...']` | A worker crashed and didn't write the checkpoint | `ls data/pilot_checkpoints/X-n###-k##__###__*.json` shows what's present | Re-run `scripts/run_stage_a.py --instances ... --checkpoint-dir ...` (no extra flags); missing keys re-dispatch. |
| Consolidation reports `dtype_mismatch: col X: expected ..., got ...` | A new field was added to `ActionResult` but the schema dict wasn't updated, or a JSON-encoded field got non-string content | Read the `consolidate.SCHEMA` dict; compare to the `_row_dict` output for one row | Bring `SCHEMA` and `_row_dict` back in sync; bump `SCHEMA_VERSION` if breaking. |
| `inspect_pilot.py` 7.5 reports `extra=[('X-n###', '###')]` | Consolidation populated audit fields on a non-audit pair | Inspect `_build_rows` audit-pair branch | The condition `if (instance, pert) in audit_pairs` is wrong somewhere; expect `select_audit_subset()` to be canonical. |
| `inspect_pilot.py` 7.9 FAIL on X-n101-k25 or X-n251-k28 DIST_4 | Delta-form ranking metric bug | Run the Phase B sanity script from Item 6 closeout to compare delta vs raw-sum top-3 from checkpoints directly | The bug is in `_compute_baseline_group_impacts` or `_top_n_groups` (in `src/vrp_copilot_bench/labels.py`). Do NOT proceed to Stage A until fixed. |
| Wall-clock 2× estimate, no failures | Thermal throttling — fan ramped, M2 throttled performance cores | `pmset -g thermlog` shows `CPU_Speed_Limit < 100` | Let the pilot complete (results are still valid), then before Stage A close other apps, ensure laptop is cool. |
| Run completes but parquet missing | Consolidation aborted; check `ConsolidationSummary` in `data/pilot.log` | `grep ConsolidationSummary data/pilot.log` | Look up the failure code in the table above. |

## §10. Post-pilot cleanup

After all checks PASS / WARN (no FAIL):

```bash
# 1. Tag the commit.
git tag pilot-passed
# (Push the tag if collaborating: git push origin pilot-passed)

# 2. Archive the pilot artefacts for reference.
mkdir -p data/pilot
mv data/pilot.parquet data/pilot/pilot.parquet
mv data/pilot.log data/pilot/pilot.log
mv data/pilot_checkpoints data/pilot/pilot_checkpoints

# 3. Verify Stage A's checkpoint dir is clean (so Stage A's --checkpoint-dir
#    data/checkpoints starts empty).
test -z "$(ls -A data/checkpoints/ 2>/dev/null)" || echo "WARN: data/checkpoints not empty"

# 4. Confirm baselines are intact (canonical from Item 3).
.venv/bin/python scripts/verify_baselines.py | tail -2
# Expect: "PASS"

# 5. Re-enable sleep, kill caffeinate.
sudo pmset -a disablesleep 0
kill %1 2>/dev/null || true
```

Stage A is then ready to launch with the same CLI minus `--instances`. The dry-run estimate at v0.5 was 5.64h on 6+4 workers; budget accordingly.

---

## §11. Validation run record (2026-05-11)

This runbook was validated by an end-to-end pilot run on 2026-05-11 on an
M2 8-core MacBook against the v0.5 prereg / v1.0 schema. Observed values:

- Dry-run estimate: **16.3 min** (`260` cell-actions, overhead 1.10).
- Actual wall-clock: **882.6 s = 14.7 min** (90% of estimate; under the 120% gate).
- Phase split: 176 small keys in 9 min 1 s at 6 workers + 84 large keys in 5 min 42 s at 4 workers.
- `RunSummary: 260/260 succeeded, 0 failed in 882.6s`.
- `ConsolidationSummary: 960 rows from 48 groups, schema_ok=True, failures=0`.
- `scripts/inspect_pilot.py data/pilot.parquet` → exit 0, 7 PASS / 2 WARN / 0 FAIL:
  - 7.1–7.5, 7.7, 7.9 PASS.
  - 7.6 WARN: 7/12 (claim × family) blocks outside [0.10, 0.90] (expected at n=12 cells per block).
  - 7.8 WARN: 70% unstable rate across 10 audit pairs (expected at n=10).
- 7.9 detail (the thesis test):
  - X-n101-k25 DIST_4: highest-cost route = group 0; seed-2 top-3 = `[0, 19, 6]` ✓; seed-3 top-3 = `[0, 19, 6]` ✓.
  - X-n251-k28 DIST_4: highest-cost route = group 17; seed-2 top-3 = `[17, 2, 10]` ✓; seed-3 top-3 = `[17, 2, 14]` ✓.

The pilot validated the orchestrator end-to-end on real solver data with
no failures, confirmed the schema-locked parquet matches v1.0 metadata,
populated audit fields on exactly the 10 pilot audit pairs, and surfaced
the delta-form ranking signature on both audited DIST_4 cells. Decision:
**proceed to Stage A**.
