import uuid

from .. import models
from .. import schemas
from .. import services


async def create_sync_run(sync: schemas.SyncRunCreate) -> dict:
    run = await models.sync_run_create(
        trigger=schemas.SyncTrigger.MANUAL,
        sync_type=sync.sync_type,
    )
    await services.enqueue_sync_run(run['id'])
    return run


async def retry_sync_run(run_id: uuid.UUID) -> dict:
    run = await models.sync_run_retry(run_id)
    await services.enqueue_sync_run(run['id'])
    return run


async def get_sync_run(run_id: uuid.UUID) -> dict:
    return await models.sync_run_detail(run_id)


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
