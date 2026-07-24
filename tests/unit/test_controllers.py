import uuid

import fastapi
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


async def test_create_sync_run_maps_queue_failure(sync_run, monkeypatch):
    async def create(**kwargs):
        return sync_run

    async def enqueue(run_id):
        raise services.SyncDispatchError

    failed = {}

    async def fail(run_id, error_message):
        failed.update(run_id=run_id, error_message=error_message)

    monkeypatch.setattr(models, 'sync_run_create', create)
    monkeypatch.setattr(models, 'sync_run_fail', fail)
    monkeypatch.setattr(services, 'enqueue_sync_run', enqueue)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.create_sync_run(schemas.SyncRunCreate())

    assert exc_info.value.status_code == 503
    assert failed['run_id'] == sync_run['id']


async def test_create_sync_run_maps_active_conflict(monkeypatch):
    async def create(**kwargs):
        raise models.SyncAlreadyActive

    monkeypatch.setattr(models, 'sync_run_create', create)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.create_sync_run(schemas.SyncRunCreate())
    assert exc_info.value.status_code == 409


async def test_retry_sync_run_maps_not_found(monkeypatch):
    async def retry(run_id):
        raise models.SyncRunDoesNotExist

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.retry_sync_run(uuid.uuid4())
    assert exc_info.value.status_code == 404


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


async def test_retry_sync_run_maps_non_retryable(monkeypatch):
    async def retry(run_id):
        raise models.SyncRunNotRetryable

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.retry_sync_run(uuid.uuid4())
    assert exc_info.value.status_code == 409


async def test_retry_sync_run_maps_active_conflict(monkeypatch):
    async def retry(run_id):
        raise models.SyncAlreadyActive

    monkeypatch.setattr(models, 'sync_run_retry', retry)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.retry_sync_run(uuid.uuid4())
    assert exc_info.value.status_code == 409


async def test_get_sync_run_maps_not_found(monkeypatch):
    async def get(run_id):
        raise models.SyncRunDoesNotExist

    monkeypatch.setattr(models, 'sync_run_detail', get)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await controllers.get_sync_run(uuid.uuid4())
    assert exc_info.value.status_code == 404


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
