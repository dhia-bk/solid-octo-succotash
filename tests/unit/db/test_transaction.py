import pytest

from app.core.exceptions import DatabaseError
from app.db.transaction import transaction_scope


class DummyResource:
    def __init__(self) -> None:
        self.started = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        self.started = True

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_transaction_success_commits_and_closes() -> None:
    resource = DummyResource()

    with transaction_scope(resource):
        pass

    assert resource.started is True
    assert resource.committed is True
    assert resource.rolled_back is False
    assert resource.closed is True


def test_transaction_failure_rolls_back_and_maps_error() -> None:
    resource = DummyResource()

    with pytest.raises(DatabaseError), transaction_scope(resource):
        raise ValueError("boom")

    assert resource.started is True
    assert resource.committed is False
    assert resource.rolled_back is True
    assert resource.closed is True
