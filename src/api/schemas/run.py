import datetime
import enum
import typing
import uuid

import pydantic

from .item import SyncItemGet


class SyncType(enum.StrEnum):
    EMPLOYEES = 'employees'


class SyncTrigger(enum.StrEnum):
    MANUAL = 'manual'
    SCHEDULED = 'scheduled'
    RETRY = 'retry'


class SyncRunStatus(enum.StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    PARTIALLY_COMPLETED = 'partially_completed'
    FAILED = 'failed'


class SyncRunCreate(pydantic.BaseModel):
    sync_type: SyncType = SyncType.EMPLOYEES

    model_config = pydantic.ConfigDict(extra='forbid')


class SyncRunGet(pydantic.BaseModel):
    id: uuid.UUID
    sync_type: SyncType
    trigger: SyncTrigger
    status: SyncRunStatus
    retry_of_id: uuid.UUID | None
    total_items: pydantic.NonNegativeInt
    succeeded_items: pydantic.NonNegativeInt
    failed_items: pydantic.NonNegativeInt
    error_message: str | None
    queued_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None

    model_config = pydantic.ConfigDict(extra='ignore', from_attributes=True)


class SyncRunDetail(SyncRunGet):
    items: list[SyncItemGet] = pydantic.Field(default_factory=list)


class Pagination(pydantic.BaseModel):
    limit: pydantic.PositiveInt
    offset: pydantic.NonNegativeInt
    total: pydantic.NonNegativeInt


class SyncRunList(pydantic.BaseModel):
    sync_runs: list[SyncRunGet]
    pagination: Pagination


class SyncCurrent(pydantic.BaseModel):
    active_run: SyncRunGet | None
    last_run: SyncRunGet | None


class SyncRunListQueryParams(pydantic.BaseModel):
    limit: typing.Annotated[int, pydantic.Field(ge=1, le=100)] = 20
    offset: typing.Annotated[int, pydantic.Field(ge=0)] = 0
    status: SyncRunStatus | None = None
    trigger: SyncTrigger | None = None
    sync_type: SyncType | None = None

    model_config = pydantic.ConfigDict(extra='forbid')
