"""Unit tests for op_validity check functions.

Pure-function tests. No API calls; runs in well under a second.

The smoke test (smoke_test.py) invokes these before any API call so a
broken check function aborts the run before consuming Max-plan quota.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from op_validity import (  # noqa: E402
    REFUSAL_PHRASE,
    check_obj,
    check_pv,
    check_schedule,
    check_struct,
    detect_refusal,
)


def _gen(answer_text="An answer.", **claims) -> dict:
    """Build a generator-output dict with all claim fields nulled by default."""
    base = {
        "answer_text": answer_text,
        "claimed_objective": None,
        "claimed_feasible": None,
        "claimed_route_count": None,
        "claimed_route_membership": None,
        "claimed_late_customers": None,
        "claimed_customer_timings": None,
    }
    base.update(claims)
    return base


# ---------------------------------------------------------------------------
# Refusal detection


class TestRefusalDetection(unittest.TestCase):
    def test_canonical_phrase_lower(self):
        self.assertTrue(detect_refusal(
            "The data does not contain this information about route 5."))

    def test_no_refusal(self):
        self.assertFalse(detect_refusal("Total cost is 934.3."))

    def test_empty_string(self):
        self.assertFalse(detect_refusal(""))

    def test_phrase_constant_matches_rubric(self):
        # Anchor: if the locked rubric phrase ever drifts we want CI to flag.
        self.assertEqual(REFUSAL_PHRASE, "the data does not contain this information")


# ---------------------------------------------------------------------------
# OBJ


class TestObj(unittest.TestCase):
    payload = {
        "units": {"objective": "solomon_distance"},
        "action_objective": 1000.00,
        "baseline_objective": 900.00,
        "objective_delta_absolute": 100.00,
        "objective_delta_percent": 11.11,
    }

    def test_exact_match(self):
        r = check_obj(_gen(claimed_objective=1000.00), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["objective_within_0_5_pct"])
        self.assertFalse(r["refusal_detected"])

    def test_within_tolerance(self):
        # 0.5% of 1000 = 5.0, so 1004.99 is within
        r = check_obj(_gen(claimed_objective=1004.99), self.payload, True)
        self.assertTrue(r["op_validity_pass"])

    def test_just_outside_tolerance(self):
        # 1005.01 → rel err 0.00501 > 0.005
        r = check_obj(_gen(claimed_objective=1005.01), self.payload, True)
        self.assertFalse(r["op_validity_pass"])
        self.assertFalse(r["op_validity_check_results"]["objective_within_0_5_pct"])

    def test_null_when_gradable_returns_false(self):
        # Rubric §b: null claim where headline required = fail (not null).
        r = check_obj(_gen(claimed_objective=None), self.payload, True)
        self.assertFalse(r["op_validity_pass"])

    def test_non_gradable_returns_null(self):
        # Rubric §c: non-headline non-refusal answers → op_validity null.
        r = check_obj(_gen(claimed_objective=None), self.payload, False)
        self.assertIsNone(r["op_validity_pass"])
        self.assertIsNone(r["op_validity_check_results"])
        self.assertFalse(r["refusal_detected"])

    def test_refusal_returns_null_with_flag(self):
        r = check_obj(_gen(answer_text="The data does not contain this information."),
                      self.payload, True)
        self.assertIsNone(r["op_validity_pass"])
        self.assertIsNone(r["op_validity_check_results"])
        self.assertTrue(r["refusal_detected"])


# ---------------------------------------------------------------------------
# PV


class TestPv(unittest.TestCase):
    payload_infeasible = {
        "feasible": False,
        "feasibility_breakdown": {"capacity_ok": True, "time_windows_ok": False, "coverage_ok": True},
        "infeasibility_kind": "time_window",
        "n_unserved_customers": 0,
        "unserved_customer_ids": [],
    }
    payload_feasible = {
        "feasible": True,
        "feasibility_breakdown": {"capacity_ok": True, "time_windows_ok": True, "coverage_ok": True},
        "infeasibility_kind": "none",
        "n_unserved_customers": 0,
        "unserved_customer_ids": [],
    }

    def test_exact_match_true(self):
        r = check_pv(_gen(claimed_feasible=True), self.payload_feasible, True)
        self.assertTrue(r["op_validity_pass"])

    def test_exact_match_false(self):
        r = check_pv(_gen(claimed_feasible=False), self.payload_infeasible, True)
        self.assertTrue(r["op_validity_pass"])

    def test_mismatch(self):
        r = check_pv(_gen(claimed_feasible=True), self.payload_infeasible, True)
        self.assertFalse(r["op_validity_pass"])

    def test_null_when_gradable_returns_false(self):
        r = check_pv(_gen(claimed_feasible=None), self.payload_feasible, True)
        self.assertFalse(r["op_validity_pass"])

    def test_non_gradable_returns_null(self):
        # Sub-feasibility / coverage sub-claims (e.g., capacity-specific
        # prompts) are op_validity_gradable=False.
        r = check_pv(_gen(claimed_feasible=None), self.payload_feasible, False)
        self.assertIsNone(r["op_validity_pass"])

    def test_refusal_returns_null(self):
        r = check_pv(_gen(answer_text="The data does not contain this information."),
                     self.payload_feasible, True)
        self.assertIsNone(r["op_validity_pass"])
        self.assertTrue(r["refusal_detected"])


# ---------------------------------------------------------------------------
# STRUCT


class TestStruct(unittest.TestCase):
    payload = {
        "n_routes": 3,
        "routes": [
            {"route_idx": 0, "customer_ids": [12, 17, 42]},
            {"route_idx": 1, "customer_ids": [5, 9, 11]},
            {"route_idx": 2, "customer_ids": [101, 77, 79]},
        ],
    }

    def test_route_count_exact(self):
        r = check_struct(_gen(claimed_route_count=3), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["route_count_exact"])

    def test_route_count_off_by_one(self):
        r = check_struct(_gen(claimed_route_count=2), self.payload, True)
        self.assertFalse(r["op_validity_pass"])
        self.assertFalse(r["op_validity_check_results"]["route_count_exact"])

    def test_single_customer_membership_subset_ok(self):
        # STRUCT-2: "which route is customer 42 on" → claim {route_idx: 0, customer_ids: [42]}
        r = check_struct(_gen(claimed_route_membership=[
            {"route_idx": 0, "customer_ids": [42]}
        ]), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["membership_set_equal"])

    def test_single_customer_membership_wrong_route(self):
        # Customer 42 is actually on route 0, not route 1.
        r = check_struct(_gen(claimed_route_membership=[
            {"route_idx": 1, "customer_ids": [42]}
        ]), self.payload, True)
        self.assertFalse(r["op_validity_pass"])

    def test_same_route_boolean_true(self):
        # 12 and 17 share route 0 in the payload.
        r = check_struct(_gen(claimed_route_membership=[
            {"route_idx": 0, "customer_ids": [12, 17]}
        ]), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["same_route_boolean"])

    def test_same_route_boolean_false(self):
        # 12 and 11 are on different routes; the answer asserts same — fail.
        r = check_struct(_gen(claimed_route_membership=[
            {"route_idx": 0, "customer_ids": [12, 11]}
        ]), self.payload, True)
        self.assertFalse(r["op_validity_pass"])

    def test_non_gradable_returns_null(self):
        # STRUCT prompts asking outside the extended rubric (e.g.,
        # "did the count change") are flagged op_validity_gradable=False
        # at construction time.
        r = check_struct(_gen(claimed_route_count=None), self.payload, False)
        self.assertIsNone(r["op_validity_pass"])

    def test_refusal_returns_null(self):
        r = check_struct(_gen(answer_text="The data does not contain this information."),
                         self.payload, True)
        self.assertIsNone(r["op_validity_pass"])
        self.assertTrue(r["refusal_detected"])


# ---------------------------------------------------------------------------
# SCHEDULE


class TestSchedule(unittest.TestCase):
    payload = {
        "units": {"time": "solomon_minutes"},
        "n_late_customers": 1,
        "late_customer_ids": [78],
        "route_end_times": [
            {"route_idx": 0, "end_time": 1234.8, "has_time_warp": False},
        ],
        "customer_schedule": [
            {"customer_id": 42, "route_idx": 0,
             "arrival": 100.0, "start_service": 100.0, "end_service": 190.0,
             "tw_early": 60.0, "tw_late": 120.0,
             "is_late": False, "lateness_minutes": 0.0},
            {"customer_id": 78, "route_idx": 0,
             "arrival": 200.0, "start_service": 200.0, "end_service": 290.0,
             "tw_early": 150.0, "tw_late": 195.0,
             "is_late": True, "lateness_minutes": 5.0},
        ],
    }

    def test_arrival_exact(self):
        r = check_schedule(_gen(claimed_customer_timings=[
            {"customer_id": 42, "stated_arrival_or_start": 100.0}
        ]), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["arrival_within_1min"])

    def test_arrival_within_1min(self):
        r = check_schedule(_gen(claimed_customer_timings=[
            {"customer_id": 42, "stated_arrival_or_start": 100.9}
        ]), self.payload, True)
        self.assertTrue(r["op_validity_pass"])

    def test_arrival_just_outside_1min(self):
        r = check_schedule(_gen(claimed_customer_timings=[
            {"customer_id": 42, "stated_arrival_or_start": 101.1}
        ]), self.payload, True)
        self.assertFalse(r["op_validity_pass"])

    def test_any_late_boolean_true(self):
        # Payload has 1 late customer; saying "yes someone is late" matches.
        r = check_schedule(_gen(claimed_late_customers=[78]), self.payload, True)
        self.assertTrue(r["op_validity_pass"])
        self.assertTrue(r["op_validity_check_results"]["any_late_boolean"])

    def test_any_late_boolean_empty_means_no_late(self):
        # Empty list = "nobody is late". Payload has 1 late → mismatch.
        r = check_schedule(_gen(claimed_late_customers=[]), self.payload, True)
        self.assertFalse(r["op_validity_check_results"]["any_late_boolean"])
        self.assertFalse(r["op_validity_pass"])

    def test_lateness_set_mismatch(self):
        # Says 42 is late, but actually only 78 is.
        r = check_schedule(_gen(claimed_late_customers=[42]), self.payload, True)
        self.assertFalse(r["op_validity_pass"])

    def test_non_gradable_returns_null(self):
        r = check_schedule(_gen(), self.payload, False)
        self.assertIsNone(r["op_validity_pass"])

    def test_refusal_returns_null(self):
        r = check_schedule(_gen(answer_text="The data does not contain this information."),
                           self.payload, True)
        self.assertIsNone(r["op_validity_pass"])
        self.assertTrue(r["refusal_detected"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
