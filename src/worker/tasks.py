import asyncio
import logging
import uuid

import celery.signals

from ..api import models
from ..api import providers
from ..api import schemas
from ..api import services
from ..core import conf
from ..core import postgres
from .app import celery_app


logger = logging.getLogger(__name__)


def _run(coroutine):
    return asyncio.run(coroutine)


def _create_database(settings: conf.Settings) -> postgres.Database:
    return postgres.Database.create(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )


async def _execute_sync(run_id: uuid.UUID) -> bool:
    settings = conf.get_settings()
    database = _create_database(settings)
    source = providers.SystemAClient(
        settings.system_a_base_url,
        settings.external_api_timeout_seconds,
    )
    destination = providers.SystemBClient(
        settings.system_b_base_url,
        settings.external_api_timeout_seconds,
    )
    executor = services.SyncExecutor(
        handlers={
            schemas.SyncType.EMPLOYEES: services.EmployeeSyncHandler(source, destination),
        },
        max_retries=settings.external_api_max_retries,
        retry_delay_seconds=settings.external_api_retry_delay_seconds,
    )

    await database.connect()
    try:
        run = await models.sync_run_claim(run_id)
        if run is None:
            logger.info('Synchronization run %s is no longer queued', run_id)
            return False
        await executor.execute(run)
        return True
    finally:
        await source.close()
        await destination.close()
        await database.disconnect()


async def _schedule_sync() -> bool:
    settings = conf.get_settings()
    database = _create_database(settings)
    await database.connect()
    try:
        try:
            run = await models.sync_run_create(
                trigger=schemas.SyncTrigger.SCHEDULED,
                sync_type=schemas.SyncType.EMPLOYEES,
            )
        except models.SyncAlreadyActive:
            logger.info('Scheduled synchronization skipped because one is already active')
            return False
        celery_app.send_task('sync.execute', args=[str(run['id'])])
        return True
    except Exception:
        if 'run' in locals():
            await models.sync_run_fail(run['id'], 'Failed to publish synchronization task')
        raise
    finally:
        await database.disconnect()


async def _requeue_interrupted() -> None:
    settings = conf.get_settings()
    database = _create_database(settings)
    await database.connect()
    try:
        requeued = await models.sync_runs_requeue_interrupted()
        if requeued:
            logger.warning('Requeued %s interrupted synchronization runs', requeued)
        for run_id in await models.sync_run_queued_ids():
            celery_app.send_task('sync.execute', args=[str(run_id)])
    finally:
        await database.disconnect()


@celery_app.task(name='sync.execute')
def execute_sync(run_id: str) -> bool:
    return _run(_execute_sync(uuid.UUID(run_id)))


@celery_app.task(name='sync.schedule')
def schedule_sync() -> bool:
    return _run(_schedule_sync())


@celery.signals.worker_ready.connect
def requeue_interrupted(**kwargs) -> None:
    _run(_requeue_interrupted())
