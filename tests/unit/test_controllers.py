import uuid

import pytest

from src.api import controllers
from src.api import models
from src.api import schemas
from src.api import services


async def test_create_sync_run(sync_run, monkeypatch):
    async def create(**kwargs):
        assert kwargs['trigger'] == schemas.SyncTrigger.MANUAL
        return sync_run

    monkeypatch.setattr(models, 'sync_run_create', create)

    async def enqueue(run_id):
        assert run_id == sync_run['id']

    monkeypatch.setattr(services, 'enqueue_sync_run', enqueue)

    result = await controllers.create_sync_run(schemas.SyncRunCreate())

    assert result == sync_run


async def test_create_sync_run_propagates_queue_failure(sync_run, monkeypatch):
    async def create(**kwargs):
        return sync_run

    async def enqueue(run_id):
        raise services.SyncDispatchError

    monkeypatch.setattr(models, 'sync_run_create', create)
    monkeypatch.setattr(services, 'enqueue_sync_run', enqueue)

    with pytest.raises(services.SyncDispatchError):
        await controllers.create_sync_run(schemas.SyncRunCreate())


async def test_create_sync_run_propagates_active_conflict(monkeypatch):
    async def create(**kwargs):
        raise models.SyncAlreadyActive

    monkeypatch.setattr(models, 'sync_run_create', create)

    with pytest.raises(models.SyncAlreadyActive):
        await controllers.create_sync_run(schemas.SyncRunCreate())


async def test_retry_sync_run_propagates_not_found(monkeypatch):
    async def retry(run_id):
        raise models.SyncRunDoesNotExist

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(models.SyncRunDoesNotExist):
        await controllers.retry_sync_run(uuid.uuid4())


async def test_retry_sync_run_enqueues_retry(sync_run, monkeypatch):
    async def retry(run_id):
        return sync_run

    enqueued = []

    async def enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(models, 'sync_run_retry', retry)
    monkeypatch.setattr(services, 'enqueue_sync_run', enqueue)

    result = await controllers.retry_sync_run(uuid.uuid4())

    assert result == sync_run
    assert enqueued == [sync_run['id']]


async def test_retry_sync_run_propagates_non_retryable(monkeypatch):
    async def retry(run_id):
        raise models.SyncRunNotRetryable

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(models.SyncRunNotRetryable):
        await controllers.retry_sync_run(uuid.uuid4())


async def test_retry_sync_run_propagates_active_conflict(monkeypatch):
    async def retry(run_id):
        raise models.SyncAlreadyActive

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(models.SyncAlreadyActive):
        await controllers.retry_sync_run(uuid.uuid4())


async def test_get_sync_run_propagates_not_found(monkeypatch):
    async def get(run_id):
        raise models.SyncRunDoesNotExist

    monkeypatch.setattr(models, 'sync_run_detail', get)

    with pytest.raises(models.SyncRunDoesNotExist):
        await controllers.get_sync_run(uuid.uuid4())


async def test_list_sync_runs_builds_pagination(sync_run, monkeypatch):
    async def list_runs(**kwargs):
        return [sync_run], 1

    monkeypatch.setattr(models, 'sync_run_list', list_runs)
    query = schemas.SyncRunListQueryParams(limit=10, offset=2)

    result = await controllers.list_sync_runs(query)

    assert result['sync_runs'] == [sync_run]
    assert result['pagination'] == {'limit': 10, 'offset': 2, 'total': 1}


async def test_get_current_sync(sync_run, monkeypatch):
    async def current():
        return {'active_run': sync_run, 'last_run': None}

    monkeypatch.setattr(models, 'sync_current', current)

    assert await controllers.get_current_sync() == {
        'active_run': sync_run,
        'last_run': None,
    }
