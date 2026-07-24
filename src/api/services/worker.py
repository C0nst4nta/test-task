import asyncio
import logging

from .. import models
from . import sync


logger = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self, executor: sync.SyncExecutor, poll_interval_seconds: float) -> None:
        self._executor = executor
        self._poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        await models.sync_runs_requeue_interrupted()
        self._task = asyncio.create_task(self._run(), name='sync-worker')

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def wake(self) -> None:
        self._wake_event.set()

    async def run_once(self) -> bool:
        run = await models.sync_run_claim_next()
        if run is None:
            return False
        await self._executor.execute(run)
        return True

    async def _run(self) -> None:
        logger.info('Synchronization worker started')
        while True:
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception('Synchronization worker iteration failed')
                processed = False
            if processed:
                continue
            self._wake_event.clear()
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self._poll_interval_seconds,
                )
            except TimeoutError:
                pass
