"""Payload parsing and field listing for Run 1 artifacts.

The canonical payload for a prompt is stored at `payload_snapshot` on the
generator record (one JSONL line in experiment/results/generator/{run}.jsonl).
This module exposes pure helpers for extracting that payload and enumerating
its useful fields. Inference about *what the payload supports answering*
lives in `product.copilot`, not here.
"""
from __future__ import annotations


def parse_payload_snapshot(generator_record: dict | None) -> dict | None:
    """Return the payload dict from a generator record, or None if absent."""
    if not generator_record:
        return None
    payload = generator_record.get("payload_snapshot")
    return payload if isinstance(payload, dict) else None


def available_payload_fields(payload: dict | None) -> list[str]:
    """Enumerate top-level fields plus one level of useful nested paths.

    For a list-valued field whose items are dicts, emit `key[].nested_key`
    for every key in the first item. For a dict-valued field, emit
    `key.nested_key` for every nested key.

    Returns the fields in insertion order for deterministic display."""
    if not payload:
        return []
    fields: list[str] = []
    for key, value in payload.items():
        fields.append(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            for nested_key in value[0].keys():
                fields.append(f"{key}[].{nested_key}")
        elif isinstance(value, dict):
            for nested_key in value.keys():
                fields.append(f"{key}.{nested_key}")
    return fields
