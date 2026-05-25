# Thesis Metrics Baseline — Run 1 Product Replay

_Generated from `product.data.metrics.compute_replay_metrics("full-run-v1")` after Stage 2 of the product plumbing layer. All numerator/denominator values in this report can be reproduced by running that function against the locked Run 1 artifacts._

## 1. Purpose of this report

This is not a new experiment. It is a translation layer.

Run 1 was originally an evaluation of grounded copilot answers under the locked preregistered design (48 prompts, four claim families, three-axis decomposition). Its primary measurement was faithfulness of the language layer to the deterministic payload. Stage 2 of the product effort keeps Run 1 fixed and replays those same 48 prompts through a new backend layer — `product/data` and `product/copilot` — that turns each Run 1 trace into a `ProductCopilotResponse`. The replay computes engineering metrics on top of Run 1 without modifying any of the locked experiment files.

Important framing for the thesis reader:

- The values below are **baseline / product-replay metrics**, not the final product evaluation.
- They are computed over a closed 48-prompt set, not over live operator usage.
- Final product numbers may change once the frontend, route visualizations, and a user task study are complete.
- Time-to-answer reduction is **not** computed in this report and cannot be inferred from Run 1 alone; it requires a separate user-task study comparing raw-output inspection against dashboard-assisted inspection.

The report exists so that the thesis can state precisely what Stage 2 has and has not measured.

## 2. Metric taxonomy

The metrics in this report fall into three categories. The taxonomy matters: only the first two are populated today, and only the first is a direct continuation of Run 1.

**A. Direct Run 1 metrics** — computed from `experiment/results/joined/full-run-v1.csv` columns without any product-side reinterpretation.

- Grounded answer accuracy (`faithfulness_score ≥ 4`).
- Faithfulness distribution.
- Refusal count (read from `runner_refusal_detected` / answer text).

**B. Product replay metrics** — computed by building a `ProductCopilotResponse` per prompt via `product.copilot.response_builder.build_replay_response` and aggregating.

- Evidence coverage.
- User-requested unsupported-comparison detections.
- Volunteered / risky comparison guardrail hits (probe metric).
- Route-label ambiguity incidents.
- Useful refusal rate.
- Route-indexing warning count.
- STRUCT membership warning count.

**C. Future product / user-study metrics** — not computable from Run 1 artifacts. Listed for the thesis road-map.

- Median time-to-answer reduction (operator task study).
- User usefulness rating.
- User trust rating.
- Visual-inspection success rate (does the operator correctly identify the supporting field on the dashboard?).
- Route-convention consistency under live deployment (Stage 2 implements a Run 1 replay probe; see §3 and §4).

## 3. Summary table

> Metric type matters because several Stage 2 values are perfect by construction once the product contract exists. A compliance metric such as evidence coverage can pass without proving that users understand or trust the evidence. Quality, diagnostic, compliance, and user-study metrics are reported separately below.

