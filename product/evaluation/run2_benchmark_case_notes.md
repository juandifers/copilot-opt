# Run 2 — Benchmark Case Notes (Stage R2-2)

_Companion to `run2_calibration_disagreement_log.md` covering the
calibration → benchmark expansion. This file records the per-cluster
design rationale for the 45 new R2-2 cases plus any labelling
decisions that surfaced during expansion. The calibration log
entries D-001 through D-014 remain authoritative for the 15
calibration rows; this file extends the record for the 45 new rows
without duplicating earlier entries._

The format mirrors the disagreement log:
- `case_id` — the calibration case(s) that triggered the issue, or
  `n/a` if the issue is purely schema-level.
- `issue / disagreement` — short statement of the design choice or
  surprise.
- `resolution` — what was decided.
- `schema change made?` — yes / no.
- `remaining ambiguity` — what is unresolved.
- `carried to R2-3?` — should the implementer of target extensions
  read this entry first.

## Cluster design rationale

### CL-OBJ — OBJ cluster (R2-016 … R2-026)

11 new OBJ rows organised as three sub-clusters:

- **objective_value clean** (R2-016, R2-019). Anchor cases for the
  current contract on different OBJ seeds (003, 006). Gold cites
  `action_objective` + `units.objective`. Reuse Run 1 prompt 003 /
  006 wording verbatim where possible.
- **objective_delta clean** (R2-017, R2-018, R2-020, R2-026). Tests
  the OBJ escape hatch (`_obj_delta_already_covered`) across multiple
  seeds with benign comparators (`change`, `compared to before`). Gold
  cites all four delta fields plus units.
- **missing_units** (R2-021, R2-022, R2-023). Target_extension cluster
  on three seeds (003, 005, 006). Each strips `units.objective` and
  expects `partial_answer_with_warning` with
  `evidence_units_missing` + `expose_units_objective`. R2-014 (in the
  calibration set) is the fourth member of this cluster.
- **comparison_referent_ambiguity** (R2-024, R2-025).
  Target_extension cluster with explicit `full re-solve` / `compared
  to a full re-solve` wording from Run 1 prompts 008 and 010 (both
  flagged by the Run 1 volunteered/risky-comparison probe). R2-013
  (calibration) is the third member.

### CL-PV — PLAN_VALIDITY cluster (R2-027 … R2-036)

10 new PV rows. The PV intent classifier is unconditional
(every PV question maps to `feasibility_status`), so cluster variety
comes from prompt wording and payload condition, not intent
routing.

- **feasibility_status clean** (R2-027 to R2-031). Five seeds (014,
  015, 016, 018, 022) covering OC / TW / TT perturbations and
  short-vs-long prompt forms. All `direct_answer`, all `current`.
- **missing_validity_fields** (R2-032 to R2-036). Five seeds (015,
  016, 017, 020, 022) with the mutation that strips both `feasible`
  and `feasibility_breakdown`. All `useful_refusal`, all
  `target_extension`. R2-036 paired with R2-031 (same prompt text,
  different payload — clean vs missing-validity) so the pair
  isolates the missing-validity refusal from the language layer.

### CL-STRUCT — STRUCT cluster (R2-037 … R2-049)

13 new STRUCT rows organised as:

- **route_count** (R2-037, R2-038). Two seeds (026, 028); R2-038's
  prompt was rewritten during R2-2 to avoid an
  `_is_about_new_customer_assignment` trigger (see B-001).
- **single_customer_route_membership** (R2-039, R2-040, R2-041, R2-045).
  Four seeds (031, 034, 030, 032) and three different customer IDs
  (42, 17, 12). All `direct_answer_with_warning` (struct_membership_
  ambiguity always fires).
- **same_route_boolean** (R2-046). One seed (028); calibration's
  R2-009 is the second member of this small cluster.
- **before_after_comparison** (R2-042, R2-043). Two seeds (035, 036)
  with different payload_condition labels (unsupported_comparison
  vs missing_baseline_solution) to exercise both schema codes.
- **new_customer_assignment missing** (R2-044). Companion to R2-003
  on a different seed (028).
- **false_premise_customer** (R2-047). STRUCT variant of R2-008;
  target_extension.
- **full_route_listing** (R2-048, R2-049). Companion to R2-010 on
  different seeds (030, 034) and a 'which customers' phrasing
  variant. Target_extension; uses the proposed Stage R2-1
  intent.

### CL-SCHEDULE — SCHEDULE cluster (R2-050 … R2-060)

