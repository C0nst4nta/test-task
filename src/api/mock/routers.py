import datetime

import fastapi

from ...core import conf
from .. import schemas


router = fastapi.APIRouter(prefix='/mock')


_SYSTEM_A_EMPLOYEES = [
    schemas.EmployeeRecord(
        external_id='employee-001',
        full_name='Alice Johnson',
        email='alice.johnson@example.com',
        department='Engineering',
        updated_at=datetime.datetime(2026, 7, 20, 10, 0, tzinfo=datetime.UTC),
    ),
    schemas.EmployeeRecord(
        external_id='employee-002',
        full_name='Bob Smith',
        email='bob.smith@example.com',
        department='Finance',
        updated_at=datetime.datetime(2026, 7, 21, 11, 30, tzinfo=datetime.UTC),
    ),
    schemas.EmployeeRecord(
        external_id='employee-003',
        full_name='Carol Williams',
        email='carol.williams@example.com',
        department='Operations',
        updated_at=datetime.datetime(2026, 7, 22, 9, 15, tzinfo=datetime.UTC),
    ),
]
_SYSTEM_B_EMPLOYEES: dict[str, schemas.SystemBRecord] = {}


@router.get(
    '/system-a/records',
    summary='Mock System A: list records',
    response_model=schemas.SystemAResponse,
    tags=['Mock systems'],
)
async def mock_system_a_records():
    if conf.get_settings().mock_system_a_fail:
        raise fastapi.HTTPException(status_code=503, detail='Simulated System A failure')
    return {'items': _SYSTEM_A_EMPLOYEES}


@router.put(
    '/system-b/records/{external_id}',
    summary='Mock System B: upsert a record',
    response_model=schemas.SystemBResponse,
    tags=['Mock systems'],
)
async def mock_system_b_upsert(external_id: str, record: schemas.SystemBRecord):
    settings = conf.get_settings()
    if external_id in settings.mock_system_b_failed_ids:
        raise fastapi.HTTPException(status_code=503, detail='Simulated System B failure')

    status = 'updated' if external_id in _SYSTEM_B_EMPLOYEES else 'created'
    _SYSTEM_B_EMPLOYEES[external_id] = record
    return {'external_id': external_id, 'status': status}


@router.get(
    '/system-b/records',
    summary='Mock System B: inspect stored records',
    response_model=dict[str, schemas.SystemBRecord],
    tags=['Mock systems'],
)
async def mock_system_b_records():
    return _SYSTEM_B_EMPLOYEES


def get_router() -> fastapi.APIRouter:
    return router
