from unittest.mock import MagicMock

from app.db.model_registry import ModelRegistryRepository


def test_register_model_run_calls_metadata_db() -> None:
    repo = ModelRegistryRepository.__new__(ModelRegistryRepository)
    repo._metadata_db = MagicMock()
    repo._logger = MagicMock()

    repo._metadata_db.fetch_one.return_value = {
        "run_id": "run123",
        "model_type": "leiden",
        "logical_version": "1.0.0",
        "config_version": None,
        "status": "succeeded",
        "artifact_uri": None,
        "compatibility_metadata_json": "{}",
        "metrics_summary_json": "{}",
        "created_at": "2026-01-23T00:00:00Z",
        "updated_at": "2026-01-23T00:00:00Z",
    }

    record = repo.register_model_run(
        model_type="leiden",
        logical_version="1.0.0",
        run_id="run123",
    )

    assert record.run_id == "run123"
    assert repo._metadata_db.execute.called
