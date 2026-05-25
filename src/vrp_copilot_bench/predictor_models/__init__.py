"""Learned cheap-action sufficiency predictors (Stage A, per claim family).

Trains binary classifiers for ``P(cheap_sufficient | features, claim_family)``
on the locked Stage A long table, reusing the predictor-baseline fold
assignments and gate-vs-route metric machinery. The public entry point is
:func:`run_predictor_models`.

Feature sets:

- **A** — categorical / block only (perturbation_family, perturbation_magnitude,
  cheap_action, instance_class).
- **B** — A + pre-cheap instance and perturbation diagnostics.
- **C** — B + post-cheap action diagnostics (feasibility, deltas, time-warp).

No reference-derived, loss-derived, band-derived, or escalation-action
features may enter any feature set; see :data:`LEAKAGE_COLUMNS` in
:mod:`.features`.
"""
from .features import (
    FEATURE_SETS,
    LEAKAGE_COLUMNS,
    build_feature_matrix,
    perturbation_magnitude,
)
from .models import MODEL_NAMES, make_model
from .runner import run_predictor_models

__all__ = [
    "FEATURE_SETS",
    "LEAKAGE_COLUMNS",
    "MODEL_NAMES",
    "build_feature_matrix",
    "make_model",
    "perturbation_magnitude",
    "run_predictor_models",
]
