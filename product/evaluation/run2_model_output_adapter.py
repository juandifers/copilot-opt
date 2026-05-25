"""Parse model contract JSON into a PredictedContract.

The model is instructed to return JSON only (no markdown). Real models
violate this from time to time, so the adapter:

- Strips surrounding ```json ... ``` fences and records the strip in
  `parser_notes` (no silent reformatting beyond the fence).
- Requires every required key to be present (we do NOT default-fill
  missing required keys; the case is marked `missing_required_fields`).
- Validates list fields are lists of strings.
- Validates each enum value is allowed (intent, answerability, behavior
  class, warnings, next actions). Invalid values trigger
  `parse_status = "invalid_enum"` and the offending values are
  recorded in `parser_notes`. We do NOT silently coerce.
- Normalises evidence and missing-field paths using the existing
  scoring normaliser so predicate-pinned paths from the model match
  the field-family gold (`run2_scoring.normalize_field_path`).
- Maps any concrete next-action strings the model might emit (in case
  it ignored the "semantic codes" instruction) back to semantic codes
  via the existing scoring helper.

The adapter never raises on bad input; it always returns a result with
`parse_status` set so the runner can keep going.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from product.evaluation.run2_model_prompts import (
    ALLOWED_ANSWERABILITY,
    ALLOWED_BEHAVIOR_CLASSES,
    ALLOWED_INTENTS,
    ALLOWED_NEXT_ACTIONS,
    ALLOWED_WARNINGS,
)
from product.evaluation.run2_scoring import (
    _to_semantic_action,
    normalize_field_path,
)
from product.evaluation.run2_system_c import PredictedContract


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


PARSE_STATUSES: tuple[str, ...] = (
    "parsed",
    "invalid_json",
    "missing_required_fields",
    "invalid_enum",
    "error",
)


@dataclass
class ParsedModelOutput:
    """Wrapper around a parsed model output plus parse-status metadata.

    `predicted` is None when parsing failed badly enough that no
    `PredictedContract` could be assembled (invalid JSON / missing
    required fields). When `parse_status == "invalid_enum"` we still
    populate `predicted` so the scorer can grade what it can; the
    invalid values are recorded in `parser_notes`.

    System A outputs additionally carry `prior_disagreement` (bool) and
    `adapter_notes` (str) — both optional. For System B outputs these
    default to False and "" respectively and the parser does not
    require their presence.
    """

    case_id: str
    parse_status: str
    parser_notes: list[str] = field(default_factory=list)
    predicted: Optional[PredictedContract] = None
    raw_text: str = ""
    answer_text: str = ""
    prior_disagreement: bool = False
    adapter_notes: str = ""


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_fence(raw_text: str) -> tuple[str, Optional[str]]:
    """If the model wrapped its JSON in a ``` fence, strip it and note it."""
    m = _FENCE_RE.match(raw_text.strip())
    if m:
        return m.group(1), "stripped_markdown_fence"
    return raw_text, None


def _try_parse_json(raw_text: str) -> tuple[Optional[dict], list[str]]:
    notes: list[str] = []
    stripped, fence_note = _strip_fence(raw_text)
    if fence_note:
        notes.append(fence_note)
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        notes.append(f"json_decode_error: {exc.msg} (line {exc.lineno})")
        return None, notes
    if not isinstance(obj, dict):
        notes.append(f"root is {type(obj).__name__}, expected object")
        return None, notes
    return obj, notes


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


_REQUIRED_KEYS: tuple[str, ...] = (
    "predicted_intent",
    "predicted_answerability",
    "predicted_evidence_paths",
    "predicted_missing_fields",
    "predicted_warnings",
    "predicted_next_actions",
    "predicted_behavior_class",
)


def _coerce_str_list(value: Any, key: str, notes: list[str]) -> list[str]:
    if value is None:
        notes.append(f"{key}: null coerced to []")
        return []
    if isinstance(value, str):
        # Some models emit a single semi-separated string; we accept it.
        if ";" in value:
            notes.append(
                f"{key}: string with ';' coerced to list (model violated array shape)"
            )
            return [item.strip() for item in value.split(";") if item.strip()]
        if not value.strip():
            return []
        notes.append(f"{key}: single string coerced to single-item list")
        return [value.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item.strip())
            else:
                notes.append(
                    f"{key}: non-string item {item!r} dropped"
                )
        return out
    notes.append(f"{key}: expected list, got {type(value).__name__}; dropped")
    return []


def _validate_enum(
    value: str, allowed: list[str], key: str
) -> tuple[bool, Optional[str]]:
    if value in allowed:
        return True, None
    return False, f"{key}: invalid value {value!r}"


def _validate_enum_list(
    values: list[str], allowed: list[str], key: str
) -> list[str]:
    bad = [v for v in values if v not in allowed]
    if not bad:
        return []
    return [f"{key}: invalid items {bad!r}"]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_model_contract_json(
    raw_text: str, case_id: str = ""
) -> ParsedModelOutput:
    """Parse one model response into a `ParsedModelOutput`.

    The function never raises; failures land on `parse_status`. Callers
    typically write the resulting object to `parsed.jsonl` and feed
    those rows back through `run2_scoring.score_case` when scoring.
    """
    obj, json_notes = _try_parse_json(raw_text)
    if obj is None:
        return ParsedModelOutput(
            case_id=case_id,
            parse_status="invalid_json",
            parser_notes=json_notes,
            raw_text=raw_text,
        )

    notes = list(json_notes)
    missing = [k for k in _REQUIRED_KEYS if k not in obj]
    if missing:
        notes.append(f"missing_required_keys: {missing}")
        return ParsedModelOutput(
            case_id=case_id,
            parse_status="missing_required_fields",
            parser_notes=notes,
            raw_text=raw_text,
        )

    # --- Scalar enum validation
    intent_raw = obj.get("predicted_intent")
    ans_raw = obj.get("predicted_answerability")
    beh_raw = obj.get("predicted_behavior_class")

    intent = intent_raw if isinstance(intent_raw, str) else ""
    answerability = ans_raw if isinstance(ans_raw, str) else ""
    behavior = beh_raw if isinstance(beh_raw, str) else ""

    enum_errors: list[str] = []
    ok, note = _validate_enum(intent, ALLOWED_INTENTS, "predicted_intent")
    if not ok and note:
        enum_errors.append(note)
    ok, note = _validate_enum(
        answerability, ALLOWED_ANSWERABILITY, "predicted_answerability"
    )
    if not ok and note:
        enum_errors.append(note)
    ok, note = _validate_enum(
        behavior, ALLOWED_BEHAVIOR_CLASSES, "predicted_behavior_class"
    )
    if not ok and note:
        enum_errors.append(note)

    # --- List fields
    evidence_paths_raw = _coerce_str_list(
        obj.get("predicted_evidence_paths"), "predicted_evidence_paths", notes
    )
    missing_fields_raw = _coerce_str_list(
        obj.get("predicted_missing_fields"), "predicted_missing_fields", notes
    )
    warnings_raw = _coerce_str_list(
        obj.get("predicted_warnings"), "predicted_warnings", notes
    )
    next_actions_raw = _coerce_str_list(
        obj.get("predicted_next_actions"), "predicted_next_actions", notes
    )

    enum_errors.extend(
        _validate_enum_list(warnings_raw, ALLOWED_WARNINGS, "predicted_warnings")
    )

    # Map concrete next-action strings back to semantic codes when
    # possible (mirrors run2_scoring.normalize_next_actions). The
    # validator still rejects truly unknown codes.
    next_actions_semantic: list[str] = []
    invalid_next_actions: list[str] = []
    for a in next_actions_raw:
        semantic = _to_semantic_action(a)
        if semantic in ALLOWED_NEXT_ACTIONS:
            next_actions_semantic.append(semantic)
        else:
            invalid_next_actions.append(a)
    if invalid_next_actions:
        enum_errors.append(
            f"predicted_next_actions: invalid items {invalid_next_actions!r}"
        )

    # --- Field paths (always normalised to field-family form)
    evidence_paths = [normalize_field_path(p) for p in evidence_paths_raw]
    missing_fields = [normalize_field_path(p) for p in missing_fields_raw]

    answer_text_val = obj.get("answer_text", "")
    if not isinstance(answer_text_val, str):
        notes.append(
            f"answer_text: expected string, got {type(answer_text_val).__name__}; "
            "coerced to empty"
        )
        answer_text_val = ""

    # System A optional fields. The parser tolerates their absence and
    # records a default-fill note. `prior_disagreement` not affecting
    # scoring is a deliberate R2-6 choice — analysis of disagreement
    # rates lives in the System A report.
    prior_disagreement_val: bool
    if "prior_disagreement" in obj:
        raw_pd = obj["prior_disagreement"]
        if isinstance(raw_pd, bool):
            prior_disagreement_val = raw_pd
        elif isinstance(raw_pd, str) and raw_pd.lower() in {"true", "false"}:
            prior_disagreement_val = raw_pd.lower() == "true"
            notes.append("prior_disagreement: string coerced to bool")
        else:
            notes.append(
                f"prior_disagreement: expected bool, got {type(raw_pd).__name__}; "
                "defaulted to False"
            )
            prior_disagreement_val = False
    else:
        prior_disagreement_val = False

    adapter_notes_val: str
    if "adapter_notes" in obj:
        raw_an = obj["adapter_notes"]
        if isinstance(raw_an, str):
            adapter_notes_val = raw_an
        else:
            notes.append(
                f"adapter_notes: expected str, got {type(raw_an).__name__}; "
                "defaulted to empty"
            )
            adapter_notes_val = ""
    else:
        adapter_notes_val = ""

    predicted = PredictedContract(
        case_id=case_id,
        predicted_intent=intent,
        predicted_answerability=answerability,
        predicted_evidence_paths=evidence_paths,
        predicted_missing_fields=missing_fields,
        predicted_warnings=warnings_raw,
        predicted_next_actions=next_actions_semantic,
        predicted_behavior_class=behavior,
        notes=[],
    )

    if enum_errors:
        notes.extend(enum_errors)
        return ParsedModelOutput(
            case_id=case_id,
            parse_status="invalid_enum",
            parser_notes=notes,
            predicted=predicted,
            raw_text=raw_text,
            answer_text=answer_text_val,
            prior_disagreement=prior_disagreement_val,
            adapter_notes=adapter_notes_val,
        )

    return ParsedModelOutput(
        case_id=case_id,
        parse_status="parsed",
        parser_notes=notes,
        predicted=predicted,
        raw_text=raw_text,
        answer_text=answer_text_val,
        prior_disagreement=prior_disagreement_val,
        adapter_notes=adapter_notes_val,
    )


# ---------------------------------------------------------------------------
# Serialisation helpers (runner writes parsed.jsonl rows)
# ---------------------------------------------------------------------------


def parsed_output_to_dict(parsed: ParsedModelOutput) -> dict:
    """Return a JSON-serialisable dict for one parsed.jsonl row."""
    pred = parsed.predicted
    return {
        "case_id": parsed.case_id,
        "parse_status": parsed.parse_status,
        "parser_notes": parsed.parser_notes,
        "predicted_intent": pred.predicted_intent if pred else "",
        "predicted_answerability": pred.predicted_answerability if pred else "",
        "predicted_evidence_paths": pred.predicted_evidence_paths if pred else [],
        "predicted_missing_fields": pred.predicted_missing_fields if pred else [],
        "predicted_warnings": pred.predicted_warnings if pred else [],
        "predicted_next_actions": pred.predicted_next_actions if pred else [],
        "predicted_behavior_class": pred.predicted_behavior_class if pred else "",
        "answer_text": parsed.answer_text,
        "prior_disagreement": parsed.prior_disagreement,
        "adapter_notes": parsed.adapter_notes,
    }


def parsed_output_from_dict(row: dict) -> ParsedModelOutput:
    """Reconstruct a ParsedModelOutput from a parsed.jsonl row."""
    pred: Optional[PredictedContract] = None
    if row.get("predicted_intent") or row.get("predicted_answerability"):
        pred = PredictedContract(
            case_id=row.get("case_id", ""),
            predicted_intent=row.get("predicted_intent", ""),
            predicted_answerability=row.get("predicted_answerability", ""),
            predicted_evidence_paths=list(row.get("predicted_evidence_paths", [])),
            predicted_missing_fields=list(row.get("predicted_missing_fields", [])),
            predicted_warnings=list(row.get("predicted_warnings", [])),
            predicted_next_actions=list(row.get("predicted_next_actions", [])),
            predicted_behavior_class=row.get("predicted_behavior_class", ""),
        )
    return ParsedModelOutput(
        case_id=row.get("case_id", ""),
        parse_status=row.get("parse_status", "error"),
        parser_notes=list(row.get("parser_notes", [])),
        predicted=pred,
        answer_text=row.get("answer_text", ""),
        prior_disagreement=bool(row.get("prior_disagreement", False)),
        adapter_notes=row.get("adapter_notes", ""),
    )


__all__ = [
    "ParsedModelOutput",
    "PARSE_STATUSES",
    "parse_model_contract_json",
    "parsed_output_to_dict",
    "parsed_output_from_dict",
]
