# Run 2 System A — Design

_Stage R2-6 design document. Defines System A — the "deterministic-prior + GPT-5.4-mini hybrid" baseline — and pins exactly how it differs from System B (R2-4A prompt-only) and System C-extended (R2-3 deterministic contract)._

## 1. Motivation

R2-4A established that GPT-5.4-mini, given the Run 2 prompt template and a clean payload projection, hits 0.95+ on intent and answerability and 0.92+ on behavior class on the 60-case benchmark. R2-5 then showed that this single-sample headline is partially an upper bound: under k=5 the strict pass^k_all rate is 3/10 on a hard subset:

- 3 of 5 target-extension cases are stably correct (R2-008 / R2-012 / R2-015).
- 2 of 5 target-extension cases are flaky (R2-048 at 0.40 all-pass rate, R2-058 at 0.80).
- All 5 R2-4A current-row failures stay failures across every replicate.

The instability has two distinct flavours:

- **Intent confusion** on lexically ambiguous prompts (R2-040 "Which route is customer 17 on…" predicted as `new_customer_assignment`; R2-051 "Is anyone going to be late…" predicted as `feasibility_status`).
- **Warning omission** on cases that require a *policy* warning the surface prompt does not name (R2-055 / R2-060 omitting `route_indexing_ambiguity` on "route 1" / "Route 1").

System A is the narrow experiment that asks: if we hand the model the deterministic *intent prior*, *answerability prior*, *missing-fields prior*, and *warning prior* that the rule-based contract already computes, does the model become contract-stable on those cases?

## 2. Positioning

- **System B** (R2-4A baseline) — the model produces every contract field from scratch given the prompt + payload + schema. No deterministic scaffolding.
- **System A** (this stage) — a deterministic prior layer computes intent / answerability / missing fields / warnings / next actions from the materialised payload. The model receives those priors alongside the prompt and payload, is told which fields are *locked* (must be preserved unless flagged as a disagreement), and emits the final JSON.
- **System C-extended** (R2-3 reference) — the deterministic contract emits every field; no model is in the loop.

System A is deliberately a *thin* prior layer. It re-uses the same `infer_intent`, `compute_answerability`, `build_warnings`, and `suggested_next_actions_for_missing_fields` functions C-extended calls — the only thing that changes is who emits the final JSON. If A converges on C-extended's score on the R2-5 subset, the wedge between B (model-alone, 0.30 pass^k) and C (rule-based, 1.0 pass^k by construction) is mostly explained by the prior, not by anything else the rule layer brings.

## 3. What System A fixes deterministically

The prior layer computes — and the prompt instructs the model to preserve, unless explicitly flagged as a disagreement:

- **intent_prior** — from `product.copilot.intent.infer_intent(prompt_text, family)`. Locked.
- **answerability_prior** — from `product.data.answerability.compute_answerability(prompt_text, family, payload, intent)`. Locked.
- **required_fields** + **available_fields** — bookkeeping, surfaced to the model for context.
- **missing_fields_prior** — locked. The model may not invent or remove missing fields.
- **warnings_prior** — locked. The model may not invent warnings beyond the allowed schema; it may not remove a prior warning unless it flags `prior_disagreement=true`.
- **next_actions_prior** — locked when they follow directly from `missing_fields_prior` via `suggested_next_actions_for_missing_fields(…)`.
- **behavior_class_prior** — locked. Derived from the (answerability, evidence, warnings) tuple via the same projection as the C-extended adapter.

"Locked" means: the model is told to copy these into its output JSON unchanged unless it sets `prior_disagreement=true` and explains in `adapter_notes` why the prior is wrong.

## 4. What the model still does

- **Final JSON.** The model emits the canonical contract object — System A is not just a thin pass-through that bypasses the model.
- **Evidence paths.** The prior does not pre-compute evidence; the model picks the field-family paths it cites. (The prior *does* give it the list of `required_fields` for the intent so the model has a hint about which paths the field-family scorer cares about.)
- **answer_text.** Optional one-sentence operator-facing answer or refusal narrative.
- **Disagreement.** If the model believes the prior is wrong (e.g. the prior fired `false_premise_detected` but the model can see the named entity *is* in the payload), it must set `prior_disagreement=true` and explain in `adapter_notes`. We will analyse disagreements separately.

## 5. What System A does not do

- **No repo-agent access.** The model only sees the prompt + payload projection + priors. No file system, no scorer code, no benchmark CSV.
- **No solver calls.** Same as B.
- **No gold labels in the prompt.** Same as B.
- **No scorer access.** The model does not know which fields the rubric weights or how the scorer normalises predicate-pinned paths.
- **No benchmark report access.** No leakage of R2-4A or R2-5 scores into the prompt.
- **No C-extended output copying.** A computes its prior independently using the same functions C-extended uses; it does NOT call `run_system_c_on_case` and read the predicted contract — because then A would be C-extended-with-an-extra-step. A produces an *answerability-and-warning* skeleton; the model fills it in.
- **No prompt access to `generator_record.structured_output`.** The deterministic prior layer is called with `generator_record=None` to match the way evaluators see the case at score time. (C-extended uses `generator_record` for claim-aware evidence pinning in the per-case predictions, but A does not.)

## 6. Failure-mode hypotheses

These are the behaviours System A is expected to *test*; the actual pass^k results will confirm or refute them.

- **R2-040 / R2-051 (intent confusion).** Prior says `single_customer_route_membership` / `lateness_summary`. If the model preserves the locked intent, all-pass should rise from 0/5 (System B) to ≥k-1/k.
- **R2-055 / R2-060 (omitted route warning).** Prior says `direct_answer_with_warning` and includes `route_indexing_ambiguity` in `warnings_prior`. If the model copies the warning, all-pass should rise from 0/5 to ≥k-1/k.
- **R2-048 (over-cited evidence on a target-extension success).** Prior locks intent `full_route_listing`, answerability `answerable`, no warnings. The model still picks evidence; the flakiness was about evidence over-citation, so the prior alone may not fix it.
- **R2-058 (single bad refusal sample on a useful_refusal case).** Prior fires `false_premise_detected`. If the model copies the warning + missing list, the bad sample should disappear.
- **R2-027 (PV evidence-subkey enumeration).** Prior provides `required_fields` `[feasible, feasibility_breakdown]` — but the *gold rubric* enumerates `feasibility_breakdown.{capacity_ok,time_windows_ok,coverage_ok}` separately, which neither the prior nor C-extended emits. A is therefore expected to remain a stable failure on R2-027.

## 7. Stop criteria

R2-6 stops after:

- design doc (this file),
- prior + prompt + runner + parser implementation + their tests,
- a 5-case smoke,
- a 10-case × k=3 pass^k on the R2-5 subset,
- the optional 30-case single-sample comparison **only if** the pass^k succeeds (defined as A pass^k_all ≥ B pass^k_all on the same subset, with concrete recovery of at least two of the four intent-or-warning failure cases),
- a final report comparing A vs B vs C-extended.

R2-6 does **not** run the full 60-case pass^k for System A, does **not** run Claude Code as model-under-test, and does **not** modify any locked file (benchmark CSV, gold schema, scorer, experiment configs).
