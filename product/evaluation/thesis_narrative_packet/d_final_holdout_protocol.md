# D-Final Semantic Holdout — Protocol and Integrity Notes

_Authored 2026-05-21. For the thesis integrity section. Documents when the
holdout was authored, how the split was fixed, what the dev set was used for,
and what the 47/48 result means._

---

## 1. When the 48 cases were authored

The 48-case semantic holdout (`semantic_holdout_cases.csv`) was authored on
2026-05-21, the same day as the D-Final design document, implementation, and
closeout report. All were committed as a single body of work at the end of the
System D development sequence (D1 → D2 → D3 → D4 → D-Final).

The cases were authored AFTER D1 was complete and its phrase banks were
finalized. This was intentional: the holdout is defined as language forms
_outside_ D1's vocabulary, so D1's exact coverage had to be known before
cases could be authored. There is no pretense that the cases were authored
blind to D1.

---

## 2. When the 32/16 split was fixed

The 32 dev / 16 heldout split is encoded in the `split` column of
`semantic_holdout_cases.csv` at case-authoring time. The split was fixed
before any D-Final evaluation was run.

Note on documentation discrepancy: the D-Final design doc (§7) and thesis
framing note describe the planned split as "24 dev / 24 heldout". The actual
executed split is 32 dev / 16 heldout, as recorded in the CSV and reflected
in the closeout report (§8 table). The 32/16 split was the implemented design;
the 24/24 language in earlier design prose was a planning estimate. The
closeout is authoritative.

---

## 3. Whether dev was used to tune the LLM prompt or thresholds

**Short answer: the dev set was used to validate the adapter architecture, and
the confidence thresholds were specified in the design doc before evaluation.
There is no evidence of iterative threshold tuning against dev outcomes.**

Longer account:

- The hybrid-guarded policy thresholds (≥0.80 accept; 0.60–0.80 conditional;
  <0.60 reject) are stated in `design.md §6`, which was authored on 2026-05-21
  before evaluation was run on the holdout.
- The risk-zone intents (`objective_value`, `objective_delta`,
  `single_customer_route_membership`, `unknown`) are specified in
  `design.md §5` based on the prior axis 3 analysis, not from dev case outcomes.
- The dev split (32 cases) was available during D-Final development. The
  design intent was to use dev for architectural validation and to confirm the
  adapter fires on the intended surface forms. There is no logged evidence of
  threshold adjustments driven by dev outcomes.

**Caveat**: because the design doc and evaluation were committed on the same
day, the temporal ordering between threshold specification and dev evaluation
cannot be independently confirmed from the git timeline alone. The claimed
ordering (thresholds specified → dev evaluated → heldout evaluated) is
documented here but is not independently verifiable from commit history.

---

## 4. Whether the heldout split was untouched until final run

The heldout cases (SH-09 through SH-12, SH-21 through SH-24, SH-33 through
SH-36, SH-45, SH-46, SH-47, SH-48) are labeled in the CSV at authoring time.
No evaluation result for heldout cases appears in any intermediate report or
design document — the first and only appearance of heldout results is in
`d_final_closeout.md` (heldout 16/16, 100%).

The heldout set was designed to be run once, after all design decisions were
locked. This is documented in the design.md acceptance criteria (§10): D-Final
is promoted only if it meets all criteria, including the holdout result.

---

## 5. Whether cases were generated before or after D1 rules were known

Cases were generated **after** D1 rules were known. This is intentional and
documented:

- Each case in `semantic_holdout_cases.csv` includes a `notes` field
  describing why the phrasing is outside D1's banks (e.g. "clock-out idiom",
  "sign-off idiom", "breach phrasing", "compare-running-fresh maps to
  objective_delta").
- The holdout is not a test of whether D1 could learn these forms; it is a
  test of whether the LLM adapter handles them correctly given that D1 cannot.

This means the holdout should not be interpreted as a fully blind evaluation.
The language forms were specifically chosen to be outside D1's coverage. The
heldout split tests generalization _within_ the space of novel paraphrases, not
generalization to arbitrary operator language.

---

## 6. Caveats on interpreting 47/48

**The single failure is SH-41, which is in the dev split.**

The heldout split (16 cases) scored 16/16 (100.0%).

Key facts about SH-41:

- **Split**: dev (visible during D-Final development).
- **Failure mode**: schema validation error in the LLM output — the LLM was
  called (llm_skipped=False), returned 123 completion tokens, but the output
  had 2 schema validation errors and was rejected. The adapter fell back to D1,
  which also returns `objective_value` (wrong) for this prompt.
- **Root cause**: The C0 classifier requires the past-tense token "compared" to
  set `is_comparative=True` for OBJ prompts. The SH-41 prompt uses the
  present-tense "compare" ("How does this plan compare to running it fresh?"),
  which is not in `_COMPARATIVE_TOKENS`. D1's phrase banks do not extend this
  either.
- **Downstream propagation**: SH-41's wrong intent (`objective_value` instead
  of `objective_delta`) does NOT propagate to a wrong downstream behavior.
  Both `objective_value` and `objective_delta` produce `not_answerable +
  useful_refusal` for this payload context (no baseline available). The
  behavior class result is coincidentally correct.
- **Not a wrong-adjacent error in the dangerous sense**: `objective_value` and
  `objective_delta` are adjacent OBJ intents. The intent error is localized;
  it does not produce a confident wrong answer.

**What 47/48 supports**: D-Final improves substantially over D1's ~62% baseline
on novel paraphrases. The single failure is a boundary case between two
adjacent OBJ intents, caused by a schema error in the LLM response, in the
dev split, with no downstream behavioral consequence.

**What 47/48 does not support**: it does not guarantee D-Final handles all
novel paraphrase forms. The holdout covers 5 semantic subtypes; real operator
language will include forms not in this set.
