"""
app/transformers/temporal.py
============================
Temporal era classification engine.

Classifies UTC datetimes into named eras for graph properties:
    - fixture_era   (written by fixtures.py)
    - prediction_era (written by predictions.py)

Era boundaries are loaded from the inference config section
(configs/inference.yaml → temporal_eras key). If not configured,
a set of platform-appropriate defaults is used.

No transformer may hardcode a date boundary. All era logic goes through
TemporalEngine.classify_era() so that era definitions remain in config,
not scattered across transformer files.

Config shape (configs/inference.yaml):
    temporal_eras:
      - name: "pre_platform"
        start: "2018-01-01"
        end: "2021-06-01"
      - name: "early"
        start: "2021-06-01"
        end: "2022-12-01"
      - name: "growth"
        start: "2022-12-01"
        end: "2024-01-01"
      - name: "current"
        start: "2024-01-01"
        end: null

Design rules:
- TemporalEngine is stateless after construction.
- Era list is sorted by start datetime at construction time.
- Eras must not overlap. Gaps are permitted (classify_era returns None for
  datetimes that fall between eras or before all known eras).
- The open-ended (end=None) era, if present, captures everything after its
  start. Only one open era is permitted and it must be last.
- build_temporal_engine() is the only permitted constructor path in
  production. Direct TemporalEngine() construction is for tests only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.core.time import ensure_utc_datetime, parse_date_string, utc_now

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default era definitions
# ---------------------------------------------------------------------------
# Used when configs/inference.yaml does not define temporal_eras.
# These represent plausible platform lifecycle phases for a sports prediction
# product. Update configs/inference.yaml to override without touching code.

_DEFAULT_ERA_SPECS: list[dict[str, str | None]] = [
    {
        "name": "pre_platform",
        "start": "2018-01-01",
        "end": "2021-06-01",
    },
    {
        "name": "early",
        "start": "2021-06-01",
        "end": "2022-12-01",
    },
    {
        "name": "growth",
        "start": "2022-12-01",
        "end": "2024-01-01",
    },
    {
        "name": "current",
        "start": "2024-01-01",
        "end": None,  # open era — captures everything from this point forward
    },
]


# ---------------------------------------------------------------------------
# TemporalEra
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalEra:
    """
    A named temporal period with an inclusive start and exclusive end.

    Attributes:
        name:  Era label written to graph properties (e.g. "early", "current").
        start: UTC-aware inclusive start datetime.
        end:   UTC-aware exclusive end datetime. None means the era is open
               (extends to the present and beyond).
    """

    name: str
    start: datetime
    end: datetime | None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ConfigurationError("TemporalEra.name cannot be empty")

        if self.start.tzinfo is None:
            raise ConfigurationError(
                "TemporalEra.start must be timezone-aware",
                era_name=self.name,
            )

        if self.end is not None:
            if self.end.tzinfo is None:
                raise ConfigurationError(
                    "TemporalEra.end must be timezone-aware when provided",
                    era_name=self.name,
                )
            if self.end <= self.start:
                raise ConfigurationError(
                    "TemporalEra.end must be after start",
                    era_name=self.name,
                    start=self.start.isoformat(),
                    end=self.end.isoformat(),
                )

    def contains(self, value: datetime) -> bool:
        """
        Return True if value falls within this era.

        Args:
            value: UTC-aware datetime to test.

        Returns:
            True if start <= value < end (or start <= value when end is None).
        """
        utc_value = ensure_utc_datetime(value)
        if utc_value < self.start:
            return False
        if self.end is None:
            return True
        return utc_value < self.end

    def is_open(self) -> bool:
        """Return True if this era has no end boundary."""
        return self.end is None


# ---------------------------------------------------------------------------
# TemporalEngine
# ---------------------------------------------------------------------------


class TemporalEngine:
    """
    Classifies UTC datetimes into named temporal eras.

    Constructed from an ordered list of TemporalEra instances. Eras are
    sorted by start datetime at construction and must not overlap.

    Usage:
        engine = build_temporal_engine()
        era_name = engine.classify_era(row.kickoff_at_utc)   # → "current"
        is_new   = engine.is_recent(row.kickoff_at_utc, days=90)
    """

    def __init__(self, eras: list[TemporalEra]) -> None:
        """
        Construct a TemporalEngine from a list of era definitions.

        Args:
            eras: Era definitions. May be in any order; sorted internally
                  by start datetime. Must not be empty.

        Raises:
            ConfigurationError: If the era list is empty, contains
                overlapping boundaries, or has more than one open era.
        """
        if not eras:
            raise ConfigurationError(
                "TemporalEngine requires at least one TemporalEra"
            )

        self._eras: list[TemporalEra] = sorted(eras, key=lambda e: e.start)
        self._validate_eras()

        logger.debug(
            "TemporalEngine constructed",
            extra={"era_count": len(self._eras), "era_names": [e.name for e in self._eras]},
        )

    # -- Public API -----------------------------------------------------------

    def classify_era(self, value: datetime | None) -> str | None:
        """
        Return the era name for a UTC datetime.

        Args:
            value: UTC-aware datetime (from a typed row after _ts coercion
                   is NOT appropriate here — pass the raw datetime before
                   converting to string). May be None.

        Returns:
            Era name string if value falls within a known era, else None.
            Returns None when value is None or falls between/before all eras.
        """
        if value is None:
            return None

        utc_value = ensure_utc_datetime(value)

        for era in self._eras:
            if era.contains(utc_value):
                return era.name

        return None

    def is_recent(self, value: datetime | None, *, days: int) -> bool:
        """
        Return True if value is within `days` of the current UTC time.

        Args:
            value: UTC-aware datetime, or None.
            days:  Lookback window in days (must be positive).

        Returns:
            True if value is not None and utc_now() - value <= days days.
            False if value is None or older than the window.
        """
        if value is None:
            return False

        if days <= 0:
            raise ConfigurationError(
                "is_recent requires a positive days argument",
                days=days,
            )

        utc_value = ensure_utc_datetime(value)
        cutoff = utc_now() - timedelta(days=days)
        return utc_value >= cutoff

    def era_names(self) -> list[str]:
        """Return all registered era names in chronological order."""
        return [era.name for era in self._eras]

    def era_count(self) -> int:
        """Return the number of registered eras."""
        return len(self._eras)

    # -- Validation -----------------------------------------------------------

    def _validate_eras(self) -> None:
        """
        Validate the sorted era list for overlaps and open-era rules.

        Raises:
            ConfigurationError: On any structural violation.
        """
        open_eras = [e for e in self._eras if e.is_open()]
        if len(open_eras) > 1:
            raise ConfigurationError(
                "TemporalEngine: only one open-ended era (end=None) is permitted",
                open_era_names=[e.name for e in open_eras],
            )

        if open_eras and self._eras[-1] != open_eras[0]:
            raise ConfigurationError(
                "TemporalEngine: the open-ended era must be the last era "
                "when sorted by start datetime",
                open_era_name=open_eras[0].name,
            )

        for i in range(len(self._eras) - 1):
            current = self._eras[i]
            following = self._eras[i + 1]

            if current.end is None:
                # Already caught above — open era is not last
                break

            if current.end > following.start:
                raise ConfigurationError(
                    "TemporalEngine: era boundaries overlap",
                    era_a=current.name,
                    era_a_end=current.end.isoformat(),
                    era_b=following.name,
                    era_b_start=following.start.isoformat(),
                )

    def __repr__(self) -> str:
        names = ", ".join(e.name for e in self._eras)
        return f"TemporalEngine(eras=[{names}])"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_temporal_engine(era_specs: list[dict[str, Any]] | None = None) -> TemporalEngine:
    """
    Build and return a TemporalEngine from config or defaults.

    Loading strategy:
    1. If era_specs is provided explicitly, use it (test / injection path).
    2. Otherwise attempt to read from the application settings:
           get_settings().inference.get("temporal_eras", [])
    3. If settings are unavailable or temporal_eras is not configured,
       fall back to _DEFAULT_ERA_SPECS.

    Era spec dict shape:
        {
            "name":  "current",        # required non-empty string
            "start": "2024-01-01",     # required YYYY-MM-DD date string
            "end":   "2025-06-01",     # optional YYYY-MM-DD; omit or null for open era
        }

    Args:
        era_specs: Optional list of era spec dicts. When provided, bypasses
                   settings lookup and defaults entirely.

    Returns:
        Constructed and validated TemporalEngine.

    Raises:
        ConfigurationError: If any era spec is malformed or the resulting
            era list fails validation.
    """
    if era_specs is not None:
        logger.debug(
            "build_temporal_engine: using explicitly provided era specs",
            extra={"count": len(era_specs)},
        )
        return TemporalEngine(_parse_era_specs(era_specs))

    # Attempt to load from application settings
    loaded_specs = _load_era_specs_from_settings()

    if loaded_specs:
        logger.info(
            "build_temporal_engine: loaded era config from inference settings",
            extra={"count": len(loaded_specs)},
        )
        return TemporalEngine(_parse_era_specs(loaded_specs))

    # Fall back to defaults
    logger.info(
        "build_temporal_engine: using default era config "
        "(set inference.temporal_eras in configs/inference.yaml to override)",
        extra={"count": len(_DEFAULT_ERA_SPECS)},
    )
    return TemporalEngine(_parse_era_specs(_DEFAULT_ERA_SPECS))


def _load_era_specs_from_settings() -> list[dict[str, Any]]:
    """
    Attempt to load temporal era specs from application settings.

    Returns empty list if settings are unavailable or not configured.
    Never raises — failures degrade gracefully to defaults.
    """
    try:
        from app.core.config import get_settings  # local import avoids circular deps at module load

        settings = get_settings()
        specs = settings.inference.get("temporal_eras", [])

        if not isinstance(specs, list):
            logger.warning(
                "build_temporal_engine: inference.temporal_eras is not a list "
                "— falling back to defaults",
                extra={"type": type(specs).__name__},
            )
            return []

        return specs

    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "build_temporal_engine: could not load settings "
            "— falling back to defaults",
            extra={"error": str(exc)},
        )
        return []


def _parse_era_specs(specs: list[dict[str, Any]]) -> list[TemporalEra]:
    """
    Parse a list of era spec dicts into TemporalEra instances.

    Args:
        specs: List of era spec dicts with name, start, and optional end keys.

    Returns:
        List of TemporalEra instances.

    Raises:
        ConfigurationError: If any spec is missing required fields or has
            invalid date strings.
    """
    eras: list[TemporalEra] = []

    for i, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ConfigurationError(
                "temporal_eras: each entry must be a dict",
                index=i,
                received_type=type(spec).__name__,
            )

        name = spec.get("name")
        if not name or not str(name).strip():
            raise ConfigurationError(
                "temporal_eras: era entry missing required 'name' field",
                index=i,
            )

        raw_start = spec.get("start")
        if not raw_start:
            raise ConfigurationError(
                "temporal_eras: era entry missing required 'start' field",
                index=i,
                era_name=name,
            )

        try:
            start_date = parse_date_string(str(raw_start))
            start_dt = datetime(
                start_date.year, start_date.month, start_date.day,
                tzinfo=UTC,
            )
        except Exception as exc:
            raise ConfigurationError(
                "temporal_eras: invalid 'start' date string",
                index=i,
                era_name=name,
                raw_start=raw_start,
            ) from exc

        raw_end = spec.get("end")
        end_dt: datetime | None = None

        if raw_end is not None:
            try:
                end_date = parse_date_string(str(raw_end))
                end_dt = datetime(
                    end_date.year, end_date.month, end_date.day,
                    tzinfo=UTC,
                )
            except Exception as exc:
                raise ConfigurationError(
                    "temporal_eras: invalid 'end' date string",
                    index=i,
                    era_name=name,
                    raw_end=raw_end,
                ) from exc

        eras.append(TemporalEra(name=str(name).strip(), start=start_dt, end=end_dt))

    return eras