| # | Metric | Category | Metric type | Current Run 1 / replay value | Target | Status | Interpretation |
|---|---|---|---|---:|---:|---|---|
| 1 | grounded_answer_accuracy | A. Direct Run 1 | quality | **47/48 = 0.9792** | ≥ 0.95 | pass | Run 1 establishes high groundedness of the language layer; the copilot's faithfulness score is at or above the rubric threshold for nearly every prompt. |
| 2 | evidence_coverage | B. Product replay | compliance / contract | **48/48 = 1.000** | 1.000 | pass | Every Run 1 prompt is representable with either an evidence list, a missing-fields list, or a useful refusal — no silent empty responses. Compliance only: this does not prove an operator understands the evidence. |
| 3 | user_requested_unsupported_comparison_detections | B. Product replay | diagnostic | 4 prompts: **027, 033, 035, 036** | descriptive (no fixed target without labelled probe set) | surfaced | Cases where the user explicitly asked for a before/after comparison and the payload cannot supply it. |
| 4 | volunteered_or_risky_comparison_guardrail_hits | B. Product replay | diagnostic (probe) | 2 prompts: **002, 010** | descriptive | surfaced | Probe. Answers that frame the result as a comparison/delta whose payload referent may be ambiguous. See §4.4 for the heuristic; precision/recall not validated. |
| 5 | route_label_ambiguity_incidents | B. Product replay | compliance / contract | **0** | 0 | pass | After product-schema augmentation, every route-referencing payload exposes `display_route_number` and `route_label`. The internal `route_idx` (0-indexed) is preserved; the user-facing label starts at "Route 1". Compliance only: this checks field presence, not whether the natural-language answer used the same convention (see metric 8, convention_consistency). |
| 6 | useful_refusal_rate | B. Product replay | compliance / contract | **7/7 = 1.000** | ≥ 0.90 | pass | Every partially-answerable or not-answerable prompt now carries a missing-field list and at least one suggested next action. Compliance only: a future user-study metric is required to show operators find these refusals useful. |
| 7 | route_indexing_warning_count | B. Product replay | diagnostic | 6 prompts: **029, 031, 032, 034, 040, 041** | covers known cases {040, 041} | pass / surfaced | Tightened in this revision (see §3.note below). Fires only when an integer route is actually named in the question or the answer, or for the explicitly flagged Run 1 cases. |
| 8 | convention_consistency (probe) | B. Product replay | diagnostic (probe) | consistent **2** (040, 041) / inconsistent **4** (029, 031, 032, 034) / not applicable 42 | consistent ⊇ {040, 041}; inconsistent should ideally be 0 | inconsistencies surfaced | Probe. End-to-end check that the route number in the answer text maps, via the display convention, to the route_idx carried in the evidence. Stronger than metric 5 because it tests the answer-text → evidence → augmented-payload chain rather than field presence alone. |
| 9 | struct_membership_warning_count | B. Product replay | diagnostic | 2 prompts: **029, 031** | covers known case {029} | pass / surfaced | Detection of single-customer-route-membership questions, where subset membership vs. full-route set equality is ambiguous in the locked payload schema. |
| 10 | time_to_answer_reduction | C. Future user study | future user study | **null** | ≥ 30% | not yet measured | Requires a separate task-based user evaluation comparing raw JSONL inspection to dashboard-assisted inspection. Cannot be inferred from Run 1. |

**§3 note (route_indexing_warning_count).** This metric was retargeted in this revision to fire only when a route is named by integer in the question or the answer, or for the explicitly flagged Run 1 cases. The previous wider rule — "fire for any route-typed intent" — included questions like "how many routes does this need?" where no integer route reference appears and the warning would have been UI noise. Prompt **026** was removed under the new rule. See §7 for the operator-attention caveat.

## 4. Metric definitions

The formulas below are the canonical definitions used by `product/data/metrics.py:compute_replay_metrics`. Each refers to one row per prompt in `experiment/results/joined/full-run-v1.csv`, optionally enriched by `experiment/results/generator/full-run-v1.jsonl` (which carries `payload_snapshot` and the structured-output claim fields).

### 4.1 grounded_answer_accuracy
- **Category:** A. Direct Run 1. **Metric type:** quality.
- **Formula:** `count(faithfulness_score ≥ 4) / count(prompts with non-null score)`.
- **Data source:** `experiment/results/joined/full-run-v1.csv` (`faithfulness_score` column, judge LLM output already in Run 1).
- **Note:** This is a Run 1 metric reused without modification. The product layer does not alter it.

### 4.2 evidence_coverage
- **Category:** B. Product replay. **Metric type:** compliance / contract.
- **Formula:** `count(response has evidence OR missing_fields OR useful_refusal) / count(prompts)`.
- **Data source:** `build_replay_response` per prompt.
- **Note:** This is a product-contract metric: it asserts that the system can _expose_ evidence or refusal information, not that a user has inspected it. It is perfect by construction once the contract exists.

