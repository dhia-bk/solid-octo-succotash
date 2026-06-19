"""
app/transformers/weighting.py
==============================
Activity weight computation engine for GDS-projection edges.

Computes the `activity_weight` float property written to:
    - MEMBER_OF edges    (memberships.py)
    - PREDICTED edges    (predictions.py)

All outputs are floats in [0.0, 1.0], enforced via
assert_activity_weight_valid() from app/schemas/graph/properties.py
before every return.

Config is loaded from get_settings().weighting which reads
configs/weighting.yaml. The engine reads:
    weighting.membership_activity_weight
    weighting.prediction_confidence_weight

No transformer may inline weight values — all thresholds and weights
come from the config.

Normalization methods:
    min_max         — (v - min) / (max - min), clamped to [0.0, 1.0]
    inverse_min_max — 1 - min_max (lower raw value → higher score)
    capped_min_max  — min_max with values above max saturating at 1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.core.time import ensure_utc_datetime, utc_now
from app.schemas.graph.properties import assert_activity_weight_valid

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_min_max(value: float, *, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _normalize_inverse_min_max(value: float, *, low: float, high: float) -> float:
    return 1.0 - _normalize_min_max(value, low=low, high=high)


def _normalize_capped_min_max(value: float, *, low: float, high: float) -> float:
    return _normalize_min_max(min(value, high), low=low, high=high)


def _apply_normalization(value: float, method: str, low: float, high: float) -> float:
    if method == "min_max":
        return _normalize_min_max(value, low=low, high=high)
    if method == "inverse_min_max":
        return _normalize_inverse_min_max(value, low=low, high=high)
    if method == "capped_min_max":
        return _normalize_capped_min_max(value, low=low, high=high)
    raise ConfigurationError(
        f"Unknown normalization method '{method}'",
        valid_methods=["min_max", "inverse_min_max", "capped_min_max"],
    )


def _days_since(value: datetime) -> float:
    delta = utc_now() - ensure_utc_datetime(value)
    return max(0.0, delta.total_seconds() / 86_400.0)


def _exponential_decay(value: datetime | None, *, half_life_days: float, floor: float) -> float:
    if value is None:
        return 1.0
    if half_life_days <= 0:
        return floor
    age = _days_since(value)
    return max(floor, min(1.0, 2.0 ** (-age / half_life_days)))


# ---------------------------------------------------------------------------
# WeightingEngine
# ---------------------------------------------------------------------------


class WeightingEngine:
    """
    Computes activity_weight floats for GDS-projection edges.

    Reads directly from configs/weighting.yaml via get_settings().weighting.
    All weight values, normalization bounds, and thresholds come from config.

    Construction:
        engine = build_weighting_engine()

    Usage (memberships.py):
        weight = engine.compute_membership_weight(
            fixture_participation_count=row.fixture_participation_count,
            chat_message_count=row.chat_message_count,
            last_active_at=row.last_active_at_utc,
            joined_at=row.joined_at_utc,
            is_moderator=row.role in {"owner", "admin", "moderator"},
        )

    Usage (predictions.py):
        weight = engine.compute_prediction_weight(
            is_correct_result=self._bool(row.is_correct_result),
            points_awarded=row.points_awarded,
            predicted_at=row.predicted_at_utc,
        )
    """

    def __init__(
        self,
        membership_cfg: dict[str, Any],
        prediction_cfg: dict[str, Any],
    ) -> None:
        self._membership = membership_cfg
        self._prediction = prediction_cfg

    # -- Membership weight ----------------------------------------------------

    def compute_membership_weight(
        self,
        fixture_participation_count: int | None,
        chat_message_count: int | None,
        last_active_at: datetime | None,
        joined_at: datetime | None,
        is_moderator: bool | None,
    ) -> float:
        """
        Compute the activity_weight for a MEMBER_OF edge.

        Reads inputs, normalization bounds, and defaults from
        weighting.membership_activity_weight in configs/weighting.yaml.

        Input resolution:
            fixture_participation_count  — None → defaults.missing_fixture_participation_count (0)
            chat_message_count           — None → defaults.missing_chat_message_count
            last_active_at               — None → defaults.missing_recency_days_since_last_activity
            joined_at                    — None → defaults.missing_membership_tenure_days
            is_moderator                 — None/False → defaults.missing_moderator_bonus (0)

        Returns:
            Weighted activity score in [0.0, 1.0].
        """
        cfg = self._membership
        inputs_cfg: dict[str, Any] = cfg["inputs"]
        norm_cfg: dict[str, Any] = cfg["normalization"]
        defaults: dict[str, Any] = cfg["defaults"]

        # Resolve raw values — compute days for datetime inputs
        recency_days = (
            _days_since(last_active_at)
            if last_active_at is not None
            else float(defaults["missing_recency_days_since_last_activity"])
        )
        tenure_days = (
            _days_since(joined_at)
            if joined_at is not None
            else float(defaults["missing_membership_tenure_days"])
        )

        raw: dict[str, float] = {
            "fixture_participation_count": float(
                fixture_participation_count if fixture_participation_count is not None else 0
            ),
            "chat_message_count": float(
                chat_message_count
                if chat_message_count is not None
                else defaults["missing_chat_message_count"]
            ),
            "recency_days_since_last_activity": recency_days,
            "membership_tenure_days": tenure_days,
            "moderator_bonus": float(1 if is_moderator else defaults["missing_moderator_bonus"]),
        }

        total = 0.0
        for input_name, raw_value in raw.items():
            spec = inputs_cfg.get(input_name, {})
            if not spec.get("enabled", True):
                continue

            input_weight = float(spec.get("weight", 0.0))
            if input_weight == 0.0:
                continue

            # moderator_bonus is binary — no normalization entry in config
            if input_name == "moderator_bonus":
                normalized = raw_value  # already 0.0 or 1.0
            else:
                n = norm_cfg[input_name]
                normalized = _apply_normalization(
                    raw_value,
                    method=n["method"],
                    low=float(n["min"]),
                    high=float(n["max"]),
                )

            total += normalized * input_weight

        weight = max(0.0, min(1.0, total))
        assert_activity_weight_valid(weight)
        return weight

    # -- Prediction weight ----------------------------------------------------

    def compute_prediction_weight(
        self,
        is_correct_result: bool | None,
        points_awarded: int | None,
        predicted_at: datetime | None,
    ) -> float:
        """
        Compute the activity_weight for a PREDICTED edge.

        NOTE: prediction_confidence_weight in configs/weighting.yaml is
        currently a stub (enabled: true, version: v1, output_range only).
        This implementation uses interim logic until inputs are defined in
        the config. When inputs are added to the yaml, update this method
        to read them the same way compute_membership_weight does.

        Interim formula:
            base            = 0.40
            correct_bonus   = 0.35 if is_correct_result else 0.0
            points_score    = normalized(points_awarded, 0..100) * 0.25
            weight          = clamp(base + correct_bonus + points_score)
                            * recency_decay(predicted_at, half_life=90d, floor=0.50)

        Returns:
            Prediction activity score in [0.0, 1.0].
        """
        base = 0.40
        correct_bonus = 0.35 if is_correct_result else 0.0
        points_score = _normalize_min_max(
            float(points_awarded) if points_awarded is not None else 0.0,
            low=0.0,
            high=100.0,
        ) * 0.25

        raw_weight = max(0.0, min(1.0, base + correct_bonus + points_score))

        recency_factor = _exponential_decay(
            predicted_at,
            half_life_days=90.0,
            floor=0.50,
        )

        weight = max(0.0, min(1.0, raw_weight * recency_factor))
        assert_activity_weight_valid(weight)
        return weight

    # -- Threshold helpers ----------------------------------------------------

    def is_active_membership(self, weight: float) -> bool:
        """Return True if weight meets the configured active_edge_min threshold."""
        threshold = float(self._membership["thresholds"]["active_edge_min"])
        return weight >= threshold

    def is_strong_membership(self, weight: float) -> bool:
        """Return True if weight meets the configured strong_edge_min threshold."""
        threshold = float(self._membership["thresholds"]["strong_edge_min"])
        return weight >= threshold


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_weighting_engine() -> WeightingEngine:
    """
    Build and return a WeightingEngine from configs/weighting.yaml.

    Reads:
        get_settings().weighting["membership_activity_weight"]
        get_settings().weighting["prediction_confidence_weight"]

    Raises:
        ConfigurationError: If membership_activity_weight is missing or
            structurally invalid. prediction_confidence_weight absence is
            tolerated (stub — interim defaults used).
    """
    weighting = get_settings().weighting

    membership_cfg = weighting.get("membership_activity_weight")
    if not membership_cfg:
        raise ConfigurationError(
            "weighting.membership_activity_weight is missing from configs/weighting.yaml",
        )

    _validate_membership_config(membership_cfg)

    prediction_cfg = weighting.get("prediction_confidence_weight") or {}

    logger.info(
        "WeightingEngine built from config",
        extra={
            "membership_inputs": list(
                k for k, v in membership_cfg.get("inputs", {}).items()
                if v.get("enabled", True)
            ),
            "prediction_config_stub": not bool(prediction_cfg.get("inputs")),
        },
    )

    return WeightingEngine(membership_cfg, prediction_cfg)


def _validate_membership_config(cfg: dict[str, Any]) -> None:
    """
    Validate the membership_activity_weight config section.

    Raises:
        ConfigurationError: If required keys are missing or weights do not
            sum to approximately 1.0.
    """
    for required_key in ("inputs", "normalization", "thresholds", "defaults"):
        if required_key not in cfg:
            raise ConfigurationError(
                f"membership_activity_weight missing required key '{required_key}'",
                config_key=f"weighting.membership_activity_weight.{required_key}",
            )

    inputs = cfg["inputs"]
    total_weight = sum(
        float(spec.get("weight", 0.0))
        for spec in inputs.values()
        if spec.get("enabled", True)
    )

    # Allow small floating point tolerance
    if not (0.99 <= total_weight <= 1.01):
        raise ConfigurationError(
            "membership_activity_weight input weights must sum to 1.0",
            actual_sum=round(total_weight, 4),
        )