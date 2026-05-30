"""Payload materialization for Run 2 calibration cases.

For each Run 2 case, produce the deterministic payload the System C
contract should evaluate. Seed payloads come from Run 1's
`experiment/results_RUN1/generator/{run_id}.jsonl` (the locked
`payload_snapshot` field on each generator record); per-case mutations
are applied on a deep copy.

Design constraints:
- No solver calls.
- No locked experiment files modified.
- No mutation of the seed dict — every mutation runs on a deep copy.
- If `source_prompt_id` is empty AND the case's
  `payload_mutation_needed` text does not unambiguously name exactly
  one Run 1 prompt, the case is `skipped_no_seed`. Run 2 must stay
  reproducible; we do not guess.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from product.evaluation.run2_case_loader import Run2Case


# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------


# Repo-root markers, in preference order. pyproject.toml is the canonical,
# always-committed root file; CLAUDE.md is kept as a fallback but is not
# shipped in the public checkout, so it must not be the sole marker.
_REPO_ROOT_MARKERS = ("pyproject.toml", "CLAUDE.md")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if any((parent / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return parent
    raise RuntimeError(f"could not locate repo root from {here}")


def _candidate_generator_paths(run_id: str) -> list[Path]:
    root = _repo_root()
    return [
        root / "experiment" / "results" / "generator" / f"{run_id}.jsonl",
        root / "experiment" / "results_RUN1" / "generator" / f"{run_id}.jsonl",
    ]


def _find_generator_jsonl(run_id: str) -> Path:
    for p in _candidate_generator_paths(run_id):
        if p.exists():
            return p
    raise FileNotFoundError(
        f"no generator JSONL for run_id={run_id!r}; tried "
        f"{[str(p) for p in _candidate_generator_paths(run_id)]}"
    )


# ---------------------------------------------------------------------------
# Seed payload index
# ---------------------------------------------------------------------------


def _normalize_prompt_id(pid: Any) -> str:
    s = str(pid).strip()
    return s.zfill(3) if s.isdigit() else s


@lru_cache(maxsize=4)
def _load_generator_records(run_id: str) -> dict[str, dict]:
    """Read the run's generator JSONL into a {prompt_id: record} dict."""
    path = _find_generator_jsonl(run_id)
    out: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            rec = json.loads(stripped)
            pid = _normalize_prompt_id(rec.get("prompt_id"))
            out[pid] = rec
    return out


def load_seed_payload(
    source_prompt_id: str, run_id: str = "full-run-v1"
) -> Optional[dict]:
    """Return the locked Run 1 payload_snapshot for the given prompt, or None.

    Returns None if either the prompt is unknown to this run, the
    generator record lacks a payload_snapshot, or the field is not a
    dict. Errors that would otherwise be silent are surfaced by the
    materializer via a non-`materialized` status.
    """
    if not source_prompt_id:
        return None
    pid = _normalize_prompt_id(source_prompt_id)
    rec = _load_generator_records(run_id).get(pid)
    if not rec:
        return None
    payload = rec.get("payload_snapshot")
    return payload if isinstance(payload, dict) else None


def load_seed_generator_record(
    source_prompt_id: str, run_id: str = "full-run-v1"
) -> Optional[dict]:
    """Return the full generator record (used by System C for
    structured_output / answer_text), or None if unknown."""
    if not source_prompt_id:
        return None
    pid = _normalize_prompt_id(source_prompt_id)
    return _load_generator_records(run_id).get(pid)


# ---------------------------------------------------------------------------
# Deterministic payload mutations (schema §2)
# ---------------------------------------------------------------------------


def _drop_key(d: dict, key: str) -> bool:
    if key in d:
        d.pop(key)
        return True
    return False


def _drop_keys_recursive(d: Any, keys: set[str]) -> int:
    """Recurse into dicts/lists removing any occurrence of `keys`.

    Returns the number of removals performed.
    """
    removed = 0
    if isinstance(d, dict):
        for k in list(d.keys()):
            if k in keys:
                d.pop(k)
                removed += 1
            else:
                removed += _drop_keys_recursive(d[k], keys)
    elif isinstance(d, list):
        for item in d:
            removed += _drop_keys_recursive(item, keys)
    return removed


