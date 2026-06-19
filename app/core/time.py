"""
UTC-only time utilities for Project Pulse Knowledge Graph.

Design rules:
- All internal datetimes are timezone-aware and normalized to UTC.
- No other module should call datetime.now() directly.
- All watermark handling should go through this module.
- Formatting for logs, partitions, and run IDs should be centralized here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.core.constants import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_PARTITION_DATE_FORMAT,
    DEFAULT_PARTITION_HOUR_FORMAT,
    DEFAULT_TIMESTAMP_FORMAT,
)
from app.core.exceptions import InvalidConfigError, ValidationError


# Data structures



@dataclass(frozen=True)
class TimeWindow:
    """
    Represents a UTC time window with inclusive start and exclusive end.

    Attributes:
        start: UTC-aware start datetime.
        end: UTC-aware end datetime.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValidationError(
                "TimeWindow datetimes must be timezone-aware",
                start=self.start,
                end=self.end,
            )
        if self.start >= self.end:
            raise ValidationError(
                "TimeWindow start must be earlier than end",
                start=self.start.isoformat(),
                end=self.end.isoformat(),
            )



# Current UTC helpers



def utc_now() -> datetime:
    """
    Return the current UTC-aware datetime.

    Returns:
        A timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)


def utc_today() -> date:
    """
    Return today's date in UTC.

    Returns:
        Current UTC date.
    """
    return utc_now().date()


def utc_midnight(dt: datetime | None = None) -> datetime:
    """
    Return the UTC midnight boundary for a given datetime.

    Args:
        dt: Optional datetime. If omitted, current UTC time is used.

    Returns:
        UTC-aware datetime at 00:00:00 for the given day.
    """
    value = ensure_utc_datetime(dt or utc_now())
    return datetime.combine(value.date(), time.min, tzinfo=UTC)



# Parsing and normalization



def ensure_utc_datetime(value: datetime) -> datetime:
    """
    Normalize a datetime to a UTC-aware datetime.

    Rules:
    - Naive datetimes are treated as UTC.
    - Timezone-aware datetimes are converted to UTC.

    Args:
        value: Datetime to normalize.

    Returns:
        UTC-aware datetime.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_iso_datetime(value: str) -> datetime:
    """
    Parse an ISO-8601 datetime string and normalize it to UTC.

    Supports:
    - 'Z' suffix
    - timezone offsets
    - naive timestamps (treated as UTC)

    Args:
        value: ISO datetime string.

    Returns:
        UTC-aware datetime.

    Raises:
        ValidationError: If the value cannot be parsed.
    """
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(
            "Invalid ISO datetime string",
            raw_value=value,
        ) from exc

    return ensure_utc_datetime(parsed)


def parse_date_string(value: str, fmt: str = DEFAULT_DATE_FORMAT) -> date:
    """
    Parse a date string using the provided format.

    Args:
        value: Date string.
        fmt: Format string.

    Returns:
        Parsed date object.
    """
    try:
        return datetime.strptime(value, fmt).date()
    except ValueError as exc:
        raise ValidationError(
            "Invalid date string",
            raw_value=value,
            date_format=fmt,
        ) from exc


