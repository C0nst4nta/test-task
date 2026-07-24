import asyncio
import logging

from .. import models
from .. import schemas
from . import worker


logger = logging.getLogger(__name__)


class SyncScheduler:
    def __init__(
        self,
        sync_worker: worker.SyncWorker,
        interval_seconds: float,
        immediate: bool = False,
    ) -> None:
        self._worker = sync_worker
        self._interval_seconds = interval_seconds
        self._immediate = immediate
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name='sync-scheduler')

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def enqueue(self) -> bool:
        try:
            await models.sync_run_create(
                trigger=schemas.SyncTrigger.SCHEDULED,
                sync_type=schemas.SyncType.EMPLOYEES,
            )
        except models.SyncAlreadyActive:
            logger.info('Scheduled synchronization skipped because one is already active')
            return False
        self._worker.wake()
        return True

    async def _run(self) -> None:
        if self._immediate:
            await self._safe_enqueue()
        while True:
            await asyncio.sleep(self._interval_seconds)
            await self._safe_enqueue()

    async def _safe_enqueue(self) -> None:
        try:
            await self.enqueue()
        except Exception:
            logger.exception('Failed to enqueue scheduled synchronization')
