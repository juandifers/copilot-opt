"""Learned sufficiency gate — Stage A predictor deployed into the D4 path.

The gate is **advisory**. It does not own answerability, evidence
paths, warnings, missing-fields, final answer text, or UI actions. It
feeds a single advisory signal into the D4 compute-decision policy:
*should the current/cheap payload be accepted as sufficient, or should
a bounded recomputation be recommended instead?*

Hard contract checks always win. The gate is consulted only after
D4's deterministic ladder has already cleared:

  - unsupported triggers
  - clarification triggers
  - explicit recompute / comparison / causal framing
  - missing required fields (D2 answerability)
  - partial-answer status

If any of those fire, the gate is not asked. If the gate is asked but
its required features are missing, it returns ``decision="no_decision"``
and D4 falls back to its deterministic behaviour.

Public surface
--------------

* :class:`SufficiencyGateResult` — pydantic decision struct.
* :func:`predict_sufficiency` — pure call that runs the gate.
* :data:`GATE_FLAG_ENV_VAR` — env-var name controlling deployment mode.

Forbidden actions
-----------------

* ``pyvrp_60s`` is **never** recommended — it was the Stage A reference
  oracle, not a deployable rung. The gate's recompute hint always
  resolves to ``run_pyvrp_10s`` (default) or a cheaper deployable rung
  if the caller pins one.
"""
from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

GateDecision = Literal["accept_current", "recommend_recompute", "no_decision"]

#: Env var that enables the learned gate. Default is ``false`` so the
#: clean D-Final baseline is preserved; the ``d_final_gated`` system
#: variant flips this on explicitly.
GATE_FLAG_ENV_VAR: str = "PRODUCT_USE_LEARNED_SUFFICIENCY_GATE"

#: pyvrp_60s was the Stage A label oracle, not a deployable rung. The
#: gate may never recommend it.
FORBIDDEN_RECOMPUTE_ACTIONS: frozenset[str] = frozenset({"pyvrp_60s", "pyvrp_60s_reference"})

#: Families the Stage A predictor is calibrated on.
SUPPORTED_FAMILIES: frozenset[str] = frozenset(
    {"OBJ", "PLAN_VALIDITY", "STRUCT", "SCHEDULE"}
)

#: Default recompute rung recommended when the gate decides the current
#: payload is insufficient. Never pyvrp_60s.
DEFAULT_RECOMPUTE_ACTION: str = "run_pyvrp_10s"


class SufficiencyGateResult(BaseModel):
    """Advisory output from the learned sufficiency gate.

    Carried alongside the deterministic D4 decision so the operator-
    facing surface can show *why* a gate-influenced flip happened (or
    why the gate abstained). The renderer is responsible for keeping
    user-facing wording conservative (the model is a probabilistic
    predictor, not a proof of sufficiency).
    """

    enabled: bool
    family: str
    action: str
    p_sufficient: Optional[float] = None
    threshold: Optional[float] = None
    decision: GateDecision
    model_id: str
    features_used: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    reason: str
    recommended_action: Optional[str] = None
    correctness_floor: Optional[float] = None


# ---------------------------------------------------------------------------
# Deployment-config loader
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DEPLOYMENT_CONFIG = _REPO_ROOT / "reports" / "predictor_models" / "deployment_config.csv"
_DEFAULT_TRAINING_PARQUET = _REPO_ROOT / "data" / "probes" / "escalation_probe_claim_rows.parquet"

# Default correctness floor used when the caller does not pin one.
DEFAULT_CORRECTNESS_FLOOR: float = 0.9


