from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from app.core.constants import (
    CHECKPOINT_STRATEGY_FULL_REFRESH,
    CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
    CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
    DEFAULT_CHECKPOINT_NAMESPACE,
)
from app.core.exceptions import CheckpointError
from app.db.checkpoints import (
    CheckpointRecord,
    CheckpointRepository,
)


@pytest.fixture
def metadata_db() -> Mock:
    return Mock()


@pytest.fixture
def logger() -> Mock:
    return Mock()


@pytest.fixture
def repo(metadata_db: Mock, logger: Mock) -> CheckpointRepository:
    return CheckpointRepository(metadata_db, logger=logger)


def _sample_row(**overrides):
    row = {
        "namespace": "default",
        "pipeline_name": "pulse_pipeline",
        "source_name": "jira",
        "checkpoint_strategy": CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
        "watermark_value": "2025-01-01T00:00:00+00:00",
        "last_successful_run_id": "run-123",
        "metadata_json": json.dumps({"foo": "bar"}),
        "updated_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# get_checkpoint
# ---------------------------------------------------------------------------

def test_get_checkpoint_returns_record_when_row_exists(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_one.return_value = _sample_row()

    record = repo.get_checkpoint(
        namespace="default",
        pipeline_name="pulse_pipeline",
        source_name="jira",
    )

    assert isinstance(record, CheckpointRecord)
    assert record.namespace == "default"
    assert record.pipeline_name == "pulse_pipeline"
    assert record.source_name == "jira"
    assert record.checkpoint_strategy == CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK
    assert record.watermark_value == "2025-01-01T00:00:00+00:00"
    assert record.last_successful_run_id == "run-123"
    assert record.metadata == {"foo": "bar"}
    assert record.updated_at == "2025-01-02T03:04:05+00:00"

    metadata_db.fetch_one.assert_called_once()
    _, params = metadata_db.fetch_one.call_args.args
    assert params == {
        "namespace": "default",
        "pipeline_name": "pulse_pipeline",
        "source_name": "jira",
    }


def test_get_checkpoint_returns_none_when_missing(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_one.return_value = None

    record = repo.get_checkpoint(
        namespace="default",
        pipeline_name="pulse_pipeline",
        source_name="jira",
    )

    assert record is None


@pytest.mark.parametrize(
    ("namespace", "pipeline_name", "source_name", "field_name"),
    [
        ("", "pipe", "src", "namespace"),
        ("default", "", "src", "pipeline_name"),
        ("default", "pipe", "", "source_name"),
        ("   ", "pipe", "src", "namespace"),
        ("default", "   ", "src", "pipeline_name"),
        ("default", "pipe", "   ", "source_name"),
    ],
)
def test_get_checkpoint_rejects_empty_keys(
    repo: CheckpointRepository,
    namespace: str,
    pipeline_name: str,
    source_name: str,
    field_name: str,
):
    with pytest.raises(CheckpointError) as exc_info:
        repo.get_checkpoint(
            namespace=namespace,
            pipeline_name=pipeline_name,
            source_name=source_name,
        )

    assert "Checkpoint key field must not be empty" in str(exc_info.value)
    assert exc_info.value.context["field_name"] == field_name


def test_get_checkpoint_wraps_db_errors(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_one.side_effect = RuntimeError("db down")

    with pytest.raises(CheckpointError) as exc_info:
        repo.get_checkpoint(
            namespace="default",
            pipeline_name="pulse_pipeline",
            source_name="jira",
        )

    assert "Failed to read checkpoint" in str(exc_info.value)
    assert exc_info.value.context["error_type"] == "RuntimeError"
    assert exc_info.value.context["namespace"] == "default"
    assert exc_info.value.context["pipeline_name"] == "pulse_pipeline"
    assert exc_info.value.context["source_name"] == "jira"


# ---------------------------------------------------------------------------
# list_checkpoints
# ---------------------------------------------------------------------------

def test_list_checkpoints_without_filters(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_all.return_value = [
        _sample_row(source_name="jira"),
        _sample_row(source_name="confluence"),
    ]

    records = repo.list_checkpoints()

    assert len(records) == 2
    assert records[0].source_name == "jira"
    assert records[1].source_name == "confluence"

    metadata_db.fetch_all.assert_called_once()
    _, params = metadata_db.fetch_all.call_args.args
    assert params == {}


def test_list_checkpoints_with_filters_strips_values(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_all.return_value = [_sample_row()]

    records = repo.list_checkpoints(namespace="  default  ", pipeline_name="  pulse_pipeline  ")

    assert len(records) == 1

    metadata_db.fetch_all.assert_called_once()
    statement, params = metadata_db.fetch_all.call_args.args
    assert "WHERE namespace = :namespace AND pipeline_name = :pipeline_name" in statement
    assert params == {
        "namespace": "default",
        "pipeline_name": "pulse_pipeline",
    }


def test_list_checkpoints_wraps_db_errors(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.fetch_all.side_effect = ValueError("bad query")

    with pytest.raises(CheckpointError) as exc_info:
        repo.list_checkpoints(namespace="default")

    assert "Failed to list checkpoints" in str(exc_info.value)
    assert exc_info.value.context["error_type"] == "ValueError"
    assert exc_info.value.context["namespace"] == "default"


# ---------------------------------------------------------------------------
# upsert_checkpoint
# ---------------------------------------------------------------------------

def test_upsert_checkpoint_with_numeric_watermark_normalizes_and_reloads(
    repo: CheckpointRepository,
    metadata_db: Mock,
):
    reloaded = CheckpointRecord(
        namespace="default",
        pipeline_name="pulse_pipeline",
        source_name="test_source",
        checkpoint_strategy=CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
        watermark_value="42",
        last_successful_run_id="run-123",
        metadata={"foo": "bar"},
        updated_at="2025-01-02T03:04:05+00:00",
    )

    with (
        patch("app.db.checkpoints.utc_now") as mock_utc_now,
        patch.object(repo, "get_checkpoint", return_value=reloaded) as mock_get_checkpoint,
    ):
        mock_utc_now.return_value = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        record = repo.upsert_checkpoint(
            namespace="  default  ",
            pipeline_name="  pulse_pipeline  ",
            source_name="  jira  ",
            checkpoint_strategy=CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
            watermark_value="0042",
            last_successful_run_id="  run-123  ",
            metadata={"foo": "bar"},
        )

    assert record is reloaded
    metadata_db.execute.assert_called_once()

    _, params = metadata_db.execute.call_args.args
    assert params == {
        "namespace": "default",
        "pipeline_name": "pulse_pipeline",
        "source_name": "jira",
        "checkpoint_strategy": CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
        "watermark_value": "42",
        "last_successful_run_id": "run-123",
        "metadata_json": json.dumps({"foo": "bar"}, sort_keys=True),
        "updated_at": "2025-01-02T03:04:05+00:00",
    }

    mock_get_checkpoint.assert_called_once_with(
        namespace="  default  ",
        pipeline_name="  pulse_pipeline  ",
        source_name="  jira  ",
    )


def test_upsert_checkpoint_with_full_refresh_forces_null_watermark(
    repo: CheckpointRepository,
    metadata_db: Mock,
):
    reloaded = CheckpointRecord(
        namespace="default",
        pipeline_name="pipe",
        source_name="src",
        checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
        watermark_value=None,
        last_successful_run_id=None,
        metadata={},
        updated_at="2025-01-02T03:04:05+00:00",
    )

    with (
        patch("app.db.checkpoints.utc_now") as mock_utc_now,
        patch.object(repo, "get_checkpoint", return_value=reloaded),
    ):
        mock_utc_now.return_value = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        repo.upsert_checkpoint(
            pipeline_name="pipe",
            source_name="src",
            checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
            watermark_value="should be ignored",
        )

    _, params = metadata_db.execute.call_args.args
    assert params["watermark_value"] is None


def test_upsert_checkpoint_uses_empty_dict_when_metadata_none(
    repo: CheckpointRepository,
    metadata_db: Mock,
):
    reloaded = CheckpointRecord(
        namespace="default",
        pipeline_name="pipe",
        source_name="src",
        checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
        watermark_value=None,
        last_successful_run_id=None,
        metadata={},
        updated_at="2025-01-02T03:04:05+00:00",
    )

    with (
        patch("app.db.checkpoints.utc_now") as mock_utc_now,
        patch.object(repo, "get_checkpoint", return_value=reloaded),
    ):
        mock_utc_now.return_value = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        repo.upsert_checkpoint(
            pipeline_name="pipe",
            source_name="src",
            checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
            metadata=None,
        )

    _, params = metadata_db.execute.call_args.args
    assert params["metadata_json"] == "{}"


def test_upsert_checkpoint_raises_if_reload_missing(repo: CheckpointRepository, metadata_db: Mock):
    with (
        patch("app.db.checkpoints.utc_now") as mock_utc_now,
        patch.object(repo, "get_checkpoint", return_value=None),
    ):
        mock_utc_now.return_value = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        with pytest.raises(CheckpointError) as exc_info:
            repo.upsert_checkpoint(
                pipeline_name="pipe",
                source_name="src",
                checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
            )

    assert "Checkpoint upsert completed but record could not be reloaded" in str(exc_info.value)


def test_upsert_checkpoint_wraps_db_errors(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.execute.side_effect = RuntimeError("write failed")

    with pytest.raises(CheckpointError) as exc_info:
        repo.upsert_checkpoint(
            pipeline_name="pipe",
            source_name="src",
            checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
        )

    assert "Failed to upsert checkpoint" in str(exc_info.value)
    assert exc_info.value.context["error_type"] == "RuntimeError"
    assert exc_info.value.context["checkpoint_strategy"] == CHECKPOINT_STRATEGY_FULL_REFRESH


def test_upsert_checkpoint_preserves_checkpoint_error(repo: CheckpointRepository):
    with pytest.raises(CheckpointError) as exc_info:
        repo.upsert_checkpoint(
            pipeline_name="pipe",
            source_name="src",
            checkpoint_strategy=CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
            watermark_value=True,
        )

    assert "Boolean values are not valid numeric watermarks" in str(exc_info.value)


# ---------------------------------------------------------------------------
# delete_checkpoint
# ---------------------------------------------------------------------------

def test_delete_checkpoint_returns_true_when_row_deleted(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.execute.return_value = 1

    deleted = repo.delete_checkpoint(
        namespace="  default  ",
        pipeline_name="  pipe  ",
        source_name="  src  ",
    )

    assert deleted is True
    metadata_db.execute.assert_called_once()
    _, params = metadata_db.execute.call_args.args
    assert params == {
        "namespace": "default",
        "pipeline_name": "pipe",
        "source_name": "src",
    }


def test_delete_checkpoint_returns_false_when_no_row_deleted(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.execute.return_value = 0

    deleted = repo.delete_checkpoint(
        pipeline_name="pipe",
        source_name="src",
    )

    assert deleted is False


def test_delete_checkpoint_wraps_db_errors(repo: CheckpointRepository, metadata_db: Mock):
    metadata_db.execute.side_effect = RuntimeError("delete failed")

    with pytest.raises(CheckpointError) as exc_info:
        repo.delete_checkpoint(
            pipeline_name="pipe",
            source_name="src",
        )

    assert "Failed to delete checkpoint" in str(exc_info.value)
    assert exc_info.value.context["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# reset_checkpoint
# ---------------------------------------------------------------------------

def test_reset_checkpoint_delegates_to_upsert(repo: CheckpointRepository):
    expected = CheckpointRecord(
        namespace="default",
        pipeline_name="pipe",
        source_name="src",
        checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
        watermark_value=None,
        last_successful_run_id="run-1",
        metadata={"reset": True},
        updated_at="2025-01-02T03:04:05+00:00",
    )

    with patch.object(repo, "upsert_checkpoint", return_value=expected) as mock_upsert:
        result = repo.reset_checkpoint(
            namespace="default",
            pipeline_name="pipe",
            source_name="src",
            metadata={"reset": True},
            last_successful_run_id="run-1",
        )

    assert result is expected
    mock_upsert.assert_called_once_with(
        namespace="default",
        pipeline_name="pipe",
        source_name="src",
        checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
        watermark_value=None,
        last_successful_run_id="run-1",
        metadata={"reset": True},
    )


# ---------------------------------------------------------------------------
# watermark normalization
# ---------------------------------------------------------------------------

def test_normalize_watermark_full_refresh_returns_none(repo: CheckpointRepository):
    assert repo._normalize_watermark_for_storage(
        CHECKPOINT_STRATEGY_FULL_REFRESH,
        "anything",
    ) is None


def test_normalize_watermark_timestamp_returns_none_for_nullish(repo: CheckpointRepository):
    assert repo._normalize_watermark_for_storage(
        CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
        None,
    ) is None


def test_normalize_watermark_timestamp_normalizes_iso(repo: CheckpointRepository):
    with patch("app.db.checkpoints.normalize_watermark") as mock_normalize:
        mock_normalize.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = repo._normalize_watermark_for_storage(
            CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
            "2025-01-01T12:00:00Z",
        )

    assert result == "2025-01-01T12:00:00+00:00"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (42, "42"),
        (42.9, "42"),
        ("42", "42"),
        (" 0042 ", "42"),
        ("-7", "-7"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_watermark_numeric_valid_cases(
    repo: CheckpointRepository,
    value,
    expected,
):
    result = repo._normalize_watermark_for_storage(
        CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
        value,
    )
    assert result == expected


def test_normalize_watermark_numeric_rejects_bool(repo: CheckpointRepository):
    with pytest.raises(CheckpointError) as exc_info:
        repo._normalize_watermark_for_storage(
            CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
            True,
        )

    assert "Boolean values are not valid numeric watermarks" in str(exc_info.value)


@pytest.mark.parametrize("value", ["12.5", "abc", "123x"])
def test_normalize_watermark_numeric_rejects_non_integer_like(repo: CheckpointRepository, value: str):
    with pytest.raises(CheckpointError) as exc_info:
        repo._normalize_watermark_for_storage(
            CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
            value,
        )

    assert "Numeric watermark must be an integer-like value" in str(exc_info.value)


def test_normalize_watermark_rejects_unsupported_strategy(repo: CheckpointRepository):
    with pytest.raises(CheckpointError) as exc_info:
        repo._normalize_watermark_for_storage("bad_strategy", "123")

    assert "Unsupported checkpoint strategy" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------

def test_validate_strategy_rejects_unknown(repo: CheckpointRepository):
    with pytest.raises(CheckpointError) as exc_info:
        repo._validate_strategy("unknown")

    assert "Unsupported checkpoint strategy" in str(exc_info.value)
    assert "supported_strategies" in exc_info.value.context


@pytest.mark.parametrize("value,expected", [(None, None), ("  abc  ", "abc"), ("   ", None)])
def test_normalize_optional_string(value, expected):
    assert CheckpointRepository._normalize_optional_string(value) == expected


# ---------------------------------------------------------------------------
# _to_record
# ---------------------------------------------------------------------------

def test_to_record_parses_json_metadata():
    row = _sample_row(metadata_json='{"a": 1}')

    record = CheckpointRepository._to_record(row)

    assert record.metadata == {"a": 1}


def test_to_record_accepts_dict_metadata():
    row = _sample_row(metadata_json={"a": 1})

    record = CheckpointRepository._to_record(row)

    assert record.metadata == {"a": 1}


def test_to_record_defaults_empty_metadata():
    row = _sample_row(metadata_json="")

    record = CheckpointRepository._to_record(row)

    assert record.metadata == {}


def test_to_record_preserves_string_updated_at():
    row = _sample_row(updated_at="2025-01-02T03:04:05+00:00")

    record = CheckpointRepository._to_record(row)

    assert record.updated_at == "2025-01-02T03:04:05+00:00"


# ---------------------------------------------------------------------------
# properties / repository_error
# ---------------------------------------------------------------------------

def test_properties_expose_dependencies(repo: CheckpointRepository, metadata_db: Mock, logger: Mock):
    assert repo.metadata_db is metadata_db
    assert repo.logger is logger


def test_repository_error_includes_original_exception_type():
    err = CheckpointRepository._repository_error(
        "boom",
        ValueError("bad"),
        namespace=DEFAULT_CHECKPOINT_NAMESPACE,
    )

    assert isinstance(err, CheckpointError)
    assert "boom" in str(err)
    assert err.context["error_type"] == "ValueError"
    assert err.context["namespace"] == DEFAULT_CHECKPOINT_NAMESPACE