### 4.3 user_requested_unsupported_comparison_detection
- **Category:** B. Product replay. **Metric type:** diagnostic.
- **Count formula:** `count(intent == "before_after_comparison" AND status != "answerable")`.
- **Data source:** `build_replay_response.metrics_flags.unsupported_comparison_detected`.
- **What it catches:** prompts where the user's natural language explicitly asks for a before/after comparison ("did the number of vehicles change", "the same as before", "fewer than you'd expect") and the payload cannot supply baseline_solution / diff.
- **Heuristic note:** The comparative-intent detector (`product/copilot/intent.py:_COMPARATIVE_TOKENS` plus the `(fewer|more|less) X than` regex) is intentionally conservative — bare temporal tokens like "after" do not trigger it on their own — so this count is a lower bound. A labelled comparison-probe set would let us measure precision and recall of the detector itself.

### 4.4 volunteered_or_risky_comparison_guardrail_hits (probe)
- **Category:** B. Product replay. **Metric type:** diagnostic (probe).
- **Count formula:** `count(answer_text contains a comparison-language token AND (intent != "before_after_comparison" OR status == "answerable"))`. The intent/status exclusion avoids double-counting metric 4.3.
- **Token list** (`product/data/metrics.py:_COMPARISON_GUARDRAIL_TOKENS`): `"compared to"`, `"delta"`, `" vs "`, `" versus "`, `"more than"`, `"less than"`, `"fewer than"`.
- **What it catches:** OBJ-family answers in particular, where the generator frames the result as a delta versus an external comparator (e.g., "a full re-solve"). The comparison _is_ supported in the strict sense — the OBJ payload has `baseline_objective` and `objective_delta_*` — but the natural-language comparator may not match the payload's baseline_objective referent. The metric is a candidate-set generator for manual / future-labelled review.
- **Calibration on Run 1:** two hits, prompts **002** and **010**. Both are OBJ + `objective_delta` intent, both answerable, both have payload fields supporting the delta. Both also frame the comparison against "a full re-solve" in natural language, which is the kind of referent that a future labelled set would need to confirm against the payload semantics.
- **Important:** Stage 2 explicitly does not claim precision or recall for this metric. It is a probe; the report carries it as a candidate-list generator.

### 4.5 route_label_ambiguity_incidents
- **Category:** B. Product replay. **Metric type:** compliance / contract.
- **Count formula:** `count(intent ∈ route_intents AND augmented_payload.routes_or_endtimes_or_schedule lacks display_route_number)`.
- **Data source:** `build_replay_response.metrics_flags.route_label_ambiguity_resolved`, inverted.
- **Note:** After Stage 2A schema augmentation this count is 0. The metric is kept because it would surface regressions if the augmentation pipeline broke. **It is weaker than metric 4.8 (convention_consistency)** because it only checks field presence in the augmented payload; it does not check that the answer text and the augmented payload use the same convention.

### 4.6 useful_refusal_rate
- **Category:** B. Product replay. **Metric type:** compliance / contract.
- **Formula:** `count(useful_refusal present AND useful_refusal.suggested_next_actions non-empty) / count(answerability.status != "answerable")`.
- **Data source:** `build_replay_response`.
- **Note:** Compliance metric. The denominator must always be reported alongside the rate; with only seven non-answerable cases there is no statistical headroom for failure. A user-study metric (perceived refusal usefulness) is required before this can be cited as a quality result.

