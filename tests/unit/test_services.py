import asyncio
import uuid

from src.api import models
from src.api import providers
from src.api import schemas
from src.api import services


class SourceStub:
    def __init__(self, records=None, error=None):
        self.records = records or []
        self.error = error
        self.calls = 0

    async def fetch_employees(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.records


class DestinationStub:
    def __init__(self, failed_ids=None):
        self.failed_ids = set(failed_ids or [])

    async def upsert_employee(self, employee):
        if employee.external_id in self.failed_ids:
            raise providers.ExternalSystemError('System B returned HTTP 503')
        return schemas.SystemBResponse(external_id=employee.external_id, status='created')


def _patch_model_repository(monkeypatch):
    state = {'items': {}, 'finished': False, 'run_error': None}

    async def failed_payloads(run_id):
        return []

    async def upsert(run_id, external_id, source_payload):
        item = {
            'id': uuid.uuid4(),
            'run_id': run_id,
            'external_id': external_id,
            'status': 'pending',
            'attempts': 0,
            'source_payload': source_payload,
        }
        state['items'][external_id] = item
        return item

    async def list_items(run_id):
        return list(state['items'].values())

    async def start(item_id):
        item = next(value for value in state['items'].values() if value['id'] == item_id)
        item['attempts'] += 1
        item['status'] = 'processing'

    async def succeed(item_id, response):
        item = next(value for value in state['items'].values() if value['id'] == item_id)
        item['status'] = 'succeeded'
        item['destination_response'] = response

    async def fail(item_id, error_message):
        item = next(value for value in state['items'].values() if value['id'] == item_id)
        item['status'] = 'failed'
        item['error_message'] = error_message

    async def finish(run_id):
        state['finished'] = True

    async def fail_run(run_id, error_message):
        state['run_error'] = error_message

    monkeypatch.setattr(models, 'sync_failed_payloads', failed_payloads)
    monkeypatch.setattr(models, 'sync_item_upsert', upsert)
    monkeypatch.setattr(models, 'sync_item_list_for_run', list_items)
    monkeypatch.setattr(models, 'sync_item_start_attempt', start)
    monkeypatch.setattr(models, 'sync_item_succeed', succeed)
    monkeypatch.setattr(models, 'sync_item_fail', fail)
    monkeypatch.setattr(models, 'sync_run_finish', finish)
    monkeypatch.setattr(models, 'sync_run_fail', fail_run)
    return state


async def test_executor_tracks_successes_and_item_failures(employee, monkeypatch):
    failed = employee.model_copy(update={'external_id': 'employee-failed'})
    source = SourceStub([employee, failed])
    destination = DestinationStub(failed_ids={failed.external_id})
    handler = services.EmployeeSyncHandler(source, destination)
    executor = services.SyncExecutor(
        {schemas.SyncType.EMPLOYEES: handler},
        max_retries=2,
        retry_delay_seconds=0,
    )
    state = _patch_model_repository(monkeypatch)

    await executor.execute({
        'id': uuid.uuid4(),
        'sync_type': 'employees',
        'retry_of_id': None,
    })

    assert state['finished'] is True
    assert state['run_error'] is None
    assert state['items'][employee.external_id]['status'] == 'succeeded'
    assert state['items'][failed.external_id]['status'] == 'failed'
    assert state['items'][failed.external_id]['attempts'] == 2


async def test_executor_retries_source_and_marks_run_failed(monkeypatch):
    source = SourceStub(error=providers.ExternalSystemError('System A is unavailable'))
    handler = services.EmployeeSyncHandler(source, DestinationStub())
    executor = services.SyncExecutor(
        {schemas.SyncType.EMPLOYEES: handler},
        max_retries=2,
        retry_delay_seconds=0,
    )
    state = _patch_model_repository(monkeypatch)

    await executor.execute({
        'id': uuid.uuid4(),
        'sync_type': 'employees',
        'retry_of_id': None,
    })

    assert source.calls == 2
    assert state['finished'] is False
    assert state['run_error'] == 'System A is unavailable'


async def test_executor_retry_uses_failed_snapshots(employee, monkeypatch):
    source = SourceStub(error=AssertionError('source should not be called'))
    handler = services.EmployeeSyncHandler(source, DestinationStub())
    executor = services.SyncExecutor(
        {schemas.SyncType.EMPLOYEES: handler},
        max_retries=1,
        retry_delay_seconds=0,
    )
    state = _patch_model_repository(monkeypatch)

    async def failed_payloads(run_id):
        return [employee.model_dump(mode='json')]

    monkeypatch.setattr(models, 'sync_failed_payloads', failed_payloads)
    await executor.execute({
        'id': uuid.uuid4(),
        'sync_type': 'employees',
        'retry_of_id': uuid.uuid4(),
    })

    assert source.calls == 0
    assert state['finished'] is True


async def test_worker_claims_and_executes(monkeypatch):
    run = {'id': uuid.uuid4()}
    calls = []

    async def claim():
        return run

    class ExecutorStub:
        async def execute(self, claimed_run):
            calls.append(claimed_run)

    monkeypatch.setattr(models, 'sync_run_claim_next', claim)
    worker = services.SyncWorker(ExecutorStub(), poll_interval_seconds=1)

    assert await worker.run_once() is True
    assert calls == [run]


async def test_scheduler_skips_when_run_is_active(monkeypatch):
    async def create(**kwargs):
        raise models.SyncAlreadyActive

    class WorkerStub:
        def wake(self):
            raise AssertionError('worker must not be woken')

    monkeypatch.setattr(models, 'sync_run_create', create)
    scheduler = services.SyncScheduler(WorkerStub(), interval_seconds=1)

    assert await scheduler.enqueue() is False


async def test_worker_lifecycle_when_queue_is_empty(monkeypatch):
    state = {'requeued': False, 'claims': 0}

    async def requeue():
        state['requeued'] = True

    async def claim():
        state['claims'] += 1
        return None

    class ExecutorStub:
        async def execute(self, run):
            raise AssertionError('empty queue must not execute')

    monkeypatch.setattr(models, 'sync_runs_requeue_interrupted', requeue)
    monkeypatch.setattr(models, 'sync_run_claim_next', claim)
    worker = services.SyncWorker(ExecutorStub(), poll_interval_seconds=0.01)

    await worker.start()
    await worker.start()
    worker.wake()
    await asyncio.sleep(0.02)
    await worker.stop()
    await worker.stop()

    assert state['requeued'] is True
    assert state['claims'] >= 1


async def test_scheduler_lifecycle_enqueues_runs(monkeypatch):
    state = {'created': 0, 'woken': 0}

    async def create(**kwargs):
        state['created'] += 1

    class WorkerStub:
        def wake(self):
            state['woken'] += 1

    monkeypatch.setattr(models, 'sync_run_create', create)
    scheduler = services.SyncScheduler(
        WorkerStub(),
        interval_seconds=0.01,
        immediate=True,
    )

    await scheduler.start()
    await scheduler.start()
    await asyncio.sleep(0.02)
    await scheduler.stop()
    await scheduler.stop()

    assert state['created'] >= 2
    assert state['woken'] == state['created']
