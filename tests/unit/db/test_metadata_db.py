from unittest.mock import MagicMock

from app.db.metadata_db import MetadataDBClient


def test_fetch_one_returns_row() -> None:
    client = MetadataDBClient.__new__(MetadataDBClient)
    client._engine = MagicMock()
    client._logger = MagicMock()

    mock_connection = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {"id": 1}
    mock_connection.execute.return_value = mock_result

    client._engine.connect.return_value.__enter__.return_value = mock_connection

    row = client.fetch_one("SELECT 1")

    assert row == {"id": 1}
    mock_connection.execute.assert_called_once()