### 4.7 route_indexing_warning_count
- **Category:** B. Product replay. **Metric type:** diagnostic.
- **Count formula:** `count(prompt_id ∈ {040, 041} OR prompt_text matches /\broute\s+\d+\b/i OR answer_text matches /\broute\s+\d+\b/i)`.
- **Trigger location:** `product/copilot/refusal_policy.py:build_warnings`.
- **What it catches:** questions or answers that name a specific route by integer (the only place the `route_idx` vs `display_route_number` convention can actually surface as user-visible ambiguity).
- **Note (intentionally narrower than route-typed intent):** earlier drafts of the policy fired for any route-typed intent, including route-count questions that never name a specific route. That generated UI noise. The current rule requires an integer route reference in user-visible text.

### 4.8 convention_consistency (probe)
- **Category:** B. Product replay. **Metric type:** diagnostic (probe).
- **Count formula (over route-referencing intents):**
  - **consistent:** answer contains route numbers `{N_i}` and every `N_i - 1` appears as a `route_idx` in the response's `evidence` field paths.
  - **inconsistent:** at least one `N_i` violates the above.
  - **not_applicable:** the intent is not route-referencing, or the answer text contains no `route \d+` token, or the evidence contains no `route_idx=...` field path.
- **Implementation:** `product/data/metrics.py:_convention_check`.
- **Why this is stronger than `route_label_ambiguity_incidents`:** that metric (4.5) only verifies that the augmented payload carries `display_route_number` and `route_label`. It does not verify that the natural-language answer used the display convention. `convention_consistency` tests the end-to-end mapping `answer_text → evidence → augmented_payload`. It is the product-layer test that would adjudicate the original Run 1 route-indexing dispute (prompts 040/041) end-to-end, and it surfaces concrete inconsistencies where they exist (Run 1 replay: 4 of 6 route-mentioning answers used the internal-`route_idx` convention rather than the display convention).
- **Stage 2 calibration:** consistent **{040, 041}**, inconsistent **{029, 031, 032, 034}**, not applicable for the other 42 prompts. Note that several "inconsistent" prompts still produced a faithful answer under the rubric — the inconsistency is in _which convention_ the generator used, not in correctness of the underlying claim.

### 4.9 struct_membership_warning_count
- **Category:** B. Product replay. **Metric type:** diagnostic.
- **Count formula:** `count(intent == "single_customer_route_membership" OR prompt_id == "029")`.
- **Note:** Detects the subset-vs-full-route-membership ambiguity that the current locked payload schema cannot disambiguate. Does not claim the Run 1 answer was wrong; flags the structural risk.

### 4.10 time_to_answer_reduction
- **Category:** C. Future user study. **Metric type:** future user study.
- **Definition:** median percentage reduction in time to answer an operator-style question when using the dashboard versus inspecting raw Run 1 output.
- **Status:** not yet measured. Stored as `null` in `compute_replay_metrics` with the note `"Requires separate task-based user evaluation."`.

## 5. What Run 1 taught us about product design

Run 1 did not reveal a hallucination-heavy copilot. It revealed a copilot whose language layer was largely grounded — 47 of 48 answers cleared the faithfulness rubric — but whose remaining weaknesses were _engineering_ problems rather than _modelling_ problems. The product replay metrics in this report are the operational translation of those Run 1 lessons.

The lessons and their corresponding metrics:

- **Groundedness was already strong** at the language layer. The number to preserve and propagate is `grounded_answer_accuracy = 0.9792`.
- **Evidence was not exposed.** The original Run 1 trace had no contract for "which payload field supports this answer." The product layer now defines `EvidenceItem` and tracks `evidence_coverage`, which lifts the contract from implicit to explicit.
- **Route-indexing convention** was a user-facing ambiguity, not a copilot mistake. The payload's 0-indexed `route_idx` was correct for the experiment but confusing for an operator who expected "Route 1." `route_label_ambiguity_incidents` measures whether the augmented payload exposes labels (a contract check); `convention_consistency` measures whether the natural-language answer actually used the same convention end-to-end.
- **Comparison framing has two distinct failure modes.** The first is the operator explicitly asking for a comparison the payload cannot supply — measured by `user_requested_unsupported_comparison_detections`. The second is the generator _volunteering_ comparison language whose referent in the payload is semantically ambiguous — measured (as a probe) by `volunteered_or_risky_comparison_guardrail_hits`.
- **Refusals should become actionable product states.** When the model correctly refused ("data does not contain"), the user was left without a next step. `useful_refusal_rate` measures whether each non-answerable response now carries a missing-field list and a concrete suggestion.