def _is_truthy_flag(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def gate_enabled() -> bool:
    """Return True iff the learned gate is turned on for this process."""
    return _is_truthy_flag(os.environ.get(GATE_FLAG_ENV_VAR))


@lru_cache(maxsize=1)
def _load_deployment_config() -> dict[tuple[str, float], dict[str, Any]]:
    """Parse deployment_config.csv into a ``{(family, floor): row}`` map.

    Falls back to an empty dict if the file is missing — callers must
    treat that as "gate cannot make a decision".
    """
    if not _DEFAULT_DEPLOYMENT_CONFIG.exists():
        logger.warning(
            "deployment_config.csv not found at %s; gate will return no_decision",
            _DEFAULT_DEPLOYMENT_CONFIG,
        )
        return {}
    import csv
    out: dict[tuple[str, float], dict[str, Any]] = {}
    with _DEFAULT_DEPLOYMENT_CONFIG.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                family = row["claim_family"].strip()
                floor = float(row["correctness_floor"])
            except (KeyError, ValueError):
                continue
            # Prefer the "deployment_active" row when multiple rows
            # share the same (family, floor).
            note = (row.get("note") or "").strip().lower()
            existing = out.get((family, floor))
            if existing is not None:
                existing_note = (existing.get("note") or "").strip().lower()
                if existing_note == "deployment_active" and note != "deployment_active":
                    continue
            out[(family, floor)] = row
    return out


def _config_for(family: str, correctness_floor: float) -> Optional[dict[str, Any]]:
    cfg = _load_deployment_config()
    return cfg.get((family, correctness_floor))


# ---------------------------------------------------------------------------
# Model loading / training
#
# Stage A trains models out-of-fold and writes OOF predictions; the
# fitted pipelines themselves are not serialised. For deployment we
# refit the per-family HistGB pipeline on the full training table the
# first time the gate is invoked and cache the resulting pipeline.
# Training is fast (~1s per family) on the parquet, but we still guard
# the load with a lock so concurrent first-calls don't race.
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


def _load_predictor_module():
    """Import the Stage A predictor_models package, injecting ``src/`` if needed."""
    import sys
    src_dir = _REPO_ROOT / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from vrp_copilot_bench.predictor_models import features as pm_features
    from vrp_copilot_bench.predictor_models import models as pm_models
    return pm_features, pm_models


def _train_family_pipeline(family: str):
    """Refit the HistGB / C_clean pipeline for ``family`` on full data.

    Returns ``(pipeline, feature_columns, model_id)`` or ``None`` if the
    training parquet is unavailable.
    """
    if not _DEFAULT_TRAINING_PARQUET.exists():
        logger.warning(
            "training parquet missing at %s; gate cannot fit %s",
            _DEFAULT_TRAINING_PARQUET, family,
        )
        return None
    try:
        import pandas as pd
        pm_features, pm_models = _load_predictor_module()
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate cannot import predictor modules: %r", exc)
        return None

    df = pd.read_parquet(_DEFAULT_TRAINING_PARQUET)
    # ``instance_class`` is derived from the Solomon instance id at load
    # time; the raw parquet does not carry it (see
    # ``predictor_baselines.data.instance_class_from_id``).
    if "instance_class" not in df.columns:
        def _ic(s):
            if not isinstance(s, str):
                return "?"
            if s.startswith("RC"):
                return "RC"
            return s[:1] if s[:1] in {"C", "R"} else "?"
        df = df.copy()
        df["instance_class"] = df["instance_id"].map(_ic)
    fam_df = df[df["claim_family"] == family].copy()
    fam_df = fam_df.dropna(subset=["sufficient_binary"]).reset_index(drop=True)
    if fam_df.empty:
        return None
    try:
        X, num_cols, cat_cols = pm_features.build_feature_matrix(
            fam_df, "C_clean", family,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate cannot build feature matrix for %s: %r", family, exc)
        return None
    y = fam_df["sufficient_binary"].astype(int).to_numpy()
    pipeline = pm_models.make_model(
        "hist_gradient_boosting",
        numeric_columns=num_cols,
        categorical_columns=cat_cols,
    )
    pipeline.fit(X, y)
    columns = list(X.columns)
    model_id = f"histgb__C_clean__{family}__refit_full"
    return pipeline, columns, num_cols, cat_cols, model_id


def _get_pipeline(family: str):
    """Return cached pipeline tuple for ``family`` or ``None`` if unavailable."""
    if family in _MODEL_CACHE:
        return _MODEL_CACHE[family]
    with _MODEL_LOCK:
        if family in _MODEL_CACHE:
            return _MODEL_CACHE[family]
        trained = _train_family_pipeline(family)
        _MODEL_CACHE[family] = trained
        return trained


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _coerce_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _coerce_int(v: Any) -> Optional[int]:
    f = _coerce_float(v)
    if f is None:
        return None
    return int(f)


def _perturbation_magnitude_from_id(perturbation_id: Optional[str]) -> Optional[int]:
    if not perturbation_id or "_" not in str(perturbation_id):
        return None
    tail = str(perturbation_id).rsplit("_", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


def _extract_feature_dict(
    family: str,
    payload_snapshot: Optional[dict],
    action_context: Optional[dict],
    perturbation_context: Optional[dict],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Pull the C_clean columns out of the three context dicts.

    Returns ``(values, used, missing)`` where:

    * ``values`` maps column → value (with ``np.nan`` for numeric
      placeholders so HistGB's native-NaN handling kicks in)
    * ``used``    lists columns we successfully sourced
    * ``missing`` lists columns we could not source from any input
    """
    pert = perturbation_context or {}
    act = action_context or {}
    pl = payload_snapshot or {}

    pid = _coerce_str(pert.get("perturbation_id")) or _coerce_str(pl.get("perturbation_id"))
    fam = _coerce_str(pert.get("family")) or _coerce_str(pert.get("perturbation_family"))
    inst_class = (
        _coerce_str(pert.get("instance_class"))
        or _coerce_str(pl.get("instance_class"))
    )
    cheap_action = _coerce_str(act.get("action")) or _coerce_str(act.get("cheap_action"))
    magnitude = pert.get("magnitude_grid")
    if magnitude is None:
        magnitude = _perturbation_magnitude_from_id(pid)

    # Source numeric features. For each, we look first in
    # action_context (post-cheap-action diagnostics), then in
    # perturbation_context (pre-cheap descriptors), then in the
    # payload_snapshot under the same name.
    def find(*keys: str) -> Any:
        for src in (act, pert, pl):
            for k in keys:
                if k in src and src[k] is not None:
                    return src[k]
        return None

    raw: dict[str, Any] = {
        "perturbation_family": fam,
        "perturbation_magnitude": magnitude,
        "cheap_action": cheap_action,
        "instance_class": inst_class,
        # Pre-cheap (B) descriptors
        "baseline_n_routes": _coerce_int(find("baseline_n_routes")),
        "baseline_obj": _coerce_float(find("baseline_obj", "baseline_objective")),
        "baseline_generalized_cost": _coerce_float(find("baseline_generalized_cost")),
        "baseline_total_wait": _coerce_float(find("baseline_total_wait")),
        "baseline_min_route_slack": _coerce_float(find("baseline_min_route_slack")),
        "baseline_mean_route_slack": _coerce_float(find("baseline_mean_route_slack")),
        "baseline_n_tight_customers": _coerce_int(find("baseline_n_tight_customers")),
        "n_affected_customers": _coerce_int(find("n_affected_customers")),
        "affected_route_share": _coerce_float(find("affected_route_share")),
        "affected_demand_share": _coerce_float(find("affected_demand_share")),
        "affected_service_time_share": _coerce_float(find("affected_service_time_share")),
        "affected_min_slack": _coerce_float(find("affected_min_slack")),
        "affected_mean_slack": _coerce_float(find("affected_mean_slack")),
        "affected_total_wait": _coerce_float(find("affected_total_wait")),
        # Post-cheap (C) diagnostics
        "action_feasible": _coerce_int(find("action_feasible")),
        "infeasibility_kind": _coerce_str(find("infeasibility_kind")),
        "action_obj_delta_pct": _coerce_float(find("action_obj_delta_pct")),
        "action_generalized_delta_pct": _coerce_float(find("action_generalized_delta_pct")),
        "action_time_warp": _coerce_float(find("action_time_warp")),
        "action_total_wait": _coerce_float(find("action_total_wait")),
        "action_total_duration": _coerce_float(find("action_total_duration")),
        "action_n_late_customers": _coerce_int(find("action_n_late_customers")),
        "action_max_lateness": _coerce_float(find("action_max_lateness")),
    }
    # Apply family-specific C_clean drops (PV / SCHEDULE).
    drops_by_family = {
        "OBJ": set(),
        "PLAN_VALIDITY": {
            "action_feasible",
            "action_n_late_customers",
            "action_max_lateness",
            "infeasibility_kind",
        },
        "STRUCT": set(),
        "SCHEDULE": {"action_n_late_customers", "action_max_lateness"},
    }
    for col in drops_by_family.get(family, set()):
        raw.pop(col, None)

    # Categorical columns must always be present (HistGB encoder expects
    # them); we substitute ``"__missing__"`` when unknown so the column
    # is preserved but contributes only the imputed-most-frequent value.
    categorical_cols = {"perturbation_family", "cheap_action", "instance_class", "infeasibility_kind"}
    used: list[str] = []
    missing: list[str] = []
    for col, val in raw.items():
        if val is None or (isinstance(val, float) and val != val):
            if col in categorical_cols:
                # Encoder will impute most-frequent; we still mark missing.
                missing.append(col)
                raw[col] = "__missing__"
            else:
                missing.append(col)
                raw[col] = np.nan
        else:
            used.append(col)
    return raw, used, missing


# Minimum number of *non-categorical* sourced features the gate needs
# before it will produce a probability. Anything below this and the
# gate abstains.
_MIN_NUMERIC_FEATURES_REQUIRED: int = 6


def _enough_features(used: Iterable[str]) -> bool:
    numeric = [c for c in used if c not in {
        "perturbation_family", "cheap_action", "instance_class", "infeasibility_kind",
    }]
    return len(numeric) >= _MIN_NUMERIC_FEATURES_REQUIRED


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def predict_sufficiency(
    *,
    family: str,
    payload_snapshot: Optional[dict] = None,
    action_context: Optional[dict] = None,
    perturbation_context: Optional[dict] = None,
    correctness_floor: float = DEFAULT_CORRECTNESS_FLOOR,
    force_enabled: Optional[bool] = None,
) -> SufficiencyGateResult:
    """Advisory sufficiency prediction.

    Parameters
    ----------
    family:
        Claim family — must be one of :data:`SUPPORTED_FAMILIES` for the
        gate to make a decision.
    payload_snapshot, action_context, perturbation_context:
        Three context dicts the gate may pull features from. The gate
        does **not** read raw operator-facing prompt text and does not
        produce answer prose. It also does not invoke a solver.
    correctness_floor:
        Stage A produced one threshold per (family, floor). 0.9 is the
        default deployment floor; 0.95 / 0.8 are also available.
    force_enabled:
        Test-hook: when ``True``, bypasses the env-flag check. Production
        callers should leave this ``None``.
    """
    fam_norm = (family or "").strip().upper()
    cheap_action = _coerce_str((action_context or {}).get("action")) or "unknown"

    if force_enabled is None:
        enabled = gate_enabled()
    else:
        enabled = bool(force_enabled)

    if not enabled:
        return SufficiencyGateResult(
            enabled=False,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            model_id="disabled",
            features_used=[],
            missing_features=[],
            reason=(
                "Learned sufficiency gate is disabled "
                f"({GATE_FLAG_ENV_VAR} not set)."
            ),
            correctness_floor=correctness_floor,
        )

    if fam_norm not in SUPPORTED_FAMILIES:
        return SufficiencyGateResult(
            enabled=True,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            model_id="unsupported_family",
            features_used=[],
            missing_features=[],
            reason=(
                f"Gate is not calibrated for family {fam_norm!r}; "
                "supported families: OBJ, PLAN_VALIDITY, STRUCT, SCHEDULE."
            ),
            correctness_floor=correctness_floor,
        )

    cfg = _config_for(fam_norm, correctness_floor)
    if cfg is None:
        return SufficiencyGateResult(
            enabled=True,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            model_id="no_deployment_config",
            features_used=[],
            missing_features=[],
            reason=(
                f"No deployment_config row for "
                f"(family={fam_norm}, correctness_floor={correctness_floor})."
            ),
            correctness_floor=correctness_floor,
        )
    threshold = float(cfg["chosen_threshold"])

    feature_values, used, missing = _extract_feature_dict(
        fam_norm, payload_snapshot, action_context, perturbation_context,
    )

    if not _enough_features(used):
        return SufficiencyGateResult(
            enabled=True,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            threshold=threshold,
            model_id=f"histgb__C_clean__{fam_norm}",
            features_used=used,
            missing_features=missing,
            reason=(
                "Gate abstained: too few non-categorical features could "
                "be sourced from the supplied contexts "
                f"({len(used)} of >= {_MIN_NUMERIC_FEATURES_REQUIRED} required)."
            ),
            correctness_floor=correctness_floor,
        )

    trained = _get_pipeline(fam_norm)
    if trained is None:
        return SufficiencyGateResult(
            enabled=True,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            threshold=threshold,
            model_id="model_unavailable",
            features_used=used,
            missing_features=missing,
            reason=(
                "Gate model could not be fit (training parquet unavailable)."
            ),
            correctness_floor=correctness_floor,
        )

    pipeline, columns, num_cols, cat_cols, model_id = trained
    try:
        import pandas as pd
        row_df = pd.DataFrame([feature_values], columns=columns)
        # ColumnTransformer expects matching dtypes — apply the same
        # casts as build_feature_matrix.
        for c in num_cols:
            row_df[c] = row_df[c].astype(float)
        for c in cat_cols:
            row_df[c] = row_df[c].astype(str)
        proba = pipeline.predict_proba(row_df)
        classes_ = getattr(pipeline.named_steps["clf"], "classes_", np.array([0, 1]))
        if proba.shape[1] == 1:
            p_sufficient = float(classes_[0] == 1)
        else:
            pos_idx = int(np.where(classes_ == 1)[0][0]) if 1 in classes_ else 1
            p_sufficient = float(proba[0, pos_idx])
    except Exception as exc:  # noqa: BLE001
        return SufficiencyGateResult(
            enabled=True,
            family=fam_norm,
            action=cheap_action,
            decision="no_decision",
            threshold=threshold,
            model_id=model_id,
            features_used=used,
            missing_features=missing,
            reason=f"Gate prediction failed: {exc!r}",
            correctness_floor=correctness_floor,
        )

    if p_sufficient >= threshold:
        decision: GateDecision = "accept_current"
        rec_action = None
        reason = (
            f"The current payload is predicted to be sufficient for this "
            f"claim (p={p_sufficient:.3f} >= threshold={threshold:.2f})."
        )
    else:
        decision = "recommend_recompute"
        rec_action = DEFAULT_RECOMPUTE_ACTION
        reason = (
            f"A bounded recomputation is recommended because the current "
            f"action is predicted insufficient for this claim "
            f"(p={p_sufficient:.3f} < threshold={threshold:.2f})."
        )

    # Hard invariant: pyvrp_60s is never a product action.
    if rec_action in FORBIDDEN_RECOMPUTE_ACTIONS:  # pragma: no cover — defensive
        rec_action = DEFAULT_RECOMPUTE_ACTION

    return SufficiencyGateResult(
        enabled=True,
        family=fam_norm,
        action=cheap_action,
        p_sufficient=p_sufficient,
        threshold=threshold,
        decision=decision,
        model_id=model_id,
        features_used=used,
        missing_features=missing,
        reason=reason,
        recommended_action=rec_action,
        correctness_floor=correctness_floor,
    )


__all__ = [
    "DEFAULT_CORRECTNESS_FLOOR",
    "DEFAULT_RECOMPUTE_ACTION",
    "FORBIDDEN_RECOMPUTE_ACTIONS",
    "GATE_FLAG_ENV_VAR",
    "SUPPORTED_FAMILIES",
    "SufficiencyGateResult",
    "gate_enabled",
    "predict_sufficiency",
]
