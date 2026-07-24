import uuid

import pytest

from src.api.models import item
from src.api.models import run


class ResultStub:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def one(self):
        return self._rows[0]

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class SessionStub:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, query):
        return ResultStub(self._rows)


async def test_item_updates_return_database_objects():
    item_id = uuid.uuid4()
    row = {'id': item_id, 'status': 'processing'}
    session = SessionStub([row])

    started = await item.sync_item_start_attempt.__wrapped__(session, item_id)
    succeeded = await item.sync_item_succeed.__wrapped__(session, item_id, {'ok': True})
    failed = await item.sync_item_fail.__wrapped__(session, item_id, 'error')

    assert started == row
    assert succeeded == row
    assert failed == row


async def test_recovery_models_return_database_objects():
    run_id = uuid.uuid4()
    rows = [{'id': run_id, 'status': 'queued'}]
    session = SessionStub(rows)

    items = await item.sync_items_requeue_interrupted.__wrapped__(session)
    runs = await run.sync_runs_requeue_interrupted.__wrapped__(session)
    queued = await run.sync_runs_queued.__wrapped__(session)

    assert items == rows
    assert runs == rows
    assert queued == rows


async def test_run_updates_return_database_object():
    run_id = uuid.uuid4()
    row = {'id': run_id, 'status': 'failed'}
    session = SessionStub([row])

    claimed = await run.sync_run_claim.__wrapped__(session, run_id)
    failed = await run.sync_run_fail.__wrapped__(session, run_id, 'error')

    assert claimed == row
    assert failed == row


async def test_run_claim_raises_when_run_is_not_queued():
    with pytest.raises(run.SyncRunNotClaimable):
        await run.sync_run_claim.__wrapped__(SessionStub([]), uuid.uuid4())