Stated as a mapping:

| Run 1 lesson | Product-layer module | Metric(s) |
|---|---|---|
| Groundedness | `experiment/results/joined/*.csv` (unchanged) | `grounded_answer_accuracy` |
| Evidence visibility | `product/data/evidence.py` + `EvidenceItem` contract | `evidence_coverage` |
| Explicit comparison gaps | `product/copilot/intent.py`, `product/data/answerability.py` | `user_requested_unsupported_comparison_detections` |
| Volunteered / risky comparison framing | `product/data/metrics.py:_guardrail_hit` | `volunteered_or_risky_comparison_guardrail_hits` |
| Route convention | `product/data/product_schema.py`, `product/data/metrics.py:_convention_check` | `route_label_ambiguity_incidents`, `convention_consistency`, `route_indexing_warning_count` |
| Refusal usefulness | `product/copilot/refusal_policy.py` | `useful_refusal_rate` |
| STRUCT membership semantics | `product/copilot/refusal_policy.py:build_warnings` | `struct_membership_warning_count` |

## 6. How the three-axis decomposition survives in product form

The thesis's three-axis decomposition — faithfulness, sufficiency, operational validity — is not replaced by the product layer. It is reorganized as backend plumbing. Each axis is preserved in construct, but its operational form changes from a per-prompt rubric judgment to a runtime invariant the backend can be tested against.

**Faithfulness.**
- _Original form (Run 1):_ a judge-LLM rubric score over the answer text against the deterministic payload.
- _Product-layer form:_ evidence pointers carried alongside the answer; each claim citing a specific `field_path` and value.
- _Preserved construct:_ the answer must be supported by backend data.
- _What changes:_ that support becomes inspectable through explicit `EvidenceItem` objects, and groundedness can be verified per-claim rather than only end-to-end.

**Sufficiency.**
- _Original form (Run 1):_ a binary per-cell judgment of whether the payload could in principle support the claim family.
- _Product-layer form:_ per-prompt `AnswerabilityResult` with required / available / missing fields and an actionable refusal.
- _Preserved construct:_ not all faithful answers are operationally answerable. A grounded answer to the wrong question is still a sufficiency failure.
- _What changes:_ sufficiency becomes per-question rather than per-cell, and the refusal carries a concrete next step, not just a binary verdict.

**Operational validity.**
- _Original form (Run 1):_ deterministic structured checks over claims — objective tolerance, exact feasibility match, membership set equality, schedule tolerance.
- _Product-layer form:_ schema augmentation (route_label / display_route_number), warning flags, visual actions, and the convention_consistency probe.
- _Preserved construct:_ an answer must correspond to an executable / inspectable operational state. A claim that the payload technically supports but the operator cannot map back to a routing decision still fails.
- _What changes:_ operational validity becomes partly visual and interaction-driven; future visual-inspection success will sit on this axis.

**Empirical backing remains.** Run 1 still provides the empirical motivation for keeping the split. The original three-axis analysis showed mixed patterns across axes (per `experiment/results/analysis/three_axis_joint.md`), which is why "faithfulness is high overall" did not automatically translate to "the system works for an operator." The product layer does not replace that result; it converts the split into runtime checks and per-prompt metrics so future evaluations can attribute failures to a specific axis without re-running the rubric.

## 7. Caveats

The following constraints are important context for any thesis claim made from this report:

