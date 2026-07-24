import uuid

import fastapi

from .. import models
from .. import schemas
from .. import services


def _already_active_exception() -> fastapi.HTTPException:
    return fastapi.HTTPException(
        status_code=409,
        detail='A synchronization of this type is already queued or running',
    )


async def create_sync_run(sync: schemas.SyncRunCreate) -> dict:
    try:
        run = await models.sync_run_create(
            trigger=schemas.SyncTrigger.MANUAL,
            sync_type=sync.sync_type,
        )
    except models.SyncAlreadyActive:
        raise _already_active_exception()
    await _enqueue(run)
    return run


async def retry_sync_run(run_id: uuid.UUID) -> dict:
    try:
        run = await models.sync_run_retry(run_id)
    except models.SyncRunDoesNotExist:
        raise fastapi.HTTPException(status_code=404, detail='Synchronization run not found')
    except models.SyncRunNotRetryable:
        raise fastapi.HTTPException(
            status_code=409,
            detail='Only failed or partially completed synchronization can be retried',
        )
    except models.SyncAlreadyActive:
        raise _already_active_exception()
    await _enqueue(run)
    return run


async def _enqueue(run: dict) -> None:
    try:
        await services.enqueue_sync_run(run['id'])
    except services.SyncDispatchError:
        await models.sync_run_fail(run['id'], 'Failed to publish synchronization task')
        raise fastapi.HTTPException(
            status_code=503,
            detail='Synchronization queue is unavailable',
        )


async def get_sync_run(run_id: uuid.UUID) -> dict:
    try:
        return await models.sync_run_detail(run_id)
    except models.SyncRunDoesNotExist:
        raise fastapi.HTTPException(status_code=404, detail='Synchronization run not found')


async def list_sync_runs(query_params: schemas.SyncRunListQueryParams) -> dict:
    runs, total = await models.sync_run_list(
        limit=query_params.limit,
        offset=query_params.offset,
        status=query_params.status,
        trigger=query_params.trigger,
        sync_type=query_params.sync_type,
    )
    return {
        'sync_runs': runs,
        'pagination': {
            'limit': query_params.limit,
            'offset': query_params.offset,
            'total': total,
        },
    }


async def get_current_sync() -> dict:
    return await models.sync_current()
