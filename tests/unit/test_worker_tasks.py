import uuid

from src.api import models
from src.worker import tasks


class DatabaseStub:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True


async def test_execute_sync_claims_specific_run(monkeypatch):
    run_id = uuid.uuid4()
    run = {'id': run_id, 'sync_type': 'employees', 'retry_of_id': None}
    database = DatabaseStub()
    executed = []

    async def claim(requested_id):
        assert requested_id == run_id
        return run

    class ClientStub:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

    class SyncServiceStub:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, claimed_run):
            executed.append(claimed_run)

    monkeypatch.setattr(tasks, '_create_database', lambda settings: database)
    monkeypatch.setattr(tasks.providers, 'SystemAClient', ClientStub)
    monkeypatch.setattr(tasks.providers, 'SystemBClient', ClientStub)
    monkeypatch.setattr(tasks.services, 'EmployeeSyncService', SyncServiceStub)
    monkeypatch.setattr(models, 'sync_run_claim', claim)

    assert await tasks._execute_sync(run_id) is True
    assert executed == [run]
    assert database.connected is True
    assert database.disconnected is True


async def test_schedule_sync_skips_active_run(monkeypatch):
    database = DatabaseStub()

    async def create(**kwargs):
        raise models.SyncAlreadyActive

    monkeypatch.setattr(tasks, '_create_database', lambda settings: database)
    monkeypatch.setattr(models, 'sync_run_create', create)

    assert await tasks._schedule_sync() is False
    assert database.disconnected is True


async def test_requeue_interrupted_runs(monkeypatch):
    database = DatabaseStub()
    run_id = uuid.uuid4()
    published = []

    async def requeue_items():
        return []

    async def requeue_runs():
        return [{'id': uuid.uuid4()}, {'id': uuid.uuid4()}]

    async def queued_runs():
        return [{'id': run_id}]

    def send_task(name, args):
        published.append((name, args))

    monkeypatch.setattr(tasks, '_create_database', lambda settings: database)
    monkeypatch.setattr(models, 'sync_items_requeue_interrupted', requeue_items)
    monkeypatch.setattr(models, 'sync_runs_requeue_interrupted', requeue_runs)
    monkeypatch.setattr(models, 'sync_runs_queued', queued_runs)
    monkeypatch.setattr(tasks.celery_app, 'send_task', send_task)

    await tasks._requeue_interrupted()

    assert database.disconnected is True
    assert published == [('sync.execute', [str(run_id)])]
