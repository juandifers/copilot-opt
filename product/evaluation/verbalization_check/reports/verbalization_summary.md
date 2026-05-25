# Verbalization Faithfulness Check — Summary

_2026-05-21. Evaluates whether the template-based verbalization renderer_
_faithfully renders the structured D-Final contract into natural language._

## Scope note

This evaluation does not replace the Run 2 product-contract benchmark.
The structured contract remains the primary evaluated artifact.
This check only tests whether the natural-language answer text faithfully
renders the already-produced contract object.

The retired 48 × 2×2 generator/judge experiment is not used because the
thesis no longer evaluates free-form model answer generation as the primary
object. Instead, the product emits a structured contract, and this smaller
check evaluates whether the final text shown to the operator preserves that
contract.

**Renderer evaluated**: `product/copilot/verbalization.py` (template-based,
deterministic, no LLM calls).

## Headline results

| Metric | Value |
|---|---|
| Cases | 24 |
| **Overall pass rate** | **100.0% (24/24)** |
| Faithful to contract | 100.0% |
| Critical omission rate | 0.0% |
| Unsupported addition rate | 0.0% |
| Numeric/entity error rate | 0.0% |
| Warning preservation rate | 100.0% |
| Missing-field preservation rate | 100.0% |
| Compute-decision preservation rate | 100.0% |

## Results by behavior class

| Behavior class | n | Pass |
|---|---:|---:|
| `direct_answer` | 6 | 6/6 = 100.0% |
| `direct_answer_with_warning` | 6 | 6/6 = 100.0% |
| `partial_answer_with_warning` | 3 | 3/3 = 100.0% |
| `useful_refusal` | 9 | 9/9 = 100.0% |

## Failures

No failures — all 24 cases pass.

## Interpretation

Thresholds (post-hoc, not pre-registered):
- ≥ 90%: verbalization acceptable for thesis demo
- 75–90%: usable with caveats
- < 75%: prototype-only; structured contract remains the evaluated artifact