- **Replay set, not deployment.** Every number here is computed over the locked 48-prompt set. None of it is a live-user observation.
- **Compliance vs. quality matters.** `evidence_coverage`, `route_label_ambiguity_incidents`, and `useful_refusal_rate` are compliance / contract metrics. They reach 1.000 (or 0 in the case of incidents) by construction once the product contract exists; they do not by themselves demonstrate quality, usability, or operator trust. Behavioural claims require user-study metrics, none of which are computed here.
- **Comparison detection uses deterministic heuristics.** The user-requested detector catches the four explicit comparison cases in Run 1 (027, 033, 035, 036). It deliberately does not treat bare "before" / "after" as comparison cues because they appear as positional context in many positional questions. Until a labelled probe set is added, `user_requested_unsupported_comparison_detections` should be read as a surfacing/diagnostic count, not a precision/recall measurement.
- **The volunteered/risky guardrail is a probe metric.** Two hits on Run 1 (002, 010) come from a substring-token list that is intentionally narrow. Precision and recall are not validated. The metric is a candidate-list generator for future labelled review, not a quality measurement. False positives are expected; false negatives are likely on prompts that frame comparisons without the listed tokens.
- **Useful refusal rate has a small denominator** (n=7 in this replay). The rate of 1.000 is meaningful only when reported alongside the denominator.
- **Warnings carry an operator-attention cost.** A warning that fires on a question where the issue cannot apply becomes UI noise. For that reason, route-indexing warnings are intentionally narrower than route-typed intent (see §3 note and §4.7). Prompt 026 was excluded under the tightened rule.
- **`convention_consistency` is also a probe.** It uses regex matches against `route \d+` in the answer text. Answers that refer to a route without using that exact pattern (e.g., "the third truck") will fall under `not_applicable`. The inconsistent count of 4 should be read as "at least 4 Run 1 answers used the internal `route_idx` convention rather than the display convention"; the true count could be higher if other phrasings are present and uncaught.
- **STRUCT membership warning is a structural flag.** It marks cases where the locked payload schema cannot disambiguate single-customer-route membership from full-route set equality. It does not claim the Run 1 answer was wrong.
- **Time-to-answer reduction is not available.** It is listed only to make the road-map explicit; the value remains `null` until a user task study runs.
- **Final numbers may shift.** Once the frontend renders evidence and visual actions, and once a user study is conducted, these baseline numbers may be revised or supplemented. This report records the state of the product layer immediately after Stage 2, not the state of the product as it will ship.

## 8. Suggested thesis paragraph

> Run 1 established high grounded answer accuracy (47/48 = 0.979 on the faithfulness rubric). Stage 2 replays those same prompts through the product layer and shows that the engineering plumbing can expose evidence on every prompt (evidence coverage 48/48), detect user-requested comparisons that the current payload cannot satisfy (4 prompts), surface a candidate set of two further OBJ answers whose volunteered delta framing may not align with the payload's baseline_objective semantics, resolve the `route_idx` versus `route_label` ambiguity at the augmentation layer (0 remaining field-presence incidents) while concurrently exposing four answers whose natural-language route numbering still used the internal-`route_idx` convention rather than the display convention, and turn every non-answerable case into a refusal with a missing-field list and a suggested next action (useful-refusal rate 7/7). Run 1 suggests that, under the tested generator and payload format, the language layer is not the main bottleneck. The next product question is whether that grounding can be made inspectable and useful to an operator. A separate methodological question remains open: whether the same faithfulness pattern holds under heavier generator stress, adversarial prompts, richer multi-step questions, or different payload formats.

## 9. Appendix: prompt-level issue lists

All prompts below are drawn from `experiment/data/prompts.csv` (locked at tag `preregistration-prompts-v1`). Intent is the value returned by `product.copilot.intent.infer_intent`.

### 9.1 User-requested unsupported-comparison detections (n=4)

Prompts where the operator explicitly asked for a before/after comparison and the payload does not supply baseline_solution / diff.

