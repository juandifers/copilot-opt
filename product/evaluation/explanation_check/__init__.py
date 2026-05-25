"""Evaluation harness for grounded overview support.

Runs each row of ``explanation_cases.csv`` through the live API
(``POST /copilot/ask``) and scores the response against the gold
expectations in the row. Reports are written under ``reports/``.

This harness is independent of the locked Run 2 suite and the
verbalization-faithfulness check. It evaluates only the new overview
intents (perturbation_summary, scenario_summary, solution_summary,
perturbation_impact_summary, route_impact_summary, what_to_watch).
"""
