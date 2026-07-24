import datetime
import typing

import pydantic


ShortString = typing.Annotated[str, pydantic.StringConstraints(min_length=1, max_length=255)]
ExternalID = typing.Annotated[str, pydantic.StringConstraints(min_length=1, max_length=128)]


class EmployeeRecord(pydantic.BaseModel):
    external_id: ExternalID
    full_name: ShortString
    email: pydantic.EmailStr
    department: ShortString
    updated_at: datetime.datetime

    model_config = pydantic.ConfigDict(extra='forbid')


class SystemAResponse(pydantic.BaseModel):
    items: list[EmployeeRecord]

    model_config = pydantic.ConfigDict(extra='forbid')


class SystemBRecord(pydantic.BaseModel):
    full_name: ShortString
    email: pydantic.EmailStr
    department: ShortString
    source_updated_at: datetime.datetime

    model_config = pydantic.ConfigDict(extra='forbid')


class SystemBResponse(pydantic.BaseModel):
    external_id: ExternalID
    status: typing.Literal['created', 'updated']

    model_config = pydantic.ConfigDict(extra='forbid')
