from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.core.exceptions import InvalidConfigError, ValidationError
from app.core.time import (
    TimeWindow,
    build_daily_window,
    build_incremental_window,
    build_rolling_lookback_window,
    ensure_utc_datetime,
    format_partition_date_key,
    format_run_id_timestamp,
    is_null_watermark,
    max_watermark,
    normalize_watermark,
    parse_iso_datetime,
    split_daily_windows,
    watermark_equal,
    watermark_greater_than,
)


def test_ensure_utc_datetime_on_naive_value() -> None:
    raw = datetime(2026, 1, 1, 12, 0, 0)

    normalized = ensure_utc_datetime(raw)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 12


def test_ensure_utc_datetime_converts_offset_to_utc() -> None:
    raw = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone(timedelta(hours=3)))

    normalized = ensure_utc_datetime(raw)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 12


def test_parse_iso_datetime_supports_z_suffix() -> None:
    parsed = parse_iso_datetime("2026-01-01T12:00:00Z")

    assert parsed == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_is_null_watermark_handles_none_and_blank() -> None:
    assert is_null_watermark(None) is True
    assert is_null_watermark("   ") is True
    assert is_null_watermark("2026-01-01T00:00:00Z") is False


def test_normalize_watermark_returns_utc_datetime() -> None:
    normalized = normalize_watermark("2026-01-01T12:00:00Z")

    assert normalized == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_max_watermark_returns_latest_value() -> None:
    latest = max_watermark(
        "2026-01-01T12:00:00Z",
        "2026-01-01T13:00:00Z",
        None,
    )

    assert latest == datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)


def test_watermark_comparisons_work() -> None:
    assert watermark_greater_than("2026-01-01T13:00:00Z", "2026-01-01T12:00:00Z") is True
    assert watermark_equal("2026-01-01T12:00:00Z", "2026-01-01T12:00:00Z") is True


def test_time_window_rejects_invalid_range() -> None:
    with pytest.raises(ValidationError):
        TimeWindow(
            start=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            end=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )


def test_build_daily_window_returns_full_utc_day() -> None:
    window = build_daily_window(date(2026, 1, 1))

    assert window.start == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert window.end == datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def test_build_incremental_window_rejects_nulls() -> None:
    with pytest.raises(InvalidConfigError):
        build_incremental_window(None, "2026-01-01T01:00:00Z")  # type: ignore[arg-type]


def test_build_rolling_lookback_window_requires_positive_delta() -> None:
    with pytest.raises(InvalidConfigError):
        build_rolling_lookback_window(end=datetime(2026, 1, 1, tzinfo=UTC), days=0, hours=0)


def test_split_daily_windows_splits_interval() -> None:
    windows = split_daily_windows(
        "2026-01-01T12:00:00Z",
        "2026-01-03T06:00:00Z",
    )

    assert len(windows) == 3
    assert windows[0].start == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert windows[-1].end == datetime(2026, 1, 3, 6, 0, 0, tzinfo=UTC)


def test_formatters_return_stable_strings() -> None:
    value = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC)

    assert format_partition_date_key(value) == "20260101"
    assert format_run_id_timestamp(value) == "20260101T123456Z"
