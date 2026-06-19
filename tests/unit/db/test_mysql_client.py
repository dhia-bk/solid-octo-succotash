from unittest.mock import MagicMock

from app.db.mysql_client import MySQLClient


def _build_client() -> MySQLClient:
    client = MySQLClient.__new__(MySQLClient)
    client._engine = MagicMock()
    client._logger = MagicMock()
    client._settings = MagicMock()
    client._settings.host = "localhost"
    client._settings.db = "pulse"
    client._settings.port = 3306
    return client


def test_fetch_all_returns_rows() -> None:
    client = _build_client()

    mock_connection = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [{"id": 1}, {"id": 2}]
    mock_connection.execute.return_value = mock_result

    client._engine.connect.return_value = mock_connection

    rows = client.fetch_all("SELECT 1")

    assert rows == [{"id": 1}, {"id": 2}]
    mock_connection.execute.assert_called_once()


def test_fetch_one_returns_single_row() -> None:
    client = _build_client()

    mock_connection = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {"id": 1}
    mock_connection.execute.return_value = mock_result

    client._engine.connect.return_value = mock_connection

    row = client.fetch_one("SELECT 1")

    assert row == {"id": 1}
    mock_connection.execute.assert_called_once()