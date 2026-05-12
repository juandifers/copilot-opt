"""Tests for the Phase 2 difficulty-band classifier.

The label spec:
    easy   := |gap| < 0.05 AND ari > 0.75
    medium := gap in [0.05, 0.15] OR ari in [0.50, 0.75]
    hard   := |gap| > 0.15 OR ari < 0.50
"""
from __future__ import annotations

from vrpbench.experiments.phase2 import _difficulty_label


def test_easy_low_gap_high_ari():
    assert _difficulty_label(objective_gap_rel=0.01, ari=0.9) == "easy"


def test_hard_large_gap():
    assert _difficulty_label(objective_gap_rel=0.35, ari=0.8) == "hard"


def test_hard_low_ari():
    assert _difficulty_label(objective_gap_rel=0.02, ari=0.1) == "hard"


def test_medium_moderate_gap():
    assert _difficulty_label(objective_gap_rel=0.10, ari=0.8) == "medium"


def test_medium_moderate_ari():
    assert _difficulty_label(objective_gap_rel=0.02, ari=0.60) == "medium"


def test_none_inputs_yield_none():
    assert _difficulty_label(objective_gap_rel=None, ari=None) is None


def test_negative_gap_absolute_value_used():
    assert _difficulty_label(objective_gap_rel=-0.30, ari=0.9) == "hard"
