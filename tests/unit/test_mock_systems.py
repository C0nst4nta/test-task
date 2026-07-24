import types

import fastapi
import pytest

from src.api import schemas
from src.api.mock import routers


async def test_mock_system_a_returns_employees(monkeypatch):
    settings = types.SimpleNamespace(mock_system_a_fail=False)
    monkeypatch.setattr(routers.conf, 'get_settings', lambda: settings)

    result = await routers.mock_system_a_records()

    assert len(result['items']) == 3


async def test_mock_system_a_can_fail(monkeypatch):
    settings = types.SimpleNamespace(mock_system_a_fail=True)
    monkeypatch.setattr(routers.conf, 'get_settings', lambda: settings)

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await routers.mock_system_a_records()
    assert exc_info.value.status_code == 503


async def test_mock_system_b_creates_and_updates(employee, monkeypatch):
    settings = types.SimpleNamespace(mock_system_b_failed_ids=set())
    monkeypatch.setattr(routers.conf, 'get_settings', lambda: settings)
    routers._SYSTEM_B_EMPLOYEES.clear()
    record = schemas.SystemBRecord(
        full_name=employee.full_name,
        email=employee.email,
        department=employee.department,
        source_updated_at=employee.updated_at,
    )

    created = await routers.mock_system_b_upsert(employee.external_id, record)
    updated = await routers.mock_system_b_upsert(employee.external_id, record)

    assert created['status'] == 'created'
    assert updated['status'] == 'updated'
    assert await routers.mock_system_b_records() == {employee.external_id: record}
    assert routers.get_router() is routers.router


async def test_mock_system_b_can_fail(employee, monkeypatch):
    settings = types.SimpleNamespace(mock_system_b_failed_ids={employee.external_id})
    monkeypatch.setattr(routers.conf, 'get_settings', lambda: settings)
    record = schemas.SystemBRecord(
        full_name=employee.full_name,
        email=employee.email,
        department=employee.department,
        source_updated_at=employee.updated_at,
    )

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await routers.mock_system_b_upsert(employee.external_id, record)
    assert exc_info.value.status_code == 503
