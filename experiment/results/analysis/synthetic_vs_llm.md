# Source comparison — synthetic vs llm_generated

Per-family comparison. Synthetic prompts are the locked template set;
llm-generated prompts are operator-style paraphrases of the same
underlying questions (locked at `preregistration-prompts-v1`). 24
prompts each, 6 per family in each source.

## Per-family table

`op_val` is runner-shadow op-validity over gradable prompts only.
`refusal` is the runner's `refusal_detected` flag count.

| family | source | n | mean_faithfulness | op_val_pass_rate | refusal_count |
|---|---|---|---|---|---|
| OBJ | synthetic     | 6 | 5.000 | 3/3 = 1.000 | 0 |
| OBJ | llm_generated | 6 | 5.000 | 2/4 = 0.500 | 0 |
| PLAN_VALIDITY | synthetic     | 6 | 5.000 | 2/2 = 1.000 | 0 |
| PLAN_VALIDITY | llm_generated | 6 | 5.000 | 2/2 = 1.000 | 0 |
| STRUCT | synthetic     | 6 | 5.000 | 5/5 = 1.000 | 0 |
| STRUCT | llm_generated | 6 | 4.833 | 2/3 = 0.667 | 2 |
| SCHEDULE | synthetic     | 6 | 4.667 | 4/6 = 0.667 | 0 |
| SCHEDULE | llm_generated | 6 | 5.000 | 6/6 = 1.000 | 0 |

## Per-source aggregate

| source | n | mean_faithfulness | op_val_pass_rate (runner) | refusals |
|---|---|---|---|---|
| synthetic     | 24 | 4.917 | 14/16 = 0.875 | 0 |
| llm_generated | 24 | 4.958 | 12/15 = 0.800 | 2 |

The two sources are within 0.04 mean faithfulness of each other.
Direction of the difference flips at the family level: SCHEDULE is
better on llm_generated (5.000 vs 4.667 — the single faithfulness 3
on the run, prompt 040, falls on the synthetic side); STRUCT is
better on synthetic (5.000 vs 4.833). Per-source cell sizes
(n = 6 per family-source) are below the threshold where a paired test
would be informative; the differences are within noise.

## What the source comparison registers

**The generator's behavior is roughly insensitive to phrasing.** A
synthetic prompt (`"What's the total cost on this plan after the
time windows got tighter?"`) and an llm-generated prompt (`"What
did this end up costing compared to running a full re-solve?"`) land
on the same kind of answer when the underlying payload supports the
question. The 24-prompt synthetic set and the 24-prompt llm-generated
set produce indistinguishable headline numbers. This was not
pre-registered as a Claim, but it is a methodology observation: the
prompt-set composition can be expanded to operator-style phrasings
without breaking faithfulness.

**Refusal behavior concentrates on llm_generated STRUCT.** Both
refusals in the run (prompts 027 and 036) are llm-generated STRUCT
prompts. The synthetic STRUCT prompts the generator answered all
six times. The llm-generated STRUCT prompts the generator refused
twice. Both refusals were on questions about truck-count or
new-customer attribution where the payload exposes only post-
perturbation state and the answer would have required a baseline-
to-perturbed comparison the payload did not surface. The
llm-generated phrasings happen to put more weight on such
comparisons. This is not a generator bias — the synthetic STRUCT
templates may simply have under-represented this question type.

**The two faithfulness sub-5 prompts split across sources.** Prompt
025 (f = 4, STRUCT, llm_generated) is a refusal that the judge
underscored. Prompt 040 (f = 3, SCHEDULE, synthetic) is the route-
indexing convention case. No clear source-bias pattern across the
two cases.

## Statistical claims

Per-family cell sizes are n = 6 each. The smallest source-paired
comparison cell is 6-vs-6. With faithfulness clustered at 5 and
deviations rare, a paired Mann-Whitney or sign test would be
underpowered. Per-family op-validity rates are computed over even
smaller cells (e.g., OBJ llm_generated gradable = 4). A statistical
test on these cell sizes would not produce informative p-values.

The honest framing for the analysis: the source comparison is
descriptive. The two sources produce equivalent headline numbers
within the precision of n = 6 per family. The pattern that does
emerge (llm-generated STRUCT prompts produce refusals on
comparison-style questions) is a finding about the prompt set
composition, not about the generator. Future iterations that want
to exercise source-by-family contrasts more rigorously would need
n = 20+ per family-source cell.
