import asyncio
import uuid

from ...worker import celery_app
from .. import models


class SyncDispatchError(Exception):
    """Raised when a synchronization task cannot be published to Celery."""


async def enqueue_sync_run(run_id: uuid.UUID) -> None:
    try:
        await asyncio.to_thread(
            celery_app.send_task,
            'sync.execute',
            args=[str(run_id)],
        )
    except Exception:
        await models.sync_run_fail(run_id, 'Failed to publish synchronization task')
        raise SyncDispatchError
