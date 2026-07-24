import logging
import uuid

import pydantic

from ...core import retries
from .. import models
from .. import providers
from .. import schemas


logger = logging.getLogger(__name__)


class EmployeeSyncService:
    def __init__(
        self,
        source: providers.SystemAClient,
        destination: providers.SystemBClient,
        max_retries: int,
        retry_delay_seconds: float,
    ) -> None:
        self._source = source
        self._destination = destination
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    async def execute(self, sync_run: dict) -> dict:
        run_id = sync_run['id']
        try:
            employees = await self._load_employees(sync_run)
            sync_items = await self._save_sync_items(run_id, employees)
            for sync_item in sync_items:
                await self._sync_employee(sync_item)
            return await models.sync_run_finish(run_id)
        except (providers.ExternalSystemError, pydantic.ValidationError) as error:
            logger.warning('Synchronization run %s failed: %s', run_id, error)
            return await models.sync_run_fail(run_id, str(error))
        except Exception:
            logger.exception('Unexpected error in synchronization run %s', run_id)
            return await models.sync_run_fail(run_id, 'Unexpected synchronization error')

    async def _load_employees(self, sync_run: dict) -> list[schemas.EmployeeRecord]:
        original_run_id = sync_run.get('retry_of_id')
        if original_run_id is not None:
            failed_payloads = await models.sync_failed_payloads(original_run_id)
            if failed_payloads:
                return [
                    schemas.EmployeeRecord.model_validate(payload)
                    for payload in failed_payloads
                ]

        fetch_employees = self._retry_external_call(self._source.fetch_employees)
        return await fetch_employees()

    async def _save_sync_items(
        self,
        run_id: uuid.UUID,
        employees: list[schemas.EmployeeRecord],
    ) -> list[dict]:
        for employee in employees:
            await models.sync_item_upsert(
                run_id,
                employee.external_id,
                employee.model_dump(mode='json'),
            )
        return await models.sync_item_list_for_run(run_id)

    async def _sync_employee(self, sync_item: dict) -> None:
        if sync_item['status'] == schemas.SyncItemStatus.SUCCEEDED.value:
            return

        item_id = sync_item['id']
        employee = schemas.EmployeeRecord.model_validate(sync_item['source_payload'])

        @self._retry_external_call
        async def upsert_employee():
            await models.sync_item_start_attempt(item_id)
            return await self._destination.upsert_employee(employee)

        try:
            response = await upsert_employee()
        except providers.ExternalSystemError as error:
            await models.sync_item_fail(item_id, str(error))
            return

        await models.sync_item_succeed(item_id, response.model_dump(mode='json'))

    def _retry_external_call(self, operation):
        return retries.retry(
            exception=providers.ExternalSystemError,
            max_retries=self._max_retries,
            max_value=self._retry_delay_seconds,
        )(operation)
