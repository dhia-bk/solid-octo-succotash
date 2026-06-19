from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.db.job_runs import JobRunRepository


def test_create_run_calls_metadata_db() -> None:
    repo = JobRunRepository.__new__(JobRunRepository)
    repo._metadata_db = MagicMock()
    repo._logger = MagicMock()

    repo._metadata_db.fetch_one.return_value = {
        "run_id": "run-123",
        "job_name": "test_job",
        "pipeline_name": None,
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "environment": "dev",
        "version": None,
        "error_message": None,
        "metadata_json": "{}",
        "created_at": "2026-01-23T00:00:00Z",
        "updated_at": "2026-01-23T00:00:00Z",
    }

    record = repo.create_run(
        run_id="run-123",
        job_name="test_job",
        environment="dev",
        metadata={"source": "unit-test"},
    )

    assert record.run_id == "run-123"
    assert repo._metadata_db.execute.called


def test_mark_succeeded_calls_metadata_db() -> None:
    repo = JobRunRepository.__new__(JobRunRepository)
    repo._metadata_db = MagicMock()
    repo._logger = MagicMock()

    started_at = datetime(2026, 1, 23, 0, 0, 0, tzinfo=UTC)
    finished_at = datetime(2026, 1, 23, 0, 1, 0, tzinfo=UTC)

    repo._metadata_db.fetch_one.side_effect = [
        {
            "run_id": "run-123",
            "job_name": "test_job",
            "pipeline_name": None,
            "status": "running",
            "started_at": started_at,
            "finished_at": None,
            "duration_ms": None,
            "environment": "dev",
            "version": None,
            "error_message": None,
            "metadata_json": "{}",
            "created_at": started_at,
            "updated_at": started_at,
        },
        {
            "run_id": "run-123",
            "job_name": "test_job",
            "pipeline_name": None,
            "status": "succeeded",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": 60000,
            "environment": "dev",
            "version": None,
            "error_message": None,
            "metadata_json": "{}",
            "created_at": started_at,
            "updated_at": finished_at,
        },
    ]

    record = repo.mark_succeeded(run_id="run-123")

    assert record.status == "succeeded"
    assert repo._metadata_db.execute.called