def _apply_mutation(payload: dict, condition: str) -> tuple[dict, list[str]]:
    """Apply the schema §2 mutation matching `condition` to a deep copy."""
    mutated = copy.deepcopy(payload)
    warnings: list[str] = []

    if condition in {
        "clean",
        "convention_boundary",
        "same_route_boolean",
        "full_route_membership",
        "single_customer_membership",
        "false_premise_customer",
        "false_premise_route",
        "missing_reference_solution",
    }:
        # No-ops by definition: either the condition is a property of
        # the prompt text or the field is already absent in Run 1
        # payloads.
        if condition == "missing_reference_solution" and "reference_solution" in mutated:
            warnings.append(
                "reference_solution unexpectedly present in seed payload; "
                "removing for missing_reference_solution"
            )
            mutated.pop("reference_solution")
        return mutated, warnings

    if condition == "missing_new_customer_ids":
        # Remove any new_customer_ids appearing top-level OR nested.
        n = _drop_keys_recursive(mutated, {"new_customer_ids"})
        if n == 0:
            # Run 1 STRUCT payloads do not carry this key — the
            # mutation is structurally a no-op. Record the fact so
            # the report is honest about it.
            warnings.append(
                "new_customer_ids was not present in the seed payload "
                "(mutation is structurally a no-op for this seed)"
            )
        return mutated, warnings

    if condition == "unsupported_comparison":
        removed = 0
        for k in ("baseline_solution", "diff"):
            if _drop_key(mutated, k):
                removed += 1
        if removed == 0:
            warnings.append(
                "neither baseline_solution nor diff was present in seed "
                "(mutation is structurally a no-op)"
            )
        return mutated, warnings

    if condition == "missing_baseline_solution":
        removed = 0
        for k in ("baseline_solution", "diff"):
            if _drop_key(mutated, k):
                removed += 1
        if removed == 0:
            warnings.append(
                "baseline_solution/diff were not present in seed "
                "(mutation is structurally a no-op)"
            )
        return mutated, warnings

    if condition == "missing_units":
        # OBJ payloads carry `units` as a nested dict with key `objective`.
        units = mutated.get("units")
        if isinstance(units, dict) and "objective" in units:
            units.pop("objective")
            if not units:
                mutated.pop("units")
        else:
            warnings.append(
                "units.objective was not present in seed; mutation no-op"
            )
        return mutated, warnings

    if condition == "missing_validity_fields":
        removed = 0
        for k in ("feasible", "feasibility_breakdown"):
            if _drop_key(mutated, k):
                removed += 1
        if removed == 0:
            warnings.append(
                "feasible/feasibility_breakdown were not present in seed; "
                "mutation no-op"
            )
        return mutated, warnings

    # Unknown condition — defensive
    warnings.append(f"unsupported payload_condition: {condition!r}")
    return mutated, warnings


# ---------------------------------------------------------------------------
# Implicit-seed resolution
# ---------------------------------------------------------------------------


_PROMPT_REF_RE = re.compile(r"\bprompt\s+(\d{3})\b", re.IGNORECASE)


