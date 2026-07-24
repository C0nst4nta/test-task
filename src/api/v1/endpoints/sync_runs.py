import uuid

import fastapi

from ... import controllers
from ... import schemas


router = fastapi.APIRouter(prefix='/sync-runs')


@router.post(
    '',
    summary='Queue a manual synchronization',
    response_model=schemas.SyncRunGet,
    response_description='Queued synchronization run',
    status_code=202,
    responses={409: {'description': 'A synchronization of this type is already active'}},
)
async def create_sync_run(sync: schemas.SyncRunCreate):
    """Queue a synchronization; processing is performed by the background worker."""
    return await controllers.create_sync_run(sync)


@router.get(
    '',
    summary='List synchronization history',
    response_model=schemas.SyncRunList,
    response_description='Synchronization runs ordered from newest to oldest',
)
async def list_sync_runs(
    query_params: schemas.SyncRunListQueryParams = fastapi.Depends(),
):
    return await controllers.list_sync_runs(query_params)


@router.get(
    '/current',
    summary='Get current synchronization state',
    response_model=schemas.SyncCurrent,
    response_description='Active and most recently finished synchronization runs',
)
async def get_current_sync():
    return await controllers.get_current_sync()


@router.get(
    '/{run_id}',
    summary='Get synchronization run details',
    response_model=schemas.SyncRunDetail,
    response_description='Synchronization run and per-item results',
    responses={404: {'description': 'Synchronization run not found'}},
)
async def get_sync_run(run_id: uuid.UUID):
    return await controllers.get_sync_run(run_id)


@router.post(
    '/{run_id}/retry',
    summary='Retry a failed synchronization',
    response_model=schemas.SyncRunGet,
    response_description='Queued retry run',
    status_code=202,
    responses={
        404: {'description': 'Synchronization run not found'},
        409: {'description': 'Synchronization cannot be retried'},
    },
)
async def retry_sync_run(run_id: uuid.UUID):
    """Queue a new run containing failed items from the selected run."""
    return await controllers.retry_sync_run(run_id)
