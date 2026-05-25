# Stage A → Run 2 Pivot

_Authored 2026-05-21. The pivot is documented as an empirical finding, not
an arbitrary transition. Use this framing in the thesis narrative._

---

## 1. What Stage A asked

Stage A started with the claim-family sufficiency question: given a VRPTW
payload, can we predict whether a backend solver action (cheap-accept vs
escalate-to-full-solver) is "sufficient" for a given claim family?

The Stage A HistGB predictor learned that sufficiency is claim-dependent —
not a single scalar property of the payload but a function of what the
operator is actually asking. A plan might be sufficient for an OBJ value
question (the objective field is present) but insufficient for a SCHEDULE
lateness query (the lateness breakdown is absent). The predictor captured
this per-family pattern.

This was the right first step: it proved that the backend action decision
cannot be divorced from the operator's intent.

---

## 2. What Stage A exposed

Stage A's closing experiment (48 prompts, Haiku generator, Sonnet judge)
showed that the three-axis decomposition separates axis outcomes — axis
separability held (Claim 1, 60.4% mixed rate). But the policy-effect and
sufficiency-manifests claims did not register (Claims 2 and 3 failed).

The diagnosis: the generator was at ceiling. On insufficient cells, Haiku
either refused correctly (useful refusal) or answered from a legitimate
sub-claim. The three-axis decomposition did not surface the predicted
faithfulness-sufficiency divergence because the generator's refusal behavior
masked the signal.

More importantly, Stage A surfaced a structural gap: the Stage A sufficiency
predictor decided whether the payload was *sufficient for a family*, but it
could not tell the operator:
- whether their specific question was answerable from the current payload,
- what evidence fields supported the answer, or
- what was missing and how to obtain it.

A user-facing copilot needs all three of those things.

---

## 3. The empirical motivating observation

When the labelling work for Run 2 was conducted, the four-axis coding of
Stage A outputs revealed that the same payload condition could produce
wildly different verdict shapes depending on what the operator was actually
asking. The "pass/warn/fail" aggregate from Stage A collapsed distinct failure
modes:

- The system answered correctly and cited correct fields (answerable, faithful).
- The system refused for a valid reason (not answerable, useful refusal).
- The system would have answered correctly if the payload carried a different
  field (not answerable, missing field).
- The system answered but cited evidence the payload did not actually contain
  (answerable, faithfulness failure).

Separating these required asking not just "is the payload sufficient?" but
"does the payload contain the specific fields the operator's question requires?"

---

## 4. The bridge sentence

> The sufficiency predictor asked whether a backend action was good enough
> for a claim family; Run 2 asks whether a copilot can recognise what claim
> is being made, determine whether the current payload contains the required
> state, and emit the correct evidence-backed product behaviour.

---

## 5. What Run 2 is

Run 2 is the product-contract translation of the Stage A sufficiency idea.

Where Stage A evaluated:
- `suff_accept` vs `suff_escal` (two payload conditions)
- free-form answer text (judge-graded faithfulness)
- one aggregate score per prompt

Run 2 evaluates:
- `intent` → was the claim family correctly identified at the operator's
  specific intent level (not just family)?
- `answerability` → does the current payload contain the fields the
  specific question requires?
- `evidence fields` → which exact fields ground the answer?
- `missing fields` → what is absent that would make a not-answerable prompt
  answerable?
- `warnings` → what ambiguities, comparator gaps, or policy violations
  should the operator know about?
- `behavior class` → what product interaction shape results?

Run 2's evaluation instrument is the structured contract response, not judge-
graded answer text. The unit of evaluation is the response object itself.

The three-axis decomposition carries forward from Stage A:
- **Faithfulness** → `evidence_precision` (the contract may not cite fields
  the payload doesn't contain)
- **Sufficiency** → `evidence_recall` + `missing_field_recall` (the contract
  must cite every field the payload supports; missing fields must be named)
- **Operational validity** → `intent_correct`, `answerability_correct`,
  `behavior_class_correct`, `useful_refusal_correct`

---

## 6. The architectural claim the pivot supports

Stage A proved that intent matters for sufficiency (claim-family dependency).

Run 2 shows that intent matters for the entire contract response:
- wrong intent → wrong answerability → wrong evidence → wrong behavior
- Conditional on correct intent: answerability, evidence, warnings, and
  behavior class are all correct (100% conditional accuracy on the locked
  benchmark and on Axis 3)

This is the contract's core claim: **if the intent classifier is correct, the
downstream deterministic contract is reliable.** The System D sequence
(D1 → D2 → D3 → D4 → D-Final) is therefore the right investment: fix the
intent classifier first; everything downstream follows.

---

## 7. Draft thesis paragraph (pivot framing)

> "Stage A's sufficiency predictor established that payload adequacy is
> claim-family-dependent: a plan sufficient for a cost query may be
> insufficient for a lateness query. But the predictor could not tell
> the operator which specific fields they needed, what was missing, or
> what the copilot should do next. The Stage A closing experiment's
> generator-ceiling finding reinforced this limitation: when the generator
> produced correct or gracefully-refused answers even on insufficient cells,
> the pre-registered sufficiency signal could not emerge.
>
> Run 2 re-frames the research question from 'is the payload sufficient for
> a family?' to 'can the copilot recognise what claim is being made,
> determine whether the payload contains the required state, and emit the
> correct evidence-backed product behaviour?' This shift from backend action
> adequacy to product contract correctness places the evaluation at the level
> of the operator-facing API response rather than the solver action underneath
> it. The same three axes — faithfulness (evidence precision), sufficiency
> (evidence and missing-field recall), and operational validity (intent,
> answerability, behavior class) — are preserved, but now evaluated against
> structured contract outputs rather than judge-graded answer text."
