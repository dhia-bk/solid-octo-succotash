from unittest.mock import MagicMock

from app.db.source_inventory import SourceInventoryRepository


def test_upsert_source_calls_metadata_db() -> None:
    repo = SourceInventoryRepository.__new__(SourceInventoryRepository)
    repo._metadata_db = MagicMock()
    repo._logger = MagicMock()

    repo._metadata_db.fetch_one.return_value = {
        "source_name": "users",
        "domain": "identity",
        "inclusion_mode": "graph_core",
        "freshness_field": None,
        "key_fields_json": "[]",
        "graph_entity_mappings_json": "[]",
        "status": None,
        "notes": None,
        "coverage_metadata_json": "{}",
        "created_at": "2026-01-23T00:00:00Z",
        "updated_at": "2026-01-23T00:00:00Z",
    }

    record = repo.upsert_source(
        source_name="users",
        domain="identity",
        inclusion_mode="graph_core",
    )

    assert record.source_name == "users"
    assert repo._metadata_db.execute.called


def test_get_source_returns_record() -> None:
    repo = SourceInventoryRepository.__new__(SourceInventoryRepository)
    repo._metadata_db = MagicMock()
    repo._logger = MagicMock()

    repo._metadata_db.fetch_one.return_value = {
        "source_name": "users",
        "domain": "identity",
        "inclusion_mode": "graph_core",
        "freshness_field": None,
        "key_fields_json": "[]",
        "graph_entity_mappings_json": "[]",
        "status": None,
        "notes": None,
        "coverage_metadata_json": "{}",
        "created_at": "2026-01-23T00:00:00Z",
        "updated_at": "2026-01-23T00:00:00Z",
    }

    record = repo.get_source("users")

    assert record is not None
    assert record.source_name == "users"
