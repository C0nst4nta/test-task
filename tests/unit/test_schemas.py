import datetime

import pydantic
import pytest

from src.api import schemas


def test_employee_record_rejects_extra_fields():
    with pytest.raises(pydantic.ValidationError):
        schemas.EmployeeRecord(
            external_id='employee-1',
            full_name='Employee',
            email='employee@example.com',
            department='Engineering',
            updated_at=datetime.datetime.now(datetime.UTC),
            unknown='value',
        )


def test_employee_record_validates_email():
    with pytest.raises(pydantic.ValidationError):
        schemas.EmployeeRecord(
            external_id='employee-1',
            full_name='Employee',
            email='not-an-email',
            department='Engineering',
            updated_at=datetime.datetime.now(datetime.UTC),
        )


def test_sync_run_create_defaults_to_employees():
    request = schemas.SyncRunCreate()
    assert request.sync_type == schemas.SyncType.EMPLOYEES


def test_sync_query_rejects_invalid_limit():
    with pytest.raises(pydantic.ValidationError):
        schemas.SyncRunListQueryParams(limit=101)


def test_sync_detail_uses_empty_item_list(sync_run):
    detail = schemas.SyncRunDetail.model_validate(sync_run)
    assert detail.items == []
