import uuid

import pytest

from src.api.services import dispatch


async def test_enqueue_sync_run_publishes_task(monkeypatch):
    run_id = uuid.uuid4()
    published = {}

    def send_task(name, args):
        published.update(name=name, args=args)

    monkeypatch.setattr(dispatch.celery_app, 'send_task', send_task)

    await dispatch.enqueue_sync_run(run_id)

    assert published == {'name': 'sync.execute', 'args': [str(run_id)]}


async def test_enqueue_sync_run_wraps_broker_error(monkeypatch):
    run_id = uuid.uuid4()
    failed = {}

    def send_task(name, args):
        raise ConnectionError

    async def fail(requested_id, error_message):
        failed.update(run_id=requested_id, error_message=error_message)

    monkeypatch.setattr(dispatch.celery_app, 'send_task', send_task)
    monkeypatch.setattr(dispatch.models, 'sync_run_fail', fail)

    with pytest.raises(dispatch.SyncDispatchError):
        await dispatch.enqueue_sync_run(run_id)

    assert failed == {
        'run_id': run_id,
        'error_message': 'Failed to publish synchronization task',
    }