def warehouse_value_to_utc_datetime(value: Any) -> datetime | None:
    """
    Convert a warehouse datetime-like value to a UTC-aware datetime.

    Supported inputs:
    - None
    - datetime
    - ISO datetime string

    Args:
        value: Raw warehouse value.

    Returns:
        UTC-aware datetime or None.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return ensure_utc_datetime(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return parse_iso_datetime(stripped)

    raise ValidationError(
        "Unsupported warehouse datetime value type",
        raw_type=type(value).__name__,
        raw_value=repr(value),
    )



# Watermark helpers



def is_null_watermark(value: datetime | str | None) -> bool:
    """
    Determine whether a watermark value is effectively null.

    Args:
        value: Watermark value.

    Returns:
        True if the watermark is missing/blank, else False.
    """
    if value is None:
        return True
    return bool(isinstance(value, str) and not value.strip())


def normalize_watermark(value: datetime | str | None) -> datetime | None:
    """
    Normalize a watermark value to a UTC-aware datetime.

    Args:
        value: Datetime, ISO string, or None.

    Returns:
        UTC-aware datetime or None.
    """
    if is_null_watermark(value):
        return None

    if isinstance(value, datetime):
        return ensure_utc_datetime(value)

    if isinstance(value, str):
        return parse_iso_datetime(value)

    raise ValidationError(
        "Unsupported watermark type",
        raw_type=type(value).__name__,
        raw_value=repr(value),
    )


def max_watermark(*values: datetime | str | None) -> datetime | None:
    """
    Return the latest non-null watermark.

    Args:
        *values: Watermark candidates.

    Returns:
        Latest UTC-aware datetime or None if all are null.
    """
    normalized = [normalize_watermark(value) for value in values]
    non_null = [value for value in normalized if value is not None]

    if not non_null:
        return None

    return max(non_null)


def watermark_greater_than(
    left: datetime | str | None,
    right: datetime | str | None,
) -> bool:
    """
    Compare two watermark values.

    Returns True if left > right after normalization.

    Null behavior:
    - null > null => False
    - non-null > null => True
    - null > non-null => False
    """
    left_value = normalize_watermark(left)
    right_value = normalize_watermark(right)

    if left_value is None:
        return False
    if right_value is None:
        return True

    return left_value > right_value


def watermark_equal(
    left: datetime | str | None,
    right: datetime | str | None,
) -> bool:
    """
    Compare two watermark values for equality after normalization.
    """
    return normalize_watermark(left) == normalize_watermark(right)


def generate_watermark_timestamp(dt: datetime | None = None) -> str:
    """
    Generate a stable watermark timestamp string in UTC.

    Args:
        dt: Optional datetime. Defaults to current UTC time.

    Returns:
        ISO-style UTC timestamp string.
    """
    return format_iso_timestamp(dt or utc_now())



# Window and partition helpers



def build_daily_window(target_date: date) -> TimeWindow:
    """
    Build a UTC daily window for a specific date.

    Args:
        target_date: Target UTC date.

    Returns:
        TimeWindow from 00:00:00 to next day 00:00:00 UTC.
    """
    start = datetime.combine(target_date, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return TimeWindow(start=start, end=end)


def build_hourly_window(target_datetime: datetime) -> TimeWindow:
    """
    Build a UTC hourly window for a specific datetime.

    Args:
        target_datetime: Any datetime within the target hour.

    Returns:
        TimeWindow aligned to the hour in UTC.
    """
    dt = ensure_utc_datetime(target_datetime)
    start = dt.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return TimeWindow(start=start, end=end)


def build_incremental_window(
    start: datetime | str,
    end: datetime | str,
) -> TimeWindow:
    """
    Build an incremental extraction window.

    Args:
        start: Inclusive start datetime.
        end: Exclusive end datetime.

    Returns:
        UTC-normalized TimeWindow.
    """
    start_dt = normalize_watermark(start)
    end_dt = normalize_watermark(end)

    if start_dt is None or end_dt is None:
        raise InvalidConfigError(
            "Incremental window requires non-null start and end",
            start=start,
            end=end,
        )

    return TimeWindow(start=start_dt, end=end_dt)


def build_rolling_lookback_window(
    *,
    end: datetime | None = None,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
) -> TimeWindow:
    """
    Build a UTC rolling lookback window ending at the provided time.

    Args:
        end: Optional UTC end datetime. Defaults to utc_now().
        days: Lookback days.
        hours: Lookback hours.
        minutes: Lookback minutes.

    Returns:
        TimeWindow covering the lookback interval.
    """
    end_dt = ensure_utc_datetime(end or utc_now())
    delta = timedelta(days=days, hours=hours, minutes=minutes)

    if delta <= timedelta(0):
        raise InvalidConfigError(
            "Rolling lookback window must be positive",
            days=days,
            hours=hours,
            minutes=minutes,
        )

    start_dt = end_dt - delta
    return TimeWindow(start=start_dt, end=end_dt)


def split_daily_windows(start: datetime | str, end: datetime | str) -> list[TimeWindow]:
    """
    Split a UTC interval into daily windows.

    Args:
        start: Inclusive start datetime.
        end: Exclusive end datetime.

    Returns:
        List of daily TimeWindow objects.
    """
    window = build_incremental_window(start, end)
    windows: list[TimeWindow] = []

    cursor = utc_midnight(window.start)

    while cursor < window.end:
        next_cursor = cursor + timedelta(days=1)
        chunk_start = max(cursor, window.start)
        chunk_end = min(next_cursor, window.end)

        if chunk_start < chunk_end:
            windows.append(TimeWindow(start=chunk_start, end=chunk_end))

        cursor = next_cursor

    return windows


def split_hourly_windows(start: datetime | str, end: datetime | str) -> list[TimeWindow]:
    """
    Split a UTC interval into hourly windows.

    Args:
        start: Inclusive start datetime.
        end: Exclusive end datetime.

    Returns:
        List of hourly TimeWindow objects.
    """
    window = build_incremental_window(start, end)
    windows: list[TimeWindow] = []

    start_dt = normalize_watermark(start)
    if start_dt is None:
        raise ValidationError("Hourly split requires non-null start", start=start)

    cursor = ensure_utc_datetime(start_dt).replace(minute=0, second=0, microsecond=0)

    while cursor < window.end:
        next_cursor = cursor + timedelta(hours=1)
        chunk_start = max(cursor, window.start)
        chunk_end = min(next_cursor, window.end)

        if chunk_start < chunk_end:
            windows.append(TimeWindow(start=chunk_start, end=chunk_end))

        cursor = next_cursor

    return windows



# Formatting helpers



def format_iso_timestamp(value: datetime) -> str:
    """
    Format a datetime using the platform's canonical UTC timestamp format.

    Args:
        value: Datetime to format.

    Returns:
        Formatted UTC timestamp string.
    """
    return ensure_utc_datetime(value).strftime(DEFAULT_TIMESTAMP_FORMAT)


def format_log_timestamp(value: datetime | None = None) -> str:
    """
    Format a UTC timestamp for structured logs.

    Args:
        value: Optional datetime. Defaults to utc_now().

    Returns:
        Stable UTC timestamp string.
    """
    return format_iso_timestamp(value or utc_now())


def format_date_only(value: date | datetime) -> str:
    """
    Format a date or datetime as YYYY-MM-DD.

    Args:
        value: Date or datetime.

    Returns:
        Stable date string.
    """
    if isinstance(value, datetime):
        return ensure_utc_datetime(value).strftime(DEFAULT_DATE_FORMAT)
    return value.strftime(DEFAULT_DATE_FORMAT)


def format_partition_date_key(value: date | datetime) -> str:
    """
    Format a partition date key as YYYYMMDD.

    Args:
        value: Date or datetime.

    Returns:
        Partition date string.
    """
    if isinstance(value, datetime):
        value = ensure_utc_datetime(value).date()
    return value.strftime(DEFAULT_PARTITION_DATE_FORMAT)


def format_partition_hour_key(value: datetime) -> str:
    """
    Format a partition hour key as YYYYMMDDHH.

    Args:
        value: Datetime.

    Returns:
        Partition hour string.
    """
    return ensure_utc_datetime(value).strftime(DEFAULT_PARTITION_HOUR_FORMAT)


def format_run_id_timestamp(value: datetime | None = None) -> str:
    """
    Format a timestamp component suitable for run IDs.

    Example:
        20260123T121530Z

    Args:
        value: Optional datetime. Defaults to utc_now().

    Returns:
        Run ID timestamp component.
    """
    dt = ensure_utc_datetime(value or utc_now())
    return dt.strftime("%Y%m%dT%H%M%SZ")