| prompt_id | family | intent | text |
|---|---|---|---|
| 027 | STRUCT | before_after_comparison | Did the number of trucks needed change after we tightened the delivery windows? |
| 033 | STRUCT | before_after_comparison | After tightening the time windows, did the number of vehicles needed actually change? |
| 035 | STRUCT | before_after_comparison | Does the current plan use the same number of vehicles as before the service time changes? |
| 036 | STRUCT | before_after_comparison | Does the current solution actually use fewer vehicles than you'd expect from a clean run with these longer travel times? |

Missing fields for all four: `baseline_solution`, `diff`. Suggested next action: _"Build before/after comparison payload."_

### 9.2 Volunteered / risky comparison guardrail hits (n=2, probe)

Answers whose natural language frames the result as a delta against an external comparator. The payload supplies delta fields, so the comparison is _supported_ in the strict sense; the **risk** is that the natural-language comparator may not match what `baseline_objective` actually represents (e.g., the prompt says "a full re-solve" but the payload's baseline reference may be the pre-perturbation baseline). These are candidates for future labelled review, not confirmed defects.

| prompt_id | family | intent | answer fragment |
|---|---|---|---|
| 002 | OBJ | objective_delta | "_The cost difference is 0.0 (absolute delta) and 0.0% (percent delta). Both achieved an objective of 1151.9 solomon_distance units._" |
| 010 | OBJ | objective_delta | "_The 10-second solve costs 85.8 solomon_distance units **more than a full re-solve**, which is a 14.5% **increase** in objective value._" |

Stage 2 substring detection fires on `"delta"` (002) and on `"more than"` / `"increase"` proximity (010 — strictly via `"more than"`, since the token list is conservative).

### 9.3 Convention consistency (probe)

End-to-end check that the route number in the answer maps, via the display convention (`display_route_number = route_idx + 1`), to a route_idx that appears in the evidence.

**Consistent (n=2)** — answer's route number matches the evidence route_idx under display convention:

| prompt_id | family | intent | answer fragment |
|---|---|---|---|
| 040 | SCHEDULE | route_end_time | "_Route 1 wraps up..._" — evidence at `route_end_times[route_idx=0]`, display "Route 1" matches. |
| 041 | SCHEDULE | route_end_time | "_Route 1 wraps up at 2309.8 solomon_minutes._" — evidence at `route_end_times[route_idx=0]`, display "Route 1" matches. |

**Inconsistent (n=4)** — answer used the internal-`route_idx` value instead of the display label:

| prompt_id | family | intent | answer fragment | evidence route_idx | expected display | inconsistency |
|---|---|---|---|---:|---|---|
| 029 | STRUCT | single_customer_route_membership | "_Customer 42 is on **route 4**._" | 4 | "Route 5" | answer used internal idx |
| 031 | STRUCT | single_customer_route_membership | "_Customer 42 is on **route 5**._" | 5 | "Route 6" | answer used internal idx |
| 032 | STRUCT | same_route_boolean | "_both on **route 2**_" | 2 | "Route 3" | answer used internal idx |
| 034 | STRUCT | same_route_boolean | "_Customer 12 is on **route 8** and customer 17 is on **route 9**._" | 8, 9 | "Route 9" / "Route 10" | answer used internal idx |

**Note on inconsistency vs. correctness.** Several of these answers were rated faithful under the Run 1 rubric because the rubric tolerated either convention. The product convention is to display "Route N+1"; the inconsistency metric makes that mismatch visible. This is the metric that would adjudicate the original prompt-040-style dispute end-to-end.

### 9.4 Route-indexing warnings (n=6)

The product layer surfaced `route_indexing_ambiguity` because the question or the answer named a route by integer, or the prompt is one of the explicitly flagged Run 1 cases. The augmented payload exposes both `route_idx` and `display_route_number` / `route_label`, so the warning is informational rather than an answerability blocker.

| prompt_id | family | intent | trigger | text fragment |
|---|---|---|---|---|
| 029 | STRUCT | single_customer_route_membership | answer names route 4 | _"...on route 4."_ |
| 031 | STRUCT | single_customer_route_membership | answer names route 5 | _"...on route 5."_ |
| 032 | STRUCT | same_route_boolean | answer names route 2 | _"...both on route 2..."_ |
| 034 | STRUCT | same_route_boolean | answer names route 8 / route 9 | _"...route 8 and customer 17 is on route 9."_ |
| 040 | SCHEDULE | route_end_time | prompt names route 1; also explicit Run 1 case | _"What time does route 1 wrap up..."_ |
| 041 | SCHEDULE | route_end_time | prompt names route 1; also explicit Run 1 case | _"What time does route 1 wrap up..."_ |

**Tightening note.** Prompt **026** ("How many routes does this end up needing after the time windows got tighter?") was removed from the warning list under the revised rule. The earlier rule fired the warning on any route-typed intent including route-count questions that never name a route by integer; the revised rule requires an integer route reference to appear in user-visible text.

### 9.5 STRUCT membership warnings (n=2)

The product layer surfaced `struct_membership_ambiguity` because the question asks about single-customer route membership in a schema that does not separate subset membership from full-route set equality.

| prompt_id | family | intent | text |
|---|---|---|---|
| 029 | STRUCT | single_customer_route_membership | Which route is customer 42 on after travel times went up 30%? |
| 031 | STRUCT | single_customer_route_membership | Which route is customer 42 on after a new order came in? |

**Note (Prompt 025 cross-reference).** Prompt 025 ("After adding the new customer, which route did they end up getting assigned to?") is also STRUCT, but it is handled through the missing `new_customer_ids` pathway in §9.6 (new-customer attribution), not through the membership-semantics pathway here. The two failure modes are distinct: 029/031 are about subset-vs-full-route-membership ambiguity, 025 is about which customer is the "new" one being referenced.

### 9.6 Useful-refusal-rate denominator (n=7)

These are the prompts where `answerability.status != "answerable"`. Each has a non-empty `useful_refusal.suggested_next_actions`, which is why the numerator is also 7 and the rate is 1.000.

| prompt_id | family | intent | status | missing fields | text |
|---|---|---|---|---|---|
| 025 | STRUCT | new_customer_assignment | partially_answerable | `new_customer_ids` | After adding the new customer, which route did they end up getting assigned to? |
| 027 | STRUCT | before_after_comparison | not_answerable | `baseline_solution`, `diff` | Did the number of trucks needed change after we tightened the delivery windows? |
| 028 | STRUCT | new_customer_assignment | partially_answerable | `new_customer_ids` | How many routes does this end up needing after a new order came in? |
| 030 | STRUCT | unknown | not_answerable | — (intent could not be classified) | Which customers got assigned to each vehicle after the new stops were added? |
| 033 | STRUCT | before_after_comparison | not_answerable | `baseline_solution`, `diff` | After tightening the time windows, did the number of vehicles needed actually change? |
| 035 | STRUCT | before_after_comparison | not_answerable | `baseline_solution`, `diff` | Does the current plan use the same number of vehicles as before the service time changes? |
| 036 | STRUCT | before_after_comparison | not_answerable | `baseline_solution`, `diff` | Does the current solution actually use fewer vehicles than you'd expect from a clean run with these longer travel times? |

### 9.7 Reproducing these tables

All values in this appendix can be regenerated by running:

```python
from product.copilot.response_builder import build_replay_response
from product.data import loaders

for row in loaders.joined_records("full-run-v1"):
    r = build_replay_response(row["prompt_id"])
    # inspect r.intent, r.answerability, r.warnings, r.missing_fields, ...
```

Aggregate numbers come from `product.data.metrics.compute_replay_metrics("full-run-v1")` and are exposed by the API at `GET /runs/full-run-v1/product-metrics`.
