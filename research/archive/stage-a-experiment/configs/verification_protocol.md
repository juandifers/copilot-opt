# Human-verification protocol — locked at preregistration-v1

After the full LLM-as-judge run, 25% of the prompts (12 of 48) are
re-verified by the candidate against the locked rubric. Disagreements
between the human verification and the judge are flagged for the
discussion section but do not change the headline scores; the locked
analysis uses judge scores throughout.

## Sample (12 prompts, 25%)

3 prompts per family. Within each family, the 3 prompts are sampled
60/40 weighted toward FP + FN quadrants vs TP + TN quadrants, to
concentrate verification effort on the cells where the predictor's
mistakes manifest at the language layer.

## Deterministic sampling algorithm

`random.Random(2026)` at the top of the verification-sampling script
in Prompt 6 or later. The seed is the same number as the
stratification seed; the verification draws are made independent by
the offset structure below.

```
SEED = 2026
WEIGHT_FP_FN = 0.6
WEIGHT_TP_TN = 0.4
PER_FAMILY = 3

for family_idx, family in enumerate(['OBJ', 'PLAN_VALIDITY',
                                     'STRUCT', 'SCHEDULE']):
    # Partition this family's 12 prompts into the two pools.
    pool_fp_fn = [p for p in family_prompts
                  if (p.sufficient_binary == 1 and p.policy_accept == False)
                  or (p.sufficient_binary == 0 and p.policy_accept == True)]
    pool_tp_tn = [p for p in family_prompts
                  if p not in pool_fp_fn]
    
    # Target counts at 60/40.
    target_fp_fn = round(PER_FAMILY * WEIGHT_FP_FN)  # = 2
    target_tp_tn = PER_FAMILY - target_fp_fn         # = 1
    
    # Fallback redistribution if a pool is under-populated.
    if len(pool_fp_fn) < target_fp_fn:
        deficit = target_fp_fn - len(pool_fp_fn)
        target_fp_fn = len(pool_fp_fn)
        target_tp_tn += deficit
    if len(pool_tp_tn) < target_tp_tn:
        deficit = target_tp_tn - len(pool_tp_tn)
        target_tp_tn = len(pool_tp_tn)
        target_fp_fn += deficit
    
    # Sample without replacement, sorted-then-shuffled for determinism.
    rng = random.Random(SEED + 2000 + family_idx)
    pool_fp_fn = sorted(pool_fp_fn,
                        key=lambda p: (p.instance_id, p.perturbation_id))
    pool_tp_tn = sorted(pool_tp_tn,
                        key=lambda p: (p.instance_id, p.perturbation_id))
    chosen_fp_fn = rng.sample(pool_fp_fn, target_fp_fn)
    chosen_tp_tn = rng.sample(pool_tp_tn, target_tp_tn)
    
    verification_set.extend(chosen_fp_fn + chosen_tp_tn)
```

The "redistribute the remainder uniformly across the other three
quadrants" wording in the spec is implemented here as the
deficit-redistribution between the two pools (FP+FN vs TP+TN); the
four-quadrant resolution falls out of the pool composition.

For the locked stratification (`stratification.md`), each family has
12 prompts distributed as Solomon (2+2+3+2) + Homberger (1+1+0+1) or
(0+1+0+2) for SCHEDULE. FP = insuff_accept, FN = suff_escalate.

Per family, pool sizes by family:

| family | FP (insuff_accept) | FN (suff_escal) | TP (suff_accept) | TN (insuff_escal) |
| --- | --- | --- | --- | --- |
| OBJ | 3 | 3 | 3 | 3 |
| PLAN_VALIDITY | 3 | 3 | 3 | 3 |
| STRUCT | 3 | 3 | 3 | 3 |
| SCHEDULE | 3 | 3 | 2 | 4 |

Every pool ≥ 2 except SCHEDULE TP at 2 (Solomon=2 + Homberger=0). The
target 2 FP+FN + 1 TP+TN per family is satisfiable everywhere; no
fallback redistribution triggers under the locked stratification.

## Outputs

- `experiment/results/verification_set.csv` — the 12 chosen prompt_ids
  with family, quadrant, source, instance_id, perturbation_id.
- `experiment/results/verification_results.csv` — candidate score,
  judge score, |diff| per prompt.
- `experiment/reports/verification_writeup.md` — summary with the
  agreement rate (% of prompts where candidate-judge |diff| ≤ 1) and
  per-prompt notes on the disagreements. This becomes a citable
  artifact in the thesis methodology section.

Disagreements with |diff| ≥ 2 are flagged in the discussion section
but do not alter the headline scores. The locked analysis is
judge-driven.
