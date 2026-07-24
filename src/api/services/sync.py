import logging
import uuid

import pydantic

from ...core import retries
from .. import models
from .. import providers
from .. import schemas


logger = logging.getLogger(__name__)


class EmployeeSyncHandler:
    def __init__(
        self,
        source: providers.SystemAClient,
        destination: providers.SystemBClient,
    ) -> None:
        self._source = source
        self._destination = destination

    async def fetch(self) -> list[schemas.EmployeeRecord]:
        return await self._source.fetch_employees()

    async def send(
        self,
        record: schemas.EmployeeRecord,
    ) -> schemas.SystemBResponse:
        return await self._destination.upsert_employee(record)


class SyncExecutor:
    def __init__(
        self,
        handlers: dict[schemas.SyncType, EmployeeSyncHandler],
        max_retries: int,
        retry_delay_seconds: float,
    ) -> None:
        self._handlers = handlers
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    async def execute(self, run: dict) -> None:
        run_id = run['id']
        try:
            sync_type = schemas.SyncType(run['sync_type'])
            handler = self._handlers[sync_type]
            records = await self._load_records(handler, run)
            items = await self._prepare_items(run_id, records)
            for item in items:
                if item['status'] == schemas.SyncItemStatus.SUCCEEDED.value:
                    continue
                record = schemas.EmployeeRecord.model_validate(item['source_payload'])
                await self._process_item(handler, item['id'], record)
            await models.sync_run_finish(run_id)
        except (providers.ExternalSystemError, pydantic.ValidationError) as error:
            logger.warning('Synchronization run %s failed: %s', run_id, error)
            await models.sync_run_fail(run_id, str(error))
        except Exception:
            logger.exception('Unexpected error in synchronization run %s', run_id)
            await models.sync_run_fail(run_id, 'Unexpected synchronization error')

    async def _load_records(
        self,
        handler: EmployeeSyncHandler,
        run: dict,
    ) -> list[schemas.EmployeeRecord]:
        retry_of_id = run.get('retry_of_id')
        if retry_of_id is not None:
            payloads = await models.sync_failed_payloads(retry_of_id)
            if payloads:
                return [schemas.EmployeeRecord.model_validate(payload) for payload in payloads]
        return await self._with_retries(handler.fetch)

    async def _prepare_items(
        self,
        run_id: uuid.UUID,
        records: list[schemas.EmployeeRecord],
    ) -> list[dict]:
        for record in records:
            await models.sync_item_upsert(
                run_id,
                record.external_id,
                record.model_dump(mode='json'),
            )
        return await models.sync_item_list_for_run(run_id)

    async def _process_item(
        self,
        handler: EmployeeSyncHandler,
        item_id: uuid.UUID,
        record: schemas.EmployeeRecord,
    ) -> None:
        @retries.retry(
            exception=providers.ExternalSystemError,
            max_retries=self._max_retries,
            max_value=self._retry_delay_seconds,
        )
        async def send():
            await models.sync_item_start_attempt(item_id)
            return await handler.send(record)

        try:
            response = await send()
        except providers.ExternalSystemError as error:
            await models.sync_item_fail(item_id, str(error))
        else:
            await models.sync_item_succeed(item_id, response.model_dump(mode='json'))

    async def _with_retries(self, operation):
        wrapped = retries.retry_wrap(
            operation,
            exception=providers.ExternalSystemError,
            max_retries=self._max_retries,
            max_value=self._retry_delay_seconds,
        )
        return await wrapped()
