import datetime
import enum
import uuid

import pydantic


class SyncItemStatus(enum.StrEnum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'


class SyncItemGet(pydantic.BaseModel):
    id: uuid.UUID
    external_id: str
    status: SyncItemStatus
    attempts: pydantic.NonNegativeInt
    source_payload: dict
    destination_response: dict | None
    error_message: str | None
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None

    model_config = pydantic.ConfigDict(extra='ignore', from_attributes=True)
