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
    def send_task(name, args):
        raise ConnectionError

    monkeypatch.setattr(dispatch.celery_app, 'send_task', send_task)

    with pytest.raises(dispatch.SyncDispatchError):
        await dispatch.enqueue_sync_run(uuid.uuid4())
