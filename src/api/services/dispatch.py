import asyncio
import uuid

from ...worker import celery_app


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
        raise SyncDispatchError