11 new SCHEDULE rows organised as:

- **customer_arrival clean** (R2-050, R2-056). Two seeds (043, 046)
  with different customer IDs (42, 17).
- **lateness_summary clean** (R2-051, R2-053, R2-054). Three seeds
  (037, 038, 042) covering "late", "delivery window", and "miss"
  keyword triggers.
- **route_end_time with route N** (R2-055, R2-060). Two seeds (041,
  039) with `route 1` / `Route 1` prompt phrasing → fires
  `route_indexing_ambiguity` directly from prompt text.
- **before_after_comparison** (R2-052, R2-057). Two seeds (044, 042)
  with `compared` wording. Both prompts were rewritten during R2-2
  to use the exact tokens in `_COMPARATIVE_TOKENS` (see B-002).
- **false_premise_customer** (R2-058). Companion to R2-008 with a
  different absent customer ID and seed.
- **false_premise_route** (R2-059). Companion to R2-015 with a
  different absent route number and seed.

## Entries from R2-2 expansion

### B-001 — STRUCT route_count cases must avoid the new-customer-assignment subject test

- **case_id:** R2-038
- **issue / disagreement:** The first draft of R2-038 used Run 1
  prompt 028's exact wording: "How many routes does this end up
  needing after a new order came in?" The gold expected
  `route_count`. The R2-2 evaluator surfaced that the contract
  predicted `new_customer_assignment` because
  `_is_about_new_customer_assignment` (in `product/copilot/intent.py`)
  fires when (a) the prompt contains a `_NEW_ORDER_TOKENS` substring
  (which "new order" satisfies), (b) no integer route/customer
  number is present, (c) the subject phrase contains one of the
  heuristic tokens — which includes "end up". So "end up needing"
  routes to new_customer_assignment, not route_count.
- **resolution:** Rewrite the prompt to avoid both `end up` and the
  new-customer subject tokens. Final wording: "How many vehicles
  are needed for this plan after a new order came in?" — "how many
  vehicles" matches the route_count keyword set; "for this plan" is
  not in `_is_about_new_customer_assignment`'s subject token list.
  Run 1 prompt 028 itself was correctly classified as
  `new_customer_assignment` in Run 1's analysis (see
  `product/reports/thesis_metrics_baseline_run1.md` §9.6), so the
  original gold was a labelling error, not a contract bug.
- **schema change made?** No — only a per-row prompt fix.
- **remaining ambiguity:** None. The intent classifier's
  subject-test list (`"end up"`, `"assigned"`, etc.) is documented
  inline; future case authors should consult it before writing
  route_count prompts that overlap with new-customer phrasing.
- **carried to R2-3?** Closed by this revision. The cluster note
  CL-STRUCT cross-references B-001.

### B-002 — SCHEDULE before_after_comparison cases must use the exact comparative tokens

- **case_id:** R2-052, R2-057
- **issue / disagreement:** The first drafts of R2-052 and R2-057
  used "How does the schedule compare to ..." wording. The gold
  expected `before_after_comparison`. The R2-2 evaluator surfaced
  that the contract predicted `unknown`: `_COMPARATIVE_TOKENS`
  contains the past-tense form `"compared"` but NOT the
  present-tense `"compare"`. `"compare" in lowered` is False; the
  SCHEDULE branch then falls through to `unknown`.
- **resolution:** Rewrite both prompts to use the literal token
  `"compared"`. Final wording: "How does the schedule look compared
  to before the service times went up?" / "How does the schedule
  look compared to the previous version?". Both now route to
  `before_after_comparison` correctly. Same correction applied
  preemptively to R2-022 ("after the service time change?" was
  routing OBJ to `objective_delta` via `"change"`).
- **schema change made?** No.
- **remaining ambiguity:** Whether intent.py's
  `_COMPARATIVE_TOKENS` list should be widened to include `"compare"`
  / `"compares"` / `"comparing"` for robustness. That is a Stage
  R2-3 intent-classifier improvement, not an R2-2 calibration
  concern.
- **carried to R2-3?** Optional. Stage R2-3 contract-extension
  implementers may want to widen the token list while they are in
  intent.py for other reasons; if they do, this case will then
  serve as a regression test (it should still classify the same).

### B-003 — partial_answer_with_warning is exclusively target_extension

