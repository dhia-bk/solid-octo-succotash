from unittest.mock import MagicMock

from app.db.neo4j_client import Neo4jClient


def test_fetch_all_returns_records() -> None:
    client = Neo4jClient.__new__(Neo4jClient)
    client._driver = MagicMock()
    client._logger = MagicMock()
    client._settings = MagicMock()
    client._settings.database = "neo4j"
    client._settings.uri = "bolt://localhost:7687"

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.data.return_value = [{"name": "user"}]
    mock_result.consume.return_value = MagicMock()
    mock_session.run.return_value = mock_result

    client._driver.session.return_value = mock_session

    rows = client.fetch_all("MATCH (n) RETURN n")

    assert rows == [{"name": "user"}]
    mock_session.run.assert_called_once()