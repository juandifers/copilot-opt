"""Stage 1 loaders for Run 1 artifacts.

Pure file I/O over locked CSV / JSONL inputs. No inference and no business
logic — every function either reads a file from disk or shapes the read
result into a plain dict / DataFrame. Inference about answer types,
evidence, missing fields, and refusal policy lives in `product.copilot`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

_REPO_ROOT_MARKERS = ("CLAUDE.md", "pyproject.toml")


def repo_root() -> Path:
    """Locate the repository root by walking up from this file."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if any((candidate / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return candidate
    raise RuntimeError(
        f"could not locate repo root from {here}; expected one of "
        f"{_REPO_ROOT_MARKERS} above this file"
    )


def _normalize_prompt_id(value: Any) -> str:
    """Coerce a prompt id to a stable string form (zero-padded if numeric)."""
    s = str(value).strip()
    if s.isdigit():
        return s.zfill(3)
    return s


def _joined_path(run_id: str) -> Path:
    return repo_root() / "experiment" / "results" / "joined" / f"{run_id}.csv"


def _generator_jsonl_path(run_id: str) -> Path:
    return repo_root() / "experiment" / "results" / "generator" / f"{run_id}.jsonl"


def _judge_jsonl_path(run_id: str) -> Path:
    return repo_root() / "experiment" / "results" / "judge" / f"{run_id}.jsonl"


def _prompts_path() -> Path:
    return repo_root() / "experiment" / "data" / "prompts.csv"


@lru_cache(maxsize=None)
def load_joined_results(run_id: str = "full-run-v1") -> pd.DataFrame:
    """Load experiment/results/joined/{run_id}.csv with prompt_id forced to str."""
    df = pd.read_csv(_joined_path(run_id), dtype={"prompt_id": str})
    df["prompt_id"] = df["prompt_id"].map(_normalize_prompt_id)
    return df


@lru_cache(maxsize=None)
def load_prompts() -> pd.DataFrame:
    """Load experiment/data/prompts.csv with prompt_id forced to str."""
    df = pd.read_csv(_prompts_path(), dtype={"prompt_id": str})
    df["prompt_id"] = df["prompt_id"].map(_normalize_prompt_id)
    return df


def load_jsonl(path: Path) -> list[dict]:
    """Generic JSONL loader; returns one dict per non-empty line."""
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                out.append(json.loads(stripped))
    return out


@lru_cache(maxsize=None)
def load_generator_records(run_id: str = "full-run-v1") -> dict[str, dict]:
    return {
        _normalize_prompt_id(rec.get("prompt_id")): rec
        for rec in load_jsonl(_generator_jsonl_path(run_id))
    }


@lru_cache(maxsize=None)
def load_judge_records(run_id: str = "full-run-v1") -> dict[str, dict]:
    return {
        _normalize_prompt_id(rec.get("prompt_id")): rec
        for rec in load_jsonl(_judge_jsonl_path(run_id))
    }


def _row_to_native(row: pd.Series) -> dict:
    """Convert a pandas row to a JSON-safe dict (NaN → None, numpy → native)."""
    return json.loads(row.to_json())


def joined_records(run_id: str = "full-run-v1") -> list[dict]:
    """Joined results as a list of native dicts (for HTTP responses)."""
    df = load_joined_results(run_id)
    return json.loads(df.to_json(orient="records"))


def load_prompt_bundle(prompt_id: str, run_id: str = "full-run-v1") -> dict:
    """Return all artifacts for one prompt: joined row, prompt row, generator
    record, judge record. Missing JSONL records are reported in `warnings`
    rather than raised; a missing joined-CSV row raises KeyError (the prompt
    does not exist in this run)."""
    pid = _normalize_prompt_id(prompt_id)
    warnings: list[str] = []

    joined = load_joined_results(run_id)
    joined_match = joined[joined["prompt_id"] == pid]
    if joined_match.empty:
        raise KeyError(f"prompt_id {pid!r} not found in joined results for run {run_id!r}")
    joined_row = _row_to_native(joined_match.iloc[0])

    prompts = load_prompts()
    prompts_match = prompts[prompts["prompt_id"] == pid]
    if prompts_match.empty:
        warnings.append(f"prompt_id {pid!r} not found in experiment/data/prompts.csv")
        prompt_row: dict | None = None
    else:
        prompt_row = _row_to_native(prompts_match.iloc[0])

    generator_record = load_generator_records(run_id).get(pid)
    if generator_record is None:
        warnings.append(f"generator record missing for prompt_id {pid!r} in run {run_id!r}")

    judge_record = load_judge_records(run_id).get(pid)
    if judge_record is None:
        warnings.append(f"judge record missing for prompt_id {pid!r} in run {run_id!r}")

    return {
        "run_id": run_id,
        "prompt_id": pid,
        "joined_row": joined_row,
        "prompt_row": prompt_row,
        "generator_record": generator_record,
        "judge_record": judge_record,
        "warnings": warnings,
    }