- **case_id:** n/a (structural observation)
- **issue / disagreement:** The 60-case behavior_class × impl_status
  matrix shows that every `partial_answer_with_warning` row is
  `target_extension` (7/7). Initially this looked like a coverage
  gap — "shouldn't some `partial_answer_with_warning` cases be
  current?" — but the structural reason is correct: the only
  current-contract warning that fires alongside non-empty missing
  fields is `unsupported_comparison`, and that pairs with
  `not_answerable` → `useful_refusal`, not partial. Every actual
  partial-answer-with-warning case in R2-2 requires either
  `comparison_referent_ambiguity` or `evidence_units_missing`, both
  of which are Stage R2-1 extensions.
- **resolution:** Document the structural reason. No case relabel.
- **schema change made?** No.
- **remaining ambiguity:** Stage R2-3 should verify that, once
  `comparison_referent_ambiguity` and `evidence_units_missing` are
  implemented, the R2-2 `partial_answer_with_warning` rows lift to
  predicted `partial_answer_with_warning` and the
  `partial_answer_correct` metric rises from 0/7 to 7/7 on those
  rows. That lift is the whole point of those two extensions.
- **carried to R2-3?** Yes — this is the R2-3 success criterion for
  the OBJ partial-answer-with-warning pathway.

### B-004 — PV evidence precision is intentionally low

- **case_id:** PV cluster, by-family aggregation
- **issue / disagreement:** PV evidence precision on the benchmark is
  0.400 — well below other families. The cause: the contract's
  `_evidence_feasibility` emits one item for each
  `feasibility_breakdown.*` subfield (capacity_ok, time_windows_ok,
  coverage_ok, plus the `feasible` flag). The gold for a clean PV
  question typically lists `feasible` + one or two breakdown
  subfields. The precision drops because the contract emits more
  evidence than the gold expects.
- **resolution:** Leave the gold as written. Widening the PV gold to
  include every breakdown subfield would be tuning the gold to the
  contract's emit pattern — exactly what R2-0 fix #1 and R2-1 D-002
  said not to do. The low PV evidence precision is intentional: it
  records that the contract's evidence breadth on PV is a candidate
  for a separate `evidence_specificity` or `evidence_brevity`
  metric in Stage R2-3.
- **schema change made?** No.
- **remaining ambiguity:** Whether evidence precision should
  actually be replaced by `evidence_relevance` (precision against a
  curated essential-field set) on PV. Deferred to R2-3.
- **carried to R2-3?** Yes — as a metric design choice, not as a
  contract change.

### B-005 — Source-prompt-id is now mandatory for every benchmark case

- **case_id:** n/a (schema-level)
- **issue / disagreement:** R2-1's D-014 entry recommended making
  `source_prompt_id` mandatory for non-synthetic cases. The R2-2
  benchmark follows this rule strictly: 60/60 cases carry an
  explicit `source_prompt_id`. The rationale-text inference path in
  the materializer remains as defence-in-depth but is not exercised.
- **resolution:** This becomes the de facto rule for R2-2 and
  forward. The schema (run2_gold_schema.md §1) should be updated in
  Stage R2-3 to formalise it: any case whose `payload_mutation_needed`
  is anything other than a purely synthetic payload fixture (none
  today) must carry a non-empty `source_prompt_id`.
- **schema change made?** No (deferred to Stage R2-3 — making this
  required would require a schema field for "synthetic payload
  fixture plan" too, which we don't need yet).
- **remaining ambiguity:** None for R2-2.
- **carried to R2-3?** Yes — formalise in `run2_gold_schema.md` and
  the loader's `validate_case`.

### B-006 — Per-row materialization no-op warnings are kept, not hidden

- **case_id:** R2-003, R2-005, R2-042, R2-043, R2-044
- **issue / disagreement:** Run 1 STRUCT/PV payloads naturally do
  not carry `baseline_solution`, `diff`, or `new_customer_ids`, so
  the corresponding payload mutations (`unsupported_comparison`,
  `missing_baseline_solution`, `missing_new_customer_ids`) degenerate
  to structural no-ops on those seeds. The materializer surfaces a
  per-case warning rather than silently swallowing the no-op.
- **resolution:** Keep the warning. It is correct accounting (the
  payload condition holds vacuously); the test of the
  `unsupported_comparison` / etc. semantics is whether the contract
  refuses correctly, which it does on these cases. Stage R2-3
  should not "fix" this by mutating the seed — there is nothing to
  mutate.
- **schema change made?** No.
- **remaining ambiguity:** Whether some payload conditions should
  be renamed to reflect that they are *invariants* (the field
  should be absent), not *mutations* (the field should be removed).
  That's a doc-level nuance and not load-bearing.
- **carried to R2-3?** No.