def _candidate_seed_ids_from_rationale(text: str) -> list[str]:
    """Extract zero or more `prompt NNN` references from rationale text.

    Used only when `source_prompt_id` is empty: a case's
    `payload_mutation_needed` may name the seed unambiguously
    ("Synthetic case derived from prompt 046's seed payload"). If the
    text names exactly one Run 1 prompt, we accept it as the seed; if
    it names zero or multiple, the case is `skipped_no_seed` per the
    materializer contract.
    """
    if not text:
        return []
    return [m.group(1) for m in _PROMPT_REF_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class MaterializedPayload:
    case_id: str
    payload: Optional[dict]
    source_prompt_id: str  # the prompt_id actually used (may differ from CSV cell)
    materialization_status: str  # materialized | skipped_no_seed |
    #                              skipped_unsupported_mutation | error
    warnings: list[str] = field(default_factory=list)
    # Generator record for the seed prompt, if any — System C needs
    # `structured_output` for claim-aware evidence extraction.
    generator_record: Optional[dict] = None


@dataclass
class MaterializationSummary:
    counts: dict[str, int]
    by_case: dict[str, str]
    skipped_no_seed_cases: list[str]
    skipped_unsupported_mutation_cases: list[str]
    error_cases: list[str]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _resolve_seed(case: Run2Case) -> tuple[str, str]:
    """Return (resolved_prompt_id, source_label).

    `source_label` is one of `csv` (taken from source_prompt_id),
    `rationale_unique` (extracted from payload_mutation_needed when
    that field names exactly one prompt), or `none` (no seed
    resolvable).
    """
    if case.source_prompt_id:
        return _normalize_prompt_id(case.source_prompt_id), "csv"

    candidates = _candidate_seed_ids_from_rationale(case.payload_mutation_needed)
    unique = sorted(set(candidates))
    if len(unique) == 1:
        return _normalize_prompt_id(unique[0]), "rationale_unique"

    return "", "none"


def materialize_case_payload(
    case: Run2Case,
    run_id: str = "full-run-v1",
) -> MaterializedPayload:
    """Materialize one case's payload deterministically.

    Resolution rules:
    1. If `case.source_prompt_id` is set, load the seed from that
       Run 1 prompt's `payload_snapshot`.
    2. If empty AND `payload_mutation_needed` names exactly one
       Run 1 prompt (regex `prompt \\d{3}`), use that prompt as the
       seed. The materializer never silently guesses outside of this
       narrow pattern.
    3. Otherwise return `skipped_no_seed`.

    The mutation in `case.payload_condition` is applied on a deep
    copy. The seed dict is never mutated.
    """
    resolved_pid, source_label = _resolve_seed(case)
    if not resolved_pid:
        return MaterializedPayload(
            case_id=case.case_id,
            payload=None,
            source_prompt_id="",
            materialization_status="skipped_no_seed",
            warnings=[
                "no source_prompt_id; payload_mutation_needed does not name "
                "exactly one Run 1 prompt — add source_prompt_id to the CSV"
            ],
        )

    try:
        seed = load_seed_payload(resolved_pid, run_id=run_id)
        gen_rec = load_seed_generator_record(resolved_pid, run_id=run_id)
    except FileNotFoundError as exc:
        return MaterializedPayload(
            case_id=case.case_id,
            payload=None,
            source_prompt_id=resolved_pid,
            materialization_status="error",
            warnings=[str(exc)],
        )

    if seed is None:
        return MaterializedPayload(
            case_id=case.case_id,
            payload=None,
            source_prompt_id=resolved_pid,
            materialization_status="error",
            warnings=[
                f"seed prompt {resolved_pid!r} has no payload_snapshot "
                f"in run {run_id!r}"
            ],
        )

    warnings: list[str] = []
    if source_label == "rationale_unique":
        warnings.append(
            f"seed inferred from payload_mutation_needed text (prompt "
            f"{resolved_pid!r}); recommend adding source_prompt_id to the CSV"
        )

    payload, mutation_warnings = _apply_mutation(seed, case.payload_condition)
    warnings.extend(mutation_warnings)

    return MaterializedPayload(
        case_id=case.case_id,
        payload=payload,
        source_prompt_id=resolved_pid,
        materialization_status="materialized",
        warnings=warnings,
        generator_record=gen_rec,
    )


def materialize_all_cases(
    cases: Iterable[Run2Case], run_id: str = "full-run-v1"
) -> tuple[list[MaterializedPayload], MaterializationSummary]:
    materialized: list[MaterializedPayload] = []
    counts: dict[str, int] = {
        "materialized": 0,
        "skipped_no_seed": 0,
        "skipped_unsupported_mutation": 0,
        "error": 0,
    }
    by_case: dict[str, str] = {}
    skipped_no_seed: list[str] = []
    skipped_unsupported: list[str] = []
    error_cases: list[str] = []

    for case in cases:
        m = materialize_case_payload(case, run_id=run_id)
        materialized.append(m)
        counts[m.materialization_status] = counts.get(m.materialization_status, 0) + 1
        by_case[case.case_id] = m.materialization_status
        if m.materialization_status == "skipped_no_seed":
            skipped_no_seed.append(case.case_id)
        elif m.materialization_status == "skipped_unsupported_mutation":
            skipped_unsupported.append(case.case_id)
        elif m.materialization_status == "error":
            error_cases.append(case.case_id)

    recommendations: list[str] = []
    if skipped_no_seed:
        recommendations.append(
            f"{len(skipped_no_seed)} case(s) have no resolvable seed: "
            f"{skipped_no_seed}. Add source_prompt_id to the CSV before "
            f"running the evaluator on these rows."
        )
    if error_cases:
        recommendations.append(
            f"{len(error_cases)} case(s) errored during materialization: "
            f"{error_cases}. Inspect the per-case warnings."
        )

    summary = MaterializationSummary(
        counts=counts,
        by_case=by_case,
        skipped_no_seed_cases=skipped_no_seed,
        skipped_unsupported_mutation_cases=skipped_unsupported,
        error_cases=error_cases,
        recommendations=recommendations,
    )
    return materialized